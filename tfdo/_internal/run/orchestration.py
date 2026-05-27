from __future__ import annotations

import json
import logging
from concurrent.futures import Future
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from ask_shell.shell import run_and_wait, run_pool
from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import ensure_parents_write_text, find_repo_root

from tfdo._internal.config import backend_resolution, config_resolution
from tfdo._internal.config.config_file import load_config_layers
from tfdo._internal.config.config_model import DependencyRef
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import LifecycleCommand, LifecycleEvent
from tfdo._internal.core import executor, lifecycle_init_retry, terraform_init
from tfdo._internal.git_utils import parse_git_remote
from tfdo._internal.hooks import execution as hook_execution
from tfdo._internal.hooks.execution import HookContext
from tfdo._internal.hooks.models import HookAbortError
from tfdo._internal.hooks.registry import HookRegistry
from tfdo._internal.hooks.runner import LocalHookRunner
from tfdo._internal.models import ApplyInput, DestroyInput, InitInput, InitMode, OutputInput, PlanInput
from tfdo._internal.output.plan_display import PlanDisplayCliOverrides
from tfdo._internal.run import filtering, tags_injection, var_file_resolution
from tfdo._internal.run.discovery import (
    DiscoveredRunDir,
    build_run_dir_contexts,
    discover_run_dirs,
)
from tfdo._internal.run.filtering import TagFilter
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.settings import TfDoSettings, load_user_config

logger = logging.getLogger(__name__)

MIN_CONCURRENT_SUBMITS = 2


