from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

_orchestration_print_lock: ContextVar[Lock | None] = ContextVar(
    "tfdo_orchestration_print_lock",
    default=None,
)


@contextmanager
def orchestration_print_scope(lock: Lock):
    token = _orchestration_print_lock.set(lock)
    try:
        yield
    finally:
        _orchestration_print_lock.reset(token)


def orchestration_print_lock() -> Lock | None:
    return _orchestration_print_lock.get()
