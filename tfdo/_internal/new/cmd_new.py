from __future__ import annotations

import logging
from pathlib import Path
from typing import NamedTuple

import typer
from ask_shell._internal.interactive import (
    ChoiceTyped,
    NewHandlerChoice,
    SelectOptions,
    confirm,
    select_list,
    select_list_choice,
    select_list_multiple_choices,
    text,
)

from tfdo._internal.cache import module_cache
from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import DependencyRef, TfDoConfig
from tfdo._internal.config.provider_hints import ModuleChoice, available_module_choices, load_provider_hints
from tfdo._internal.hcl_entity_parser import TfModuleCall, TfOutput, parse_dir_entities, parse_module_examples
from tfdo._internal.hcl_example_prompt import _hcl_value_display
from tfdo._internal.hcl_roundtrip import HclAttrRef, HclLiteral, HclValue, HclVarRef, prepare_preserved_module_hcl
from tfdo._internal.new.backend_bootstrap import NewBackendInput, new_backend
from tfdo._internal.new.new_run_dir import (
    AttrPromotion,
    ModuleRunDirConfig,
    NewRunDirInput,
    _module_required_attrs,
    module_outputs,
    new_run_dir,
)
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

new_app = typer.Typer(help="Provision new tfdo-managed infrastructure")
app.add_typer(new_app, name="new")


@new_app.command("backend")
def backend_cmd(
    ctx: typer.Context,
    bucket: str = typer.Option(..., "--bucket", "-b", help="S3 bucket name for Terraform state"),
    region: str = typer.Option("us-east-1", "--region", "-r", help="AWS region"),
    key: str = typer.Option(
        "{path}/terraform.tfstate", "--key", help="State key template; {path} is resolved per run-dir"
    ),
) -> None:
    """Write backend.tf to all run-dirs."""
    settings = get_settings(ctx)
    result = new_backend(NewBackendInput(settings=settings, bucket=bucket, region=region, key=key))
    logger.info(f"tfdo.yaml updated: {result.updated_yaml}")
    logger.info(f"backend.tf written to {len(result.backend_tf_files)} run-dir(s):")
    for f in result.backend_tf_files:
        logger.info(f"  {f}")


def _select_env(work_dir: Path, config: TfDoConfig, is_interactive: bool) -> str:
    env_dirs = config.envs(work_dir)
    if not is_interactive:
        raise ValueError("run-dir command requires interactive mode")
    if not env_dirs:
        create = select_list("No envs found. Create the first env?", ["yes", "no"])
        if create == "no":
            raise typer.Exit(1)
        env_name = text("Env name")
        (config.env_base_dir(work_dir) / env_name).mkdir(parents=True, exist_ok=True)
        return env_name
    return select_list("Select env:", [d.name for d in env_dirs])


_LOCAL_SOURCE_PREFIXES = ("./", "../", "/")


def _ask_default_value(attr_name: str, current_display: str) -> str | None:
    if confirm(f"Set a default for var.{attr_name}?", default=True):
        return text(f"Default value for var.{attr_name}", default=current_display)
    return None


class _ModuleBuildResult(NamedTuple):
    config: ModuleRunDirConfig
    module_path: Path


class RawAttrsSelection(NamedTuple):
    attrs: dict[str, HclValue]
    configure_keys: frozenset[str]
    preserved_hcl: str | None


def _split_attrs_for_customize(
    raw_attrs: dict[str, HclValue], configure_keys: frozenset[str]
) -> tuple[dict[str, HclValue], list[tuple[str, HclValue]]]:
    passthrough: dict[str, HclValue] = {}
    customize: list[tuple[str, HclValue]] = []
    for attr_name, current_val in raw_attrs.items():
        if isinstance(current_val, dict | list):
            passthrough[attr_name] = current_val
        elif attr_name not in configure_keys:
            passthrough[attr_name] = current_val
        else:
            customize.append((attr_name, current_val))
    return passthrough, customize


def _scalar_attribute_keys(attrs: dict[str, HclValue]) -> frozenset[str]:
    return frozenset(name for name, val in attrs.items() if not isinstance(val, dict | list))


