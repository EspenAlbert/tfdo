from __future__ import annotations

import contextvars
import threading

from tfdo._internal.output.orchestration_print import orchestration_print_lock, orchestration_print_scope


def test_orchestration_print_scope_serializes_whole_blocks() -> None:
    lock = threading.Lock()
    lines: list[str] = []

    def worker(tag: str) -> None:
        active = orchestration_print_lock()
        assert active is not None
        assert active is lock
        with active:
            for i in range(3):
                lines.append(f"{tag}-{i}")

    with orchestration_print_scope(lock):
        ctx = contextvars.copy_context()
        threads = [threading.Thread(target=ctx.run, args=(worker, f"t{n}")) for n in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert orchestration_print_lock() is None
    assert lines[:3] == ["t0-0", "t0-1", "t0-2"] or lines[:3] == ["t1-0", "t1-1", "t1-2"]
    assert lines[3:6] == ["t1-0", "t1-1", "t1-2"] or lines[3:6] == ["t0-0", "t0-1", "t0-2"]


def test_render_plan_holds_lock_until_tree_finishes(create_flat_plan) -> None:
    from unittest.mock import patch

    from ask_shell import console as ask_console

    from tfdo._internal.output.conftest import build_attr_lines_by_addr
    from tfdo._internal.output.parser import parse_plan_file
    from tfdo._internal.output.plan_renderer import render_plan
    from tfdo._internal.output.tree_builder import build_plan_tree

    plan = parse_plan_file(create_flat_plan)
    tree = build_plan_tree(plan)
    attr_lines = build_attr_lines_by_addr(tree, plan=plan)
    printed: list[str] = []
    lock = threading.Lock()
    gate = threading.Event()
    proceed = threading.Event()

    def slow_print(*args: object, **_kwargs: object) -> None:
        printed.append(str(args[0]) if args else "")
        if len(printed) == 1:
            gate.set()
            proceed.wait(timeout=2.0)

    def render_in_thread() -> None:
        render_plan(tree, attr_lines, terminal_width=120, run_dir_key="envs/a")

    with orchestration_print_scope(lock):
        ctx = contextvars.copy_context()
        with patch.object(ask_console, "print_to_live", side_effect=slow_print):
            thread = threading.Thread(target=ctx.run, args=(render_in_thread,))
            thread.start()
            assert gate.wait(timeout=2.0)
            with lock:
                printed.append("INTRUDER")
            proceed.set()
            thread.join(timeout=2.0)

    assert str(printed[0]) == "envs/a"
    assert str(printed[1]).startswith("📋 Plan:")
    intruder_index = printed.index("INTRUDER")
    assert intruder_index > 0
    assert any("local_file" in line for line in printed[1:intruder_index])
