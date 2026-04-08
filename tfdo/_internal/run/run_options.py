import typer


def env_option() -> str | None:
    return typer.Option(None, "--env", help="Filter by {env} selector from discovery pattern")


def app_option() -> str | None:
    return typer.Option(None, "--app", help="Filter by {app} selector from discovery pattern")


def tags_option() -> list[str]:
    return typer.Option([], "--tags", help="Tag filter as key=value (repeatable, AND logic)")


def parallel_option() -> int:
    return typer.Option(10, "--parallel", min=1, help="Max concurrent run_dir executions per wave")


def on_failure_option() -> str:
    return typer.Option("stop", "--on-failure", help="Failure behavior: stop (abort remaining), continue (run all)")


def dry_run_option() -> bool:
    return typer.Option(False, "--dry-run", help="Print resolved commands per run_dir without executing")
