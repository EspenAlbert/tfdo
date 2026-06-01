from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

_orchestration_print_lock: ContextVar[Lock | None] = ContextVar(
    "tfdo_orchestration_print_lock",
    default=None,
)
_orch_dir_blocks = 0


def reset_orchestration_dir_blocks() -> None:
    """Reset per-run directory block count when orchestration display starts."""
    global _orch_dir_blocks
    _orch_dir_blocks = 0


def orchestration_dir_block_separator() -> bool:
    """Return True before the 2nd+ orchestration plan block so callers can insert a blank line."""
    global _orch_dir_blocks
    separator = _orch_dir_blocks > 0
    _orch_dir_blocks += 1
    return separator


@contextmanager
def orchestration_print_scope(lock: Lock):
    token = _orchestration_print_lock.set(lock)
    try:
        yield
    finally:
        _orchestration_print_lock.reset(token)


def orchestration_print_lock() -> Lock | None:
    return _orchestration_print_lock.get()