def _select_raw_attrs(mpath: Path, alias: str, source: str, registry_version: str | None) -> RawAttrsSelection:
    examples = parse_module_examples(mpath)
    choice = select_list(
        f"Configure module '{alias}':",
        ["configure manually"] + [e.name for e in examples],
    )
    if choice == "configure manually":
        module_attrs = _module_required_attrs(mpath)
        attr_choices: list[ChoiceTyped[str]] = [
            ChoiceTyped(name=f"required: {n}", value=n, checked=True) for n in module_attrs.required
        ] + [ChoiceTyped(name=f"optional: {n}", value=n, checked=False) for n in module_attrs.optional]
        selected_names: list[str] = (
            select_list_multiple_choices("Select attributes:", attr_choices, default=[]) if attr_choices else []
        )
        attrs: dict[str, HclValue] = {name: HclLiteral(value="") for name in selected_names}
        return RawAttrsSelection(attrs=attrs, configure_keys=frozenset(attrs), preserved_hcl=None)
    example = next(e for e in examples if e.name == choice)
    for entity in example.entities:
        if not isinstance(entity, TfModuleCall):
            continue
        if entity.source == source or entity.source.startswith(_LOCAL_SOURCE_PREFIXES):
            preserved = prepare_preserved_module_hcl(
                full_text=entity.file_path.read_text(),
                example_module_label=entity.name,
                run_dir_module_label=alias,
                registry_version=registry_version,
            )
            ex_attrs = dict(entity.attrs)
            scalar_sorted = sorted(_scalar_attribute_keys(ex_attrs))
            key_choices = [ChoiceTyped(name=k, value=k, checked=False) for k in scalar_sorted]
            picked: list[str] = (
                select_list_multiple_choices(
                    "Customize which module arguments? (none = keep example values):",
                    key_choices,
                    default=[],
                )
                if key_choices
                else []
            )
            return RawAttrsSelection(attrs=ex_attrs, configure_keys=frozenset(picked), preserved_hcl=preserved)
    return RawAttrsSelection(attrs={}, configure_keys=frozenset(), preserved_hcl=None)


def _build_module_config(
    provider_name: str,
    source: str,
    alias: str,
    settings,
    hints_registry: dict,
    constraint: str | None,
) -> _ModuleBuildResult:
    cache_version = constraint or module_cache.UNRESOLVED
    mpath = module_cache.lookup(settings.cache_root, source, cache_version)
    if mpath is None:
        mpath = module_cache.populate(settings.cache_root, source, cache_version, settings)
    mpath = module_cache.module_source_dir(mpath)

    selection = _select_raw_attrs(mpath, alias, source, constraint)
    raw_attrs = selection.attrs
    preserved_hcl = selection.preserved_hcl

    provider_hints = hints_registry.get(provider_name)
    auth_var_names = {vm.tf_var for vm in provider_hints.auth_variables} if provider_hints else set()

    promotions: list[AttrPromotion] = []
    passthrough, customize_attrs = _split_attrs_for_customize(raw_attrs, selection.configure_keys)
    resolved: dict[str, HclValue] = dict(passthrough)
    for attr_name, current_val in customize_attrs:
        current_display = _hcl_value_display(current_val)
        if attr_name in auth_var_names:
            default_val = _ask_default_value(attr_name, current_display)
            promotions.append(AttrPromotion(attr_name=attr_name, tf_var_name=attr_name, default_value=default_val))
            resolved[attr_name] = HclVarRef(path=f"var.{attr_name}")
            continue
        is_ref = isinstance(current_val, HclVarRef | HclAttrRef)
        choices = ["var_ref", "tf_var", "literal"] if is_ref else ["literal", "tf_var"]
        how = select_list(f"Set '{attr_name}' as:", choices)
        if how == "var_ref":
            resolved[attr_name] = current_val
        elif how == "tf_var":
            default_val = _ask_default_value(attr_name, current_display)
            promotions.append(AttrPromotion(attr_name=attr_name, tf_var_name=attr_name, default_value=default_val))
            resolved[attr_name] = HclVarRef(path=f"var.{attr_name}")
        else:
            literal_val = text(f"{attr_name}", default=current_display)
            resolved[attr_name] = HclLiteral(value=literal_val)

    final_attrs = {key: resolved[key] for key in raw_attrs}

    output_names = module_outputs(mpath)
    default_set = {n for n in output_names if n == "id" or n.endswith("_id")}
    output_choices = [ChoiceTyped(name=n, value=n, checked=n in default_set) for n in output_names]
    exposed: list[str] = (
        select_list_multiple_choices("Select outputs to expose:", output_choices, default=[]) if output_choices else []
    )

    config = ModuleRunDirConfig(
        source=source,
        label=alias,
        version=constraint,
        attrs=final_attrs,
        tf_var_promotions=promotions,
        exposed_outputs=exposed,
        preserved_module_hcl=preserved_hcl,
    )
    return _ModuleBuildResult(config, mpath)


