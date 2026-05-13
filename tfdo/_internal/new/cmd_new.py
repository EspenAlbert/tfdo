from __future__ import annotations

import logging

import typer
from ask_shell._internal.interactive import ChoiceTyped, select_list, select_list_multiple_choices, text

from tfdo._internal.cache import module_cache
from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.config.provider_hints import load_provider_hints
from tfdo._internal.hcl_entity_parser import TfModuleCall, parse_module_examples
from tfdo._internal.hcl_example_prompt import _hcl_value_display
from tfdo._internal.hcl_roundtrip import HclLiteral, HclVarRef
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


def _select_env(work_dir, is_interactive: bool) -> str:
    envs_dir = work_dir / "envs"
    env_dirs = sorted(envs_dir.glob("*/")) if envs_dir.is_dir() else []
    if not is_interactive:
        raise ValueError("run-dir command requires interactive mode")
    if not env_dirs:
        create = select_list("No envs found. Create the first env?", ["yes", "no"])
        if create == "no":
            raise typer.Exit(1)
        env_name = text("Env name")
        (work_dir / "envs" / env_name).mkdir(parents=True, exist_ok=True)
        return env_name
    return select_list("Select env:", [d.name for d in env_dirs])


def _build_module_config(
    provider_name: str,
    source: str,
    alias: str,
    settings,
    hints_registry: dict,
) -> ModuleRunDirConfig:
    mpath = module_cache.lookup(settings.cache_root, source, module_cache.UNRESOLVED)
    if mpath is None:
        mpath = module_cache.populate(settings.cache_root, source, module_cache.UNRESOLVED, settings)

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
        raw_attrs = {name: HclLiteral("") for name in selected_names}
    else:
        example = next(e for e in examples if e.name == choice)
        raw_attrs = {}
        for entity in example.entities:
            if isinstance(entity, TfModuleCall) and entity.source == source:
                raw_attrs = dict(entity.attrs)
                break

    provider_hints = hints_registry.get(provider_name)
    auth_var_names = {vm.tf_var for vm in provider_hints.auth_variables} if provider_hints else set()

    promotions: list[AttrPromotion] = []
    final_attrs = {}
    for attr_name, current_val in raw_attrs.items():
        is_complex = isinstance(current_val, dict | list)
        if is_complex:
            final_attrs[attr_name] = current_val
            continue
        current_display = _hcl_value_display(current_val)
        if attr_name in auth_var_names:
            default_val = text(f"Default value for '{attr_name}'", default=current_display)
            promotions.append(AttrPromotion(attr_name=attr_name, tf_var_name=attr_name, default_value=default_val))
            final_attrs[attr_name] = HclVarRef(f"var.{attr_name}")
        else:
            how = select_list(f"Set '{attr_name}' as:", ["literal", "tf_var"])
            if how == "tf_var":
                default_val = text(f"Default value for var.{attr_name}", default=current_display)
                promotions.append(AttrPromotion(attr_name=attr_name, tf_var_name=attr_name, default_value=default_val))
                final_attrs[attr_name] = HclVarRef(f"var.{attr_name}")
            else:
                literal_val = text(f"{attr_name}", default=current_display)
                final_attrs[attr_name] = HclLiteral(literal_val)

    output_names = module_outputs(mpath)
    default_set = {n for n in output_names if n == "id" or n.endswith("_id")}
    output_choices = [ChoiceTyped(name=n, value=n, checked=n in default_set) for n in output_names]
    exposed: list[str] = (
        select_list_multiple_choices("Select outputs to expose:", output_choices, default=[]) if output_choices else []
    )

    return ModuleRunDirConfig(
        source=source,
        label=alias,
        attrs=final_attrs,
        tf_var_promotions=promotions,
        exposed_outputs=exposed,
    )


@new_app.command("run-dir")
def run_dir_cmd(ctx: typer.Context) -> None:
    """Scaffold a new run-dir with module calls, variables, and outputs."""
    settings = get_settings(ctx)
    work_dir = settings.work_dir
    config = load_config(work_dir) or TfDoConfig()

    env_name = _select_env(work_dir, settings.is_interactive)
    run_dir_name = text("Run-dir name")

    hints_registry = load_provider_hints(settings.resolved_provider_hints_path)
    module_choices: list[ChoiceTyped[tuple[str, str, str]]] = []
    for pc in config.providers:
        hints = hints_registry.get(pc.name)
        if not hints or not hints.modules:
            continue
        for mhint in hints.modules:
            module_choices.append(
                ChoiceTyped(name=f"{pc.name}: {mhint.alias}", value=(pc.name, mhint.source, mhint.alias), checked=False)
            )

    selected: list[tuple[str, str, str]] = (
        select_list_multiple_choices("Select modules:", module_choices, default=[]) if module_choices else []
    )

    module_configs = [
        _build_module_config(provider_name, source, alias, settings, hints_registry)
        for provider_name, source, alias in selected
    ]

    result = new_run_dir(
        NewRunDirInput(
            settings=settings,
            config=config,
            env_name=env_name,
            run_dir_name=run_dir_name,
            module_configs=module_configs,
        )
    )
    logger.info(f"New run-dir created at {result.run_dir}. Run `tfdo check` to ensure it is ready!")
