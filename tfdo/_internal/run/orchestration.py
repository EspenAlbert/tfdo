from __future__ import annotations

import logging
import re
from concurrent.futures import Future
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from ask_shell.shell import run_and_wait, run_pool
from pydantic import BaseModel, Field
from zero_3rdparty.file_utils import find_repo_root

from tfdo._internal.config import backend_resolution, config_resolution
from tfdo._internal.config.config_file import load_config_layers
from tfdo._internal.config.config_resolution import ResolvedConfig
from tfdo._internal.config.enums import LifecycleCommand, LifecycleEvent
from tfdo._internal.core import executor
from tfdo._internal.hooks import execution as hook_execution
from tfdo._internal.hooks.execution import HookContext
from tfdo._internal.hooks.models import HookAbortError
from tfdo._internal.hooks.registry import HookRegistry
from tfdo._internal.hooks.runner import LocalHookRunner
from tfdo._internal.models import ApplyInput, DestroyInput, InitInput, InitMode, PlanInput
from tfdo._internal.run import filtering, tags_injection, var_file_resolution
from tfdo._internal.run.discovery import (
    DiscoveredRunDir,
    build_run_dir_contexts,
    discover_run_dirs,
    parse_discovery_pattern,
)
from tfdo._internal.run.filtering import TagFilter
from tfdo._internal.run.run_context import RunDirContext
from tfdo._internal.settings import TfDoSettings, load_user_config

logger = logging.getLogger(__name__)

MIN_CONCURRENT_SUBMITS = 2
_GIT_REMOTE_RE = re.compile(r"(?:https?://[^/]+/|git@[^:]+:)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$")


def _parse_git_remote_url(url: str) -> tuple[str, str] | None:
    if m := _GIT_REMOTE_RE.match(url.strip()):
        return m.group("owner"), m.group("repo")
    return None


def _parse_git_remote(repo_root: Path) -> tuple[str, str]:
    """Returns (owner, repo_name) from git remote origin URL."""
    try:
        run = run_and_wait(
            "git remote get-url origin",
            cwd=repo_root,
            allow_non_zero_exit=True,
            skip_binary_check=True,
        )
        url = run.stdout.strip()
        if result := _parse_git_remote_url(url):
            return result
    except Exception:
        logger.error(f"failed to read git remote for {repo_root}")
    return ("unknown", repo_root.name)


