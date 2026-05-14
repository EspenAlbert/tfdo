from __future__ import annotations

import logging
from pathlib import Path

import typer
from ask_shell._internal.interactive import ChoiceTyped, select_list_multiple_choices

from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.copy.copy_env import (
    CopyEnvInput,
    DstEnvExistsError,
    ModuleCallEdit,
    ResourceEdit,
    SrcEnvNotFoundError,
    copy_env,
)
from tfdo._internal.hcl_entity_parser import TfModuleCall, TfResource, parse_dir_entities
from tfdo._internal.hcl_example_prompt import ask_field_edits
from tfdo._internal.typer_app import app, get_settings

logger = logging.getLogger(__name__)

copy_app = typer.Typer(help="Copy tfdo-managed environments")
app.add_typer(copy_app, name="copy")


def _entity_choices(src_dir, run_dir_name: str) -> list[ChoiceTyped]:
    choices: list[ChoiceTyped] = []
    for e in parse_dir_entities(src_dir / run_dir_name):
        if isinstance(e, TfModuleCall):
            choices.append(ChoiceTyped(name=f"module:{e.name}", value=e, checked=False))
        elif isinstance(e, TfResource):
            choices.append(ChoiceTyped(name=f"resource:{e.type}.{e.name}", value=e, checked=False))
    return choices


def _entity_to_edit(run_dir_name: str, original, edited) -> ModuleCallEdit | ResourceEdit | None:
    if edited is original:
        return None
    changed = {k: v for k, v in edited.attrs.items() if original.attrs.get(k) != v}
    if not changed:
        return None
    if isinstance(original, TfModuleCall) and isinstance(edited, TfModuleCall):
        return ModuleCallEdit(run_dir=run_dir_name, module_name=original.name, attrs=changed)
    if isinstance(original, TfResource) and isinstance(edited, TfResource):
        return ResourceEdit(
            run_dir=run_dir_name,
            resource_type=original.type,
            resource_name=original.name,
            attrs=changed,
        )
    return None


def _collect_interactive_input(
    src_dir: Path, config: TfDoConfig, work_dir: Path
) -> tuple[list[str], list[ModuleCallEdit | ResourceEdit]]:
    run_dir_names = [p.name for p in config.run_dirs(work_dir, src_dir.name)]
    all_choices = [ChoiceTyped(name=n, value=n, checked=True) for n in run_dir_names]
    selected: list[str] = select_list_multiple_choices(
        "Select run-dirs to copy:", all_choices, default=[c.value for c in all_choices]
    )

    edit_choices = [ChoiceTyped(name=n, value=n, checked=False) for n in selected]
    to_edit: list[str] = select_list_multiple_choices(
        "Edit attributes in copied run-dirs? (none = straight clone):", edit_choices, default=[]
    )

    edits: list[ModuleCallEdit | ResourceEdit] = []
    for run_dir_name in to_edit:
        chosen = select_list_multiple_choices(
            f"[{run_dir_name}] Select entities to edit:",
            _entity_choices(src_dir, run_dir_name),
            default=[],
        )
        for entity in chosen:
            edited_list, original_list = ask_field_edits([entity])
            edit = _entity_to_edit(run_dir_name, original_list[0], edited_list[0])
            if edit:
                edits.append(edit)

    return selected, edits


@copy_app.command("env")
def env_cmd(
    ctx: typer.Context,
    src: str = typer.Option(..., "--from", help="Source env name"),
    dst: str = typer.Option(..., "--to", help="Destination env name"),
) -> None:
    """Copy a tfdo-managed environment."""
    settings = get_settings(ctx)
    work_dir = settings.work_dir
    config = load_config(work_dir) or TfDoConfig()
    src_dir = config.env_base_dir(work_dir) / src

    if settings.is_interactive:
        selected_run_dirs, edits = _collect_interactive_input(src_dir, config, work_dir)
    else:
        selected_run_dirs = [p.name for p in config.run_dirs(work_dir, src)]
        edits = []

    try:
        copy_env(
            CopyEnvInput(
                settings=settings,
                config=config,
                src_env=src,
                dst_env=dst,
                selected_run_dirs=selected_run_dirs,
                edits=edits,
            )
        )
    except (SrcEnvNotFoundError, DstEnvExistsError) as e:
        logger.error(str(e))
        raise typer.Exit(1)