class FailureMode(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"


DEFAULT_PARALLEL = 10


class RunOrchestrationInput(BaseModel):
    settings: TfDoSettings
    command: LifecycleCommand
    parallel: int = DEFAULT_PARALLEL
    on_failure: FailureMode = FailureMode.STOP
    dry_run: bool = False
    changed: bool = False
    selector_filters: dict[str, str] = Field(default_factory=dict)
    tag_filters: list[str] = Field(default_factory=list)
    init_mode: InitMode = InitMode.AUTO
    var_file: Path | None = None
    extra_flags: list[str] = Field(default_factory=list)
    auto_approve: bool = False
    plan_display_cli: PlanDisplayCliOverrides = Field(default_factory=PlanDisplayCliOverrides)


class RunDirResult(BaseModel):
    run_dir: str
    exit_code: int
    skipped: bool = False
    stdout: str = ""
    stderr: str = ""


class OrchestrationResult(BaseModel):
    results: list[RunDirResult] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        for r in self.results:
            if r.exit_code != 0:
                return r.exit_code
        return 0


class ExecutionWave(BaseModel):
    wave_index: int
    run_dirs: list[str]


class ExecutionPlan(BaseModel):
    waves: list[ExecutionWave] = Field(default_factory=list)

    @property
    def total_run_dirs(self) -> int:
        return sum(len(w.run_dirs) for w in self.waves)

    def reversed(self) -> ExecutionPlan:
        return ExecutionPlan(
            waves=[ExecutionWave(wave_index=i, run_dirs=w.run_dirs) for i, w in enumerate(reversed(self.waves))]
        )


class DependencyGraph(BaseModel):
    edges: dict[str, set[str]] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    def to_waves(self) -> ExecutionPlan:
        all_nodes = set(self.edges.keys())
        in_degree: dict[str, int] = {n: 0 for n in all_nodes}
        for node, deps in self.edges.items():
            in_degree[node] = len(deps)

        remaining = dict(in_degree)
        waves: list[ExecutionWave] = []
        wave_idx = 0
        while remaining:
            ready = sorted(n for n, deg in remaining.items() if deg == 0)
            if not ready:
                cycle_nodes = sorted(remaining.keys())
                raise ValueError(f"dependency cycle detected among: {cycle_nodes}")
            waves.append(ExecutionWave(wave_index=wave_idx, run_dirs=ready))
            for n in ready:
                del remaining[n]
            for node in remaining:
                removed = sum(1 for dep in self.edges[node] if dep in set(ready))
                remaining[node] -= removed
            wave_idx += 1
        return ExecutionPlan(waves=waves)


def _resolve_ref(ref: str, run_dir_path: str, all_paths: set[str]) -> str:
    parent = run_dir_path.rsplit("/", 1)[0] if "/" in run_dir_path else ""
    sibling = f"{parent}/{ref}" if parent else ref
    if sibling not in all_paths:
        raise ValueError(
            f"dependency ref '{ref}' from '{run_dir_path}' resolves to '{sibling}' which is not a discovered run_dir"
        )
    return sibling


def build_dependency_graph(
    discovered: list[DiscoveredRunDir],
    configs: dict[str, ResolvedConfig],
) -> DependencyGraph:
    all_paths = {d.relative_path for d in discovered}
    edges: dict[str, set[str]] = {}
    for d in discovered:
        deps: set[str] = set()
        if cfg := configs.get(d.relative_path):
            for dep_ref in cfg.dependencies:
                deps.add(_resolve_ref(dep_ref.ref, d.relative_path, all_paths))
        edges[d.relative_path] = deps
    return DependencyGraph(edges=edges)


class PreparedRunDir(NamedTuple):
    init_input: InitInput
    lifecycle_flags: list[str]


def prepare_run_dir(
    settings: TfDoSettings,
    run_dir_path: Path,
    ctx: RunDirContext,
    config: ResolvedConfig,
    cli_var_file: Path | None,
) -> PreparedRunDir:
    backend_args = backend_resolution.resolve_init_backend_args(config.backend, ctx)

    var_files = var_file_resolution.resolve_var_files(run_dir_path, config.var_files, [])
    var_file_resolution.validate_var_files(var_files)

    tags_file = tags_injection.resolve_tags_injection(
        run_dir_path,
        config.tags,
        config.tags_inject,
        run_dir_path,
    )

    all_var_flags = var_file_resolution.var_file_flags(var_files)
    if tags_file:
        all_var_flags.append(f"-var-file={tags_file}")
    if cli_var_file:
        all_var_flags.append(f"-var-file={cli_var_file}")

    dir_settings = settings.with_overrides(run_dir_path, config.binary, config.tf_version)
    init_input = InitInput(settings=dir_settings, backend_args=backend_args)
    return PreparedRunDir(init_input=init_input, lifecycle_flags=all_var_flags)


DEP_TFVARS_SUFFIX = TfDoSettings.DEP_TFVARS_SUFFIX


def _dependency_outputs_or_log(
    init_input: InitInput, run_dir_path: Path, *, log_suffix: str = ""
) -> dict[str, object] | None:
    result = executor.output_json(OutputInput(settings=init_input.settings))
    if result.exit_code != 0:
        extra = f" {log_suffix}" if log_suffix else ""
        logger.warning(f"terraform output failed in {run_dir_path}{extra}: {result.stderr}")
        return None
    return result.outputs


def _outputs_after_prereq_init(init_input: InitInput, run_dir_path: Path) -> dict[str, object] | None:
    if (ir := terraform_init.init(init_input)).exit_code != 0:
        logger.warning(f"terraform init before output failed in {run_dir_path}: {ir.stderr}")
        return None
    return _dependency_outputs_or_log(init_input, run_dir_path)


def _outputs_retry_after_auto_init(
    init_input: InitInput,
    run_dir_path: Path,
    stderr: str,
) -> dict[str, object] | None:
    init_for_retry = lifecycle_init_retry.init_input_for_output_retry(stderr, init_input)
    if init_for_retry is None:
        logger.warning(f"terraform output failed in {run_dir_path}: {stderr}")
        return None
    if (ir := terraform_init.init(init_for_retry)).exit_code != 0:
        logger.warning(f"terraform init before output retry failed in {run_dir_path}: {ir.stderr}")
        return None
    return _dependency_outputs_or_log(init_input, run_dir_path, log_suffix="after init")


def _collect_dependency_outputs(
    settings: TfDoSettings,
    run_dir_path: Path,
    ctx: RunDirContext,
    config: ResolvedConfig,
    init_mode: InitMode,
    var_file: Path | None,
) -> dict[str, object] | None:
    try:
        prepared = prepare_run_dir(settings, run_dir_path, ctx, config, var_file)
    except Exception as e:
        logger.warning(f"dependency output prepare failed in {run_dir_path}: {e}")
        return None
    init_input = prepared.init_input
    if init_mode == InitMode.ALWAYS:
        return _outputs_after_prereq_init(init_input, run_dir_path)

    first = executor.output_json(OutputInput(settings=init_input.settings))
    if first.exit_code == 0:
        return first.outputs
    if init_mode == InitMode.NEVER:
        logger.warning(f"terraform output failed in {run_dir_path}: {first.stderr}")
        return None
    return _outputs_retry_after_auto_init(init_input, run_dir_path, first.stderr or "")


def _resolve_dep_outputs(dep_ref: DependencyRef, collected: dict[str, object] | None) -> dict[str, str] | None:
    if not dep_ref.outputs:
        return None
    if collected is not None:
        mapped: dict[str, str] = {}  # pyright: ignore[reportRedeclaration]
        for out_name, local_var in dep_ref.outputs.items():
            if out_name not in collected:
                return None
            val = collected[out_name]
            if val is None:
                return None
            mapped[local_var] = str(val)
        return mapped
    if dep_ref.outputs_mock:
        mapped: dict[str, str] = {}
        for out_name, local_var in dep_ref.outputs.items():
            if out_name not in dep_ref.outputs_mock:
                return None
            mapped[local_var] = dep_ref.outputs_mock[out_name]
        return mapped
    return None


def _write_dep_tfvars(dependent_run_dir: Path, dep_name: str, mapped_values: dict[str, str]) -> Path:
    path = dependent_run_dir / f"{dep_name}{DEP_TFVARS_SUFFIX}"
    ensure_parents_write_text(path, json.dumps(mapped_values, indent=2) + "\n")
    return path


def _build_hook_registry(config: ResolvedConfig, run_dir_path: Path) -> HookRegistry | None:
    if not config.hook_configs:
        return None
    runner = LocalHookRunner(run_dir_path)
    return HookRegistry.from_hook_configs(config.hook_configs, runner)


def _dispatch_command(
    inp: RunOrchestrationInput,
    prepared: PreparedRunDir,
    extra_flags: list[str],
    rel: str,
) -> RunDirResult:
    dir_settings = prepared.init_input.settings
    if inp.command == LifecycleCommand.INIT:
        init_input = prepared.init_input
        if inp.extra_flags:
            init_input = InitInput(
                settings=init_input.settings,
                backend_args=init_input.backend_args,
                extra_args=[*init_input.extra_args, *inp.extra_flags],
                env=init_input.env,
            )
        init_result = terraform_init.init(init_input)
        return RunDirResult(
            run_dir=rel, exit_code=init_result.exit_code, stdout=init_result.stdout, stderr=init_result.stderr or ""
        )
    mode = inp.init_mode
    backend_args = prepared.init_input.backend_args
    if inp.command == LifecycleCommand.PLAN:
        result = executor.plan(
            PlanInput(
                settings=dir_settings,
                init_mode=mode,
                extra_args=extra_flags,
                init_backend_args=backend_args,
            )
        )
    elif inp.command == LifecycleCommand.APPLY:
        result = executor.apply(
            ApplyInput(
                settings=dir_settings,
                auto_approve=inp.auto_approve,
                init_mode=mode,
                extra_args=extra_flags,
                init_backend_args=backend_args,
                plan_display_cli=inp.plan_display_cli,
            )
        )
    elif inp.command == LifecycleCommand.DESTROY:
        result = executor.destroy(
            DestroyInput(
                settings=dir_settings,
                auto_approve=inp.auto_approve,
                init_mode=mode,
                extra_args=extra_flags,
                init_backend_args=backend_args,
            )
        )
    else:
        raise ValueError(f"unsupported command: {inp.command}")
    return RunDirResult(run_dir=rel, exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr or "")


def _run_event_hooks(registry: HookRegistry, event: LifecycleEvent, hook_ctx: HookContext, rel: str) -> None:
    try:
        hook_execution.run_hooks(registry, event, hook_ctx)
    except HookAbortError as e:
        logger.warning(f"{rel}: {e}")
    except Exception as e:
        logger.warning(f"{rel}: unexpected error in {event} hooks: {e}")


def _execute_run_dir(
    inp: RunOrchestrationInput,
    run_dir_path: Path,
    ctx: RunDirContext,
    config: ResolvedConfig,
) -> RunDirResult:
    rel = ctx.path
    try:
        prepared = prepare_run_dir(inp.settings, run_dir_path, ctx, config, inp.var_file)
    except Exception as e:
        logger.error(f"{rel}: preparation failed: {e}")
        return RunDirResult(run_dir=rel, exit_code=1, stderr=str(e))

    registry = _build_hook_registry(config, run_dir_path)
    hook_ctx = HookContext(run_dir=run_dir_path, command=inp.command)
    all_extra = [*prepared.lifecycle_flags, *inp.extra_flags]

    before_event, after_event = hook_execution.lifecycle_events(inp.command)
    if registry:
        try:
            hook_execution.run_hooks(registry, before_event, hook_ctx)
        except HookAbortError as e:
            _run_event_hooks(registry, LifecycleEvent.ON_ERROR, hook_ctx, rel)
            return RunDirResult(run_dir=rel, exit_code=1, stderr=str(e))

    result_dir = _dispatch_command(inp, prepared, all_extra, rel)

    if registry:
        try:
            hook_execution.run_hooks(registry, after_event, hook_ctx)
        except HookAbortError as e:
            logger.warning(f"{rel}: {e}")
        ok_or_error = LifecycleEvent.ON_OK if result_dir.exit_code == 0 else LifecycleEvent.ON_ERROR
        _run_event_hooks(registry, ok_or_error, hook_ctx, rel)

    return result_dir


def _log_run_dir_output(result: RunDirResult, command: str) -> None:
    header = f"=== {result.run_dir} ({command}) ==="
    logger.info(header)
    if result.stdout:
        logger.info(result.stdout)
    if result.stderr:
        logger.warning(result.stderr)
    status = "OK" if result.exit_code == 0 else f"FAILED (exit {result.exit_code})"
    logger.info(f"--- {status} ---")


def _discover_run_dirs(repo_root: Path) -> list[DiscoveredRunDir]:
    root_layers = load_config_layers(repo_root)
    if not root_layers:
        raise ValueError(f"no tfdo.yaml found at or above {repo_root}")

    root_config = root_layers[-1].config
    if not root_config.run_dir_discovery:
        raise ValueError("root tfdo.yaml must define run_dir_discovery pattern")

    return discover_run_dirs(repo_root, root_config.parsed_pattern())


def _resolve_all_configs(
    discovered: list[DiscoveredRunDir],
    inp: RunOrchestrationInput,
    repo_root: Path,
) -> tuple[dict[str, ResolvedConfig], dict[str, RunDirContext]]:
    user_config = load_user_config(inp.settings)
    remote = parse_git_remote(repo_root)
    owner = remote.org if remote else "unknown"
    repo_name = remote.repo if remote else repo_root.name
    configs: dict[str, ResolvedConfig] = {}
    contexts: dict[str, RunDirContext] = {}
    for d in discovered:
        dir_layers = load_config_layers(d.path)
        cfg = config_resolution.resolve_config(dir_layers, user_config, inp.settings, d.selectors)
        configs[d.relative_path] = cfg
        ctx_list = build_run_dir_contexts([d], cfg, owner, repo_name)
        contexts[d.relative_path] = ctx_list[0]
    return configs, contexts


_OUTPUT_INJECT_COMMANDS = {LifecycleCommand.APPLY, LifecycleCommand.PLAN, LifecycleCommand.DESTROY}


def _inject_dep_outputs(
    rel_path: str,
    inp: RunOrchestrationInput,
    repo_root: Path,
    configs: dict[str, ResolvedConfig],
    collected_outputs: dict[str, dict[str, object] | None],
) -> list[str] | None:
    """Write .dep.tfvars.json files and return extra var-file flags. Returns None to signal skip."""
    cfg = configs.get(rel_path)
    if not cfg or not cfg.dependencies:
        return []
    extra_flags: list[str] = []
    for dep_ref in cfg.dependencies:
        if not dep_ref.outputs:
            continue
        dep_path = _resolve_ref_path(dep_ref.ref, rel_path)
        collected = collected_outputs.get(dep_path)
        resolved = _resolve_dep_outputs(dep_ref, collected)
        if resolved is None:
            if inp.command == LifecycleCommand.PLAN:
                logger.warning(f"{rel_path}: skipping, no outputs or mocks for dependency '{dep_ref.ref}'")
                return None
            raise ValueError(f"{rel_path}: dependency '{dep_ref.ref}' has no outputs and no mocks")
        dep_name = dep_ref.ref.rsplit("/", 1)[-1]
        tfvars_path = _write_dep_tfvars(repo_root / rel_path, dep_name, resolved)
        extra_flags.append(f"-var-file={tfvars_path}")
    return extra_flags


def _execute_wave_sequential(
    wave: ExecutionWave,
    inp: RunOrchestrationInput,
    repo_root: Path,
    contexts: dict[str, RunDirContext],
    configs: dict[str, ResolvedConfig],
    collected_outputs: dict[str, dict[str, object] | None] | None = None,
) -> tuple[list[RunDirResult], bool]:
    results: list[RunDirResult] = []
    has_failure = False
    for rel_path in wave.run_dirs:
        if collected_outputs is not None and inp.command in _OUTPUT_INJECT_COMMANDS:
            dep_flags = _inject_dep_outputs(rel_path, inp, repo_root, configs, collected_outputs)
            if dep_flags is None:
                results.append(RunDirResult(run_dir=rel_path, exit_code=0, skipped=True))
                continue
            if dep_flags:
                inp = inp.model_copy(update={"extra_flags": [*inp.extra_flags, *dep_flags]})
        result = _execute_run_dir(inp, repo_root / rel_path, contexts[rel_path], configs[rel_path])
        results.append(result)
        _log_run_dir_output(result, inp.command)
        if result.exit_code == 0 and collected_outputs is not None and inp.command != LifecycleCommand.DESTROY:
            collected_outputs[rel_path] = _collect_dependency_outputs(
                inp.settings,
                repo_root / rel_path,
                contexts[rel_path],
                configs[rel_path],
                inp.init_mode,
                inp.var_file,
            )
        if result.exit_code != 0:
            has_failure = True
    return results, has_failure


def _execute_wave_parallel(
    wave: ExecutionWave,
    inp: RunOrchestrationInput,
    repo_root: Path,
    contexts: dict[str, RunDirContext],
    configs: dict[str, ResolvedConfig],
    effective_parallel: int,
    collected_outputs: dict[str, dict[str, object] | None] | None = None,
) -> tuple[list[RunDirResult], bool]:
    max_submits = min(max(effective_parallel, MIN_CONCURRENT_SUBMITS), len(wave.run_dirs))
    futures: list[tuple[str, Future[RunDirResult]]] = []

    with run_pool(
        task_name=f"wave-{wave.wave_index}",
        total=len(wave.run_dirs),
        max_concurrent_submits=max_submits,
        pool_thread_count=max_submits,
    ) as pool:
        for rel_path in wave.run_dirs:
            fut = pool.submit(_execute_run_dir, inp, repo_root / rel_path, contexts[rel_path], configs[rel_path])
            futures.append((rel_path, fut))

    results: list[RunDirResult] = []
    has_failure = False
    for rel_path, fut in futures:
        result = fut.result()
        results.append(result)
        _log_run_dir_output(result, inp.command)
        if result.exit_code == 0 and collected_outputs is not None and inp.command != LifecycleCommand.DESTROY:
            collected_outputs[rel_path] = _collect_dependency_outputs(
                inp.settings,
                repo_root / rel_path,
                contexts[rel_path],
                configs[rel_path],
                inp.init_mode,
                inp.var_file,
            )
        if result.exit_code != 0:
            has_failure = True
    return results, has_failure


def _execute_plan(
    plan: ExecutionPlan,
    inp: RunOrchestrationInput,
    repo_root: Path,
    contexts: dict[str, RunDirContext],
    configs: dict[str, ResolvedConfig],
) -> list[RunDirResult]:
    needs_approval = not inp.auto_approve and inp.command in (LifecycleCommand.APPLY, LifecycleCommand.DESTROY)
    sequential = inp.parallel == 1 or needs_approval
    if needs_approval:
        logger.warning(f"interactive approval: running sequentially for {inp.command}")

    collected_outputs: dict[str, dict[str, object] | None] | None = (
        {} if inp.command in _OUTPUT_INJECT_COMMANDS else None
    )
    if collected_outputs is not None and inp.command == LifecycleCommand.DESTROY:
        for wave in plan.waves:
            for rel_path in wave.run_dirs:
                collected_outputs[rel_path] = _collect_dependency_outputs(
                    inp.settings,
                    repo_root / rel_path,
                    contexts[rel_path],
                    configs[rel_path],
                    inp.init_mode,
                    inp.var_file,
                )
    all_results: list[RunDirResult] = []
    for wave in plan.waves:
        use_sequential = sequential or len(wave.run_dirs) <= 1
        wave_results, has_failure = (
            _execute_wave_sequential(wave, inp, repo_root, contexts, configs, collected_outputs)
            if use_sequential
            else _execute_wave_parallel(wave, inp, repo_root, contexts, configs, inp.parallel, collected_outputs)
        )
        all_results.extend(wave_results)
        if has_failure and inp.on_failure == FailureMode.STOP:
            for remaining_wave in plan.waves[wave.wave_index + 1 :]:
                for rd in remaining_wave.run_dirs:
                    all_results.append(RunDirResult(run_dir=rd, exit_code=1, skipped=True))
            break
    return all_results


def _resolve_ref_path(ref: str, run_dir_path: str) -> str:
    parent = run_dir_path.rsplit("/", 1)[0] if "/" in run_dir_path else ""
    return f"{parent}/{ref}" if parent else ref


def _include_dependency_targets(
    filtered: list[DiscoveredRunDir],
    all_discovered: list[DiscoveredRunDir],
    configs: dict[str, ResolvedConfig],
) -> list[DiscoveredRunDir]:
    """Pull in transitive dependency targets that were excluded by filters."""
    filtered_paths = {d.relative_path for d in filtered}
    all_by_path = {d.relative_path: d for d in all_discovered}
    added: set[str] = set()
    queue = list(filtered_paths)
    while queue:
        rel = queue.pop()
        if cfg := configs.get(rel):
            for dep_ref in cfg.dependencies:
                dep_path = _resolve_ref_path(dep_ref.ref, rel)
                if dep_path not in filtered_paths and dep_path not in added and dep_path in all_by_path:
                    added.add(dep_path)
                    queue.append(dep_path)
    if added:
        logger.info(f"auto-included {len(added)} dependency targets: {sorted(added)}")
        return sorted(
            [*filtered, *(all_by_path[p] for p in added)],
            key=lambda d: d.relative_path,
        )
    return filtered


def _get_changed_files(repo_root: Path) -> list[str]:
    run = run_and_wait("git diff --name-only HEAD", cwd=repo_root, allow_non_zero_exit=True, skip_binary_check=True)
    return [line.strip() for line in run.stdout.strip().splitlines() if line.strip()]


def _build_effective_filters(
    inp: RunOrchestrationInput,
    all_discovered: list[DiscoveredRunDir],
) -> tuple[dict[str, str] | None, list[TagFilter] | None]:
    selector_filters = dict(inp.selector_filters) if inp.selector_filters else {}
    tag_filters = [TagFilter.parse(t) for t in inp.tag_filters]

    if "team" in selector_filters:
        has_team_selector = any("team" in d.selectors for d in all_discovered)
        if not has_team_selector:
            team_val = selector_filters.pop("team")
            tag_filters.append(TagFilter(key="team", values=team_val.split(",")))

    return selector_filters or None, tag_filters or None


def _fire_on_all_done(repo_root: Path, inp: RunOrchestrationInput) -> None:
    root_layers = load_config_layers(repo_root)
    if not root_layers:
        return
    user_config = load_user_config(inp.settings)
    root_config = config_resolution.resolve_config(root_layers, user_config, inp.settings)
    registry = _build_hook_registry(root_config, repo_root)
    if not registry:
        return
    if not registry.get_hooks(LifecycleEvent.ON_ALL_DONE):
        return
    hook_ctx = HookContext(run_dir=repo_root, command=inp.command)
    _run_event_hooks(registry, LifecycleEvent.ON_ALL_DONE, hook_ctx, "orchestration")


def run_orchestration(inp: RunOrchestrationInput) -> OrchestrationResult:
    repo_root = find_repo_root(inp.settings.work_dir)
    all_discovered = _discover_run_dirs(repo_root)
    if not all_discovered:
        logger.warning("no run directories matched filters")
        return OrchestrationResult()

    configs, contexts = _resolve_all_configs(all_discovered, inp, repo_root)
    resolved_tags = {rel: cfg.tags for rel, cfg in configs.items()}
    selector_filters, tag_filters = _build_effective_filters(inp, all_discovered)
    changed_files = _get_changed_files(repo_root) if inp.changed else None
    discovered = filtering.apply_filters(
        all_discovered,
        selector_filters=selector_filters,
        tag_filters=tag_filters,
        changed_files=changed_files,
        resolved_tags=resolved_tags,
    )
    if not discovered:
        logger.warning("no run directories matched filters")
        return OrchestrationResult()

    discovered = _include_dependency_targets(discovered, all_discovered, configs)
    graph = build_dependency_graph(discovered, configs)
    plan = graph.to_waves()
    if inp.command == LifecycleCommand.DESTROY:
        plan = plan.reversed()

    if inp.dry_run:
        for wave in plan.waves:
            for rd in wave.run_dirs:
                logger.info(f"[dry-run] wave {wave.wave_index}: {rd} -> {inp.command}")
        return OrchestrationResult(
            results=[RunDirResult(run_dir=rd, exit_code=0, skipped=True) for w in plan.waves for rd in w.run_dirs],
        )

    results = _execute_plan(plan, inp, repo_root, contexts, configs)
    _fire_on_all_done(repo_root, inp)
    return OrchestrationResult(results=results)
