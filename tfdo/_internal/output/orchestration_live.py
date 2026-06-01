from __future__ import annotations

import time
from threading import Lock
from typing import Protocol

from ask_shell import console as ask_console
from ask_shell.console import RemoveLivePart
from rich.console import Console, ConsoleOptions, RenderResult

from tfdo._internal.output import orchestration_renderer as renderer
from tfdo._internal.output.orchestration_state import OrchestrationProgressState

ORCHESTRATION_LIVE_ORDER = -110
ORCHESTRATION_RENDERABLE_NAME = "orchestration-status"


class _OrchestrationLiveHost(Protocol):
    _lock: Lock
    state: OrchestrationProgressState


class OrchestrationStatusRenderable:
    def __init__(self, display: _OrchestrationLiveHost) -> None:
        self._display = display

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        with self._display._lock:
            state = self._display.state
            now = time.monotonic()
            yield renderer.render_orchestration_live_header(state)
            yield renderer.build_wave_progress(state, now=now)


def register_orchestration_live(display: _OrchestrationLiveHost) -> RemoveLivePart:
    return ask_console.add_renderable(
        OrchestrationStatusRenderable(display),
        name=ORCHESTRATION_RENDERABLE_NAME,
        order=ORCHESTRATION_LIVE_ORDER,
    )