class FailureMode(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"


class RunOrchestrationInput(BaseModel):
    settings: TfDoSettings
    command: LifecycleCommand
    parallel: int = 10
    on_failure: FailureMode = FailureMode.STOP
    dry_run: bool = False
    selector_filters: dict[str, str] = Field(default_factory=dict)
    tag_filters: list[str] = Field(default_factory=list)
    init_mode: InitMode = InitMode.AUTO
    var_file: Path | None = None
    extra_flags: list[str] = Field(default_factory=list)
    auto_approve: bool = False


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
        init_result = executor.init(prepared.init_input)
        return RunDirResult(
            run_dir=rel, exit_code=init_result.exit_code, stdout=init_result.stdout, stderr=init_result.stderr or ""
        )
    mode = inp.init_mode
    backend_args = prepared.init_input.backend_args
    if inp.command == LifecycleCommand.PLAN:
        result = executor.plan(
            PlanInput(settings=dir_settings, init_mode=mode, extra_args=extra_flags, init_backend_args=backend_args)
        )
    elif inp.command == LifecycleCommand.APPLY:
        result = executor.apply(
            ApplyInput(
                settings=dir_settings,
                auto_approve=inp.auto_approve,
                init_mode=mode,
                extra_args=extra_flags,
                init_backend_args=backend_args,
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

    pattern = parse_discovery_pattern(root_config.run_dir_discovery)
    return discover_run_dirs(repo_root, pattern)


def _resolve_all_configs(
    discovered: list[DiscoveredRunDir],
    inp: RunOrchestrationInput,
    repo_root: Path,
) -> tuple[dict[str, ResolvedConfig], dict[str, RunDirContext]]:
    user_config = load_user_config(inp.settings)
    owner, repo_name = _parse_git_remote(repo_root)
    configs: dict[str, ResolvedConfig] = {}
    contexts: dict[str, RunDirContext] = {}
    for d in discovered:
        dir_layers = load_config_layers(d.path)
        cfg = config_resolution.resolve_config(dir_layers, user_config, inp.settings, d.selectors)
        configs[d.relative_path] = cfg
        ctx_list = build_run_dir_contexts([d], cfg, owner, repo_name)
        contexts[d.relative_path] = ctx_list[0]
    return configs, contexts


def _execute_wave_sequential(
    wave: ExecutionWave,
    inp: RunOrchestrationInput,
    repo_root: Path,
    contexts: dict[str, RunDirContext],
    configs: dict[str, ResolvedConfig],
) -> tuple[list[RunDirResult], bool]:
    results: list[RunDirResult] = []
    has_failure = False
    for rel_path in wave.run_dirs:
        result = _execute_run_dir(inp, repo_root / rel_path, contexts[rel_path], configs[rel_path])
        results.append(result)
        _log_run_dir_output(result, inp.command)
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
) -> tuple[list[RunDirResult], bool]:
    max_submits = max(effective_parallel, MIN_CONCURRENT_SUBMITS)
    futures: list[tuple[str, Future[RunDirResult]]] = []

    with run_pool(
        task_name=f"wave-{wave.wave_index}", total=len(wave.run_dirs), max_concurrent_submits=max_submits
    ) as pool:
        for rel_path in wave.run_dirs:
            fut = pool.submit(_execute_run_dir, inp, repo_root / rel_path, contexts[rel_path], configs[rel_path])
            futures.append((rel_path, fut))

    results: list[RunDirResult] = []
    has_failure = False
    for _, fut in futures:
        result = fut.result()
        results.append(result)
        _log_run_dir_output(result, inp.command)
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
    sequential = inp.parallel == 1 or (
        not inp.auto_approve and inp.command in (LifecycleCommand.APPLY, LifecycleCommand.DESTROY)
    )
    if sequential:
        logger.warning(f"interactive approval: running sequentially for {inp.command}")

    all_results: list[RunDirResult] = []
    for wave in plan.waves:
        wave_results, has_failure = (
            _execute_wave_sequential(wave, inp, repo_root, contexts, configs)
            if sequential
            else _execute_wave_parallel(wave, inp, repo_root, contexts, configs, inp.parallel)
        )
        all_results.extend(wave_results)
        if has_failure and inp.on_failure == FailureMode.STOP:
            for remaining_wave in plan.waves[wave.wave_index + 1 :]:
                for rd in remaining_wave.run_dirs:
                    all_results.append(RunDirResult(run_dir=rd, exit_code=1, skipped=True))
            break
    return all_results


def run_orchestration(inp: RunOrchestrationInput) -> OrchestrationResult:
    repo_root = find_repo_root(inp.settings.work_dir)
    all_discovered = _discover_run_dirs(repo_root)
    if not all_discovered:
        logger.warning("no run directories matched filters")
        return OrchestrationResult()

    configs, contexts = _resolve_all_configs(all_discovered, inp, repo_root)
    resolved_tags = {rel: cfg.tags for rel, cfg in configs.items()}
    tag_filters = [TagFilter.parse(t) for t in inp.tag_filters]
    discovered = filtering.apply_filters(
        all_discovered,
        selector_filters=inp.selector_filters or None,
        tag_filters=tag_filters or None,
        resolved_tags=resolved_tags,
    )
    if not discovered:
        logger.warning("no run directories matched filters")
        return OrchestrationResult()

    graph = build_dependency_graph(discovered, configs)
    plan = graph.to_waves()

    if inp.dry_run:
        for wave in plan.waves:
            for rd in wave.run_dirs:
                logger.info(f"[dry-run] wave {wave.wave_index}: {rd} -> {inp.command}")
        return OrchestrationResult(
            results=[RunDirResult(run_dir=rd, exit_code=0, skipped=True) for w in plan.waves for rd in w.run_dirs],
        )

    return OrchestrationResult(results=_execute_plan(plan, inp, repo_root, contexts, configs))