def _run_dir_outputs(run_dir_path: Path) -> list[str]:
    return [e.name for e in parse_dir_entities(run_dir_path, recursive=False) if isinstance(e, TfOutput)]


def _wizard_dependencies(
    work_dir: Path, config: TfDoConfig, env_name: str, module_var_names: list[str]
) -> list[DependencyRef]:
    existing = config.run_dirs(work_dir, env_name)
    if not existing:
        return []
    dep_choices = [ChoiceTyped(name=rd.name, value=rd, checked=False) for rd in existing]
    selected_dirs: list[Path] = select_list_multiple_choices(
        "Does this run-dir depend on an existing one?", dep_choices, default=[]
    )
    deps: list[DependencyRef] = []
    for rd_path in selected_dirs:
        output_names = _run_dir_outputs(rd_path)
        if not output_names:
            logger.info(f"no outputs found in {rd_path.name}, skipping")
            continue
        out_choices = [ChoiceTyped(name=n, value=n, checked=True) for n in output_names]
        selected_outputs: list[str] = select_list_multiple_choices(
            f"Select outputs from '{rd_path.name}':", out_choices, default=[]
        )
        outputs: dict[str, str] = {}
        for out_name in selected_outputs:
            outputs[out_name] = _ask_local_var_name(out_name, module_var_names)
        deps.append(DependencyRef(ref=rd_path.name, outputs=outputs))
    return deps


def _ask_local_var_name(out_name: str, module_var_names: list[str]) -> str:
    if not module_var_names:
        return text(f"Local variable name for '{out_name}'", default=out_name)
    var_choices = [ChoiceTyped(name=n, value=n, checked=False) for n in module_var_names]
    new_handler = NewHandlerChoice(constructor=str, new_prompt=f"New variable name (default: {out_name})")
    options = SelectOptions(new_handler_choice=new_handler)
    return select_list_choice(
        f"Local variable name for '{out_name}':",
        var_choices,
        options=options,
    )


@new_app.command("run-dir")
def run_dir_cmd(ctx: typer.Context) -> None:
    """Scaffold a new run-dir with module calls, variables, and outputs."""
    settings = get_settings(ctx)
    work_dir = settings.work_dir
    config = load_config(work_dir) or TfDoConfig()

    env_name = _select_env(work_dir, config, settings.is_interactive)
    run_dir_name = text("Run-dir name")

    hints_registry = load_provider_hints(settings.resolved_provider_hints_path)
    provider_names = [pc.name for pc in config.providers]
    module_choices = available_module_choices(provider_names, hints_registry)

    selected: list[ModuleChoice] = (
        select_list_multiple_choices("Select modules:", module_choices, default=[]) if module_choices else []
    )

    constraints_by_source = {m.source: m.constraint for m in config.modules}
    build_results = [
        _build_module_config(
            mc.provider,
            mc.hint.source,
            mc.hint.alias,
            settings,
            hints_registry,
            constraints_by_source.get(mc.hint.source),
        )
        for mc in selected
    ]

    module_var_names = sorted(
        {attr_name for br in build_results for attr_name, val in br.config.attrs.items() if isinstance(val, HclVarRef)}
    )
    dependencies = _wizard_dependencies(work_dir, config, env_name, module_var_names)

    dep_local_vars = {v for dep in dependencies for v in dep.outputs.values()}
    for br in build_results:
        if not dep_local_vars:
            break
        required = set(_module_required_attrs(br.module_path).required)
        for var_name in dep_local_vars & required:
            if var_name not in br.config.attrs:
                br.config.attrs[var_name] = HclVarRef(path=f"var.{var_name}")

    module_configs = [br.config for br in build_results]

    result = new_run_dir(
        NewRunDirInput(
            settings=settings,
            config=config,
            env_name=env_name,
            run_dir_name=run_dir_name,
            module_configs=module_configs,
            dependencies=dependencies,
        )
    )
    logger.info(f"New run-dir created at {result.run_dir}. Run `tfdo check` to ensure it is ready!")
