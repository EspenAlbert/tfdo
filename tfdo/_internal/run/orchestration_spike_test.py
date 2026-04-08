"""Spike test: validate run_pool wave-based execution with stdout capture.

Proves that:
1. run_pool + run_and_wait captures stdout per run via ShellRun.stdout
2. Wave-based execution (sequential run_pool contexts) preserves ordering
3. skip_progress_output suppresses live Rich progress without losing stdout
"""

import time
from concurrent.futures import Future

from ask_shell.shell import ShellRun, run_and_wait, run_pool


def _run_echo(message: str, *, skip_progress: bool = False) -> ShellRun:
    return run_and_wait(
        f"echo '{message}'",
        skip_progress_output=skip_progress,
        skip_binary_check=True,
    )


def test_run_pool_captures_stdout_per_run():
    messages = ["alpha", "bravo", "charlie"]
    futures: list[Future[ShellRun]] = []

    with run_pool(task_name="stdout-capture", total=len(messages), max_concurrent_submits=3) as pool:
        for msg in messages:
            futures.append(pool.submit(_run_echo, msg))

    results = [f.result() for f in futures]
    captured = [r.stdout for r in results]
    assert captured == messages


def test_wave_ordering():
    """Wave 0 must complete before wave 1 starts.

    Note: max_concurrent_submits must be >= 2 because run_pool increments
    the submit counter before the while-loop check, so 1 would deadlock.
    """
    wave_0_end: float = 0
    wave_1_start: float = 0

    def wave_0_task(label: str) -> tuple[str, float]:
        run = run_and_wait(f"echo '{label}'", skip_binary_check=True)
        return run.stdout, time.monotonic()

    def wave_1_task(label: str) -> tuple[str, float]:
        nonlocal wave_1_start
        wave_1_start = time.monotonic()
        run = run_and_wait(f"echo '{label}'", skip_binary_check=True)
        return run.stdout, time.monotonic()

    with run_pool(task_name="wave-0", total=2, max_concurrent_submits=2) as pool:
        w0_futures = [pool.submit(wave_0_task, f"w0-{i}") for i in range(2)]
    wave_0_end = max(f.result()[1] for f in w0_futures)

    with run_pool(task_name="wave-1", total=1, max_concurrent_submits=2) as pool:
        w1_futures = [pool.submit(wave_1_task, "w1-0")]
    w1_stdout = w1_futures[0].result()[0]

    assert wave_1_start >= wave_0_end
    assert w1_stdout == "w1-0"


def test_skip_progress_output_still_captures_stdout():
    run = _run_echo("quiet-run", skip_progress=True)
    assert run.stdout == "quiet-run"
    assert run.exit_code == 0
