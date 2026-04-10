import typer

from tfdo._internal.run.orchestration import DEFAULT_PARALLEL, FailureMode


def env_option() -> str | None:
    return typer.Option(None, "--env", help="Filter run directories by {env} selector from discovery pattern")


def app_option() -> str | None:
    return typer.Option(None, "--app", help="Filter run directories by {app} selector from discovery pattern")


def tags_option() -> list[str]:
    return typer.Option(
        [], "--tags", help="Tag filter as key=value, repeatable with AND logic (e.g. --tags env=dev --tags team=infra)"
    )


def parallel_option() -> int:
    return typer.Option(DEFAULT_PARALLEL, "--parallel", min=1, help="Max concurrent run directory executions per wave")


def on_failure_option() -> FailureMode:
    return typer.Option(
        FailureMode.STOP, "--on-failure", help="Failure behavior: stop aborts remaining directories, continue runs all"
    )


def dry_run_option() -> bool:
    return typer.Option(
        False, "--dry-run", help="Show execution plan (waves and run directories) without running terraform"
    )
