from pathlib import Path

import typer
from pydantic import BaseModel, Field

from tfdo._internal import cmd_options
from tfdo._internal.config.config_file import load_config
from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.models import InitMode
from tfdo._internal.run import orchestration, run_options
from tfdo._internal.run.orchestration import FailureMode, LifecycleCommand, RunOrchestrationInput
from tfdo._internal.settings import TfDoSettings
from tfdo._internal.typer_app import app, get_settings


class RunContext(BaseModel):
    settings: TfDoSettings
    selector_filters: dict[str, str] = Field(default_factory=dict)
    tag_filters: list[str] = Field(default_factory=list)
    parallel: int = 10
    on_failure: FailureMode = FailureMode.STOP
    dry_run: bool = False
    changed: bool = False

    def build_input(self, command: LifecycleCommand, **kwargs) -> RunOrchestrationInput:
        return RunOrchestrationInput(
            settings=self.settings,
            command=command,
            parallel=self.parallel,
            on_failure=self.on_failure,
            dry_run=self.dry_run,
            changed=self.changed,
            selector_filters=self.selector_filters,
            tag_filters=self.tag_filters,
            **kwargs,
        )


def _get_run_context(ctx: typer.Context) -> RunContext:
    run_ctx: RunContext = ctx.obj
    return run_ctx


run_app = typer.Typer(name="run", help="Run lifecycle commands across multiple run directories")
app.add_typer(run_app, name="run")


@run_app.callback()
def run_callback(
    ctx: typer.Context,
    env: str | None = run_options.env_option(),
    app_name: str | None = run_options.app_option(),
    team: str | None = run_options.team_option(),
    tags: list[str] = run_options.tags_option(),
    changed: bool = run_options.changed_option(),
    parallel: int = run_options.parallel_option(),
    on_failure: FailureMode = run_options.on_failure_option(),
    dry_run: bool = run_options.dry_run_option(),
) -> None:
    parent_settings = get_settings(ctx)
    config = load_config(parent_settings.work_dir) or TfDoConfig()
    selector_filters: dict[str, str] = {}
    if env:
        selector_filters["env"] = env
    if app_name:
        names = config.selector_names
        app_selector = names[1] if len(names) >= 2 else "app"
        selector_filters[app_selector] = app_name
    if team:
        selector_filters["team"] = team
    ctx.obj = RunContext(
        settings=parent_settings,
        selector_filters=selector_filters,
        tag_filters=tags,
        parallel=parallel,
        on_failure=on_failure,
        dry_run=dry_run,
        changed=changed,
    )


@run_app.command("init")
def run_init_cmd(
    ctx: typer.Context,
    extra_args: list[str] | None = typer.Option(
        None, "--extra-args", help="Extra arguments forwarded to terraform init (e.g. --extra-args=-upgrade)"
    ),
) -> None:
    """Run init across multiple run directories."""
    run_ctx = _get_run_context(ctx)
    inp = run_ctx.build_input(LifecycleCommand.INIT, extra_flags=extra_args or [])
    result = orchestration.run_orchestration(inp)
    raise typer.Exit(result.exit_code)


@run_app.command("plan")
@run_app.command("p")
def run_plan_cmd(
    ctx: typer.Context,
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
    out: Path | None = typer.Option(None, "-o", "--out", help="Write plan output to file (per run directory)"),
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
) -> None:
    """Run plan across multiple run directories."""
    extra_flags: list[str] = []
    if out:
        extra_flags.append(f"-out={out}")
    if json_output:
        extra_flags.append("-json")
    run_ctx = _get_run_context(ctx)
    inp = run_ctx.build_input(LifecycleCommand.PLAN, var_file=var_file, init_mode=init_mode, extra_flags=extra_flags)
    result = orchestration.run_orchestration(inp)
    raise typer.Exit(result.exit_code)


@run_app.command("apply")
@run_app.command("a")
def run_apply_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
) -> None:
    """Run apply across multiple run directories."""
    run_ctx = _get_run_context(ctx)
    inp = run_ctx.build_input(LifecycleCommand.APPLY, auto_approve=auto_approve, var_file=var_file, init_mode=init_mode)
    result = orchestration.run_orchestration(inp)
    raise typer.Exit(result.exit_code)


@run_app.command("destroy")
@run_app.command("d")
def run_destroy_cmd(
    ctx: typer.Context,
    auto_approve: bool = cmd_options.auto_approve_option(),
    var_file: Path | None = cmd_options.var_file_option(),
    init_mode: InitMode = cmd_options.init_mode_option(),
) -> None:
    """Run destroy across multiple run directories."""
    run_ctx = _get_run_context(ctx)
    inp = run_ctx.build_input(
        LifecycleCommand.DESTROY, auto_approve=auto_approve, var_file=var_file, init_mode=init_mode
    )
    result = orchestration.run_orchestration(inp)
    raise typer.Exit(result.exit_code)
