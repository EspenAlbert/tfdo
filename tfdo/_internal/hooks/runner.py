from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Callable

from tfdo._internal.config.config_model import HookConfig
from tfdo._internal.hooks.models import ExitEvent, HookEffect, HookInput, InputModification, RetryEvent

logger = logging.getLogger(__name__)

_HOOK_EFFECT_TYPES = (ExitEvent, InputModification, RetryEvent)


class LocalHookRunner:
    def __init__(self, run_dir: Path) -> None:
        self._run_dir = run_dir

    def wrap(self, config: HookConfig) -> Callable[[HookInput], HookEffect | None]:
        if config.cmd:
            return self._wrap_cmd(config)
        if config.py_locate:
            return self._wrap_py_locate(config)
        raise ValueError(f"hook '{config.name}' has neither cmd nor py_locate")

    def _wrap_cmd(self, config: HookConfig) -> Callable[[HookInput], HookEffect | None]:
        from ask_shell.shell import run_and_wait

        cmd = config.cmd
        timeout = config.timeout_seconds
        run_dir = self._run_dir

        def _run(hook_input: HookInput) -> HookEffect | None:
            run_and_wait(
                cmd,
                timeout=timeout,
                cwd=run_dir,
                env=dict(hook_input.env_vars),
                allow_non_zero_exit=False,
                skip_binary_check=True,
            )
            return None

        return _run

    def _wrap_py_locate(self, config: HookConfig) -> Callable[[HookInput], HookEffect | None]:
        assert config.py_locate is not None
        dotted = config.py_locate
        last_dot = dotted.rfind(".")
        if last_dot == -1:
            raise ValueError(f"py_locate '{dotted}' must be a dotted path (module.function)")
        module_path, attr_name = dotted[:last_dot], dotted[last_dot + 1 :]
        try:
            mod = importlib.import_module(module_path)
        except ModuleNotFoundError as e:
            raise ValueError(f"py_locate module '{module_path}' not found") from e
        fn = getattr(mod, attr_name, None)
        if fn is None:
            raise ValueError(f"py_locate attribute '{attr_name}' not found in '{module_path}'")
        if not callable(fn):
            raise ValueError(f"py_locate '{dotted}' is not callable")

        params = inspect.signature(fn).parameters
        accepts_input = len(params) >= 1

        def _run(hook_input: HookInput) -> HookEffect | None:
            from tfdo._internal.hooks.execution import _hook_env

            _hook_env.set(dict(hook_input.env_vars))
            result = fn(hook_input) if accepts_input else fn()
            if result is None:
                return None
            if isinstance(result, _HOOK_EFFECT_TYPES):
                return result
            logger.warning(f"py_locate hook '{dotted}' returned unexpected type {type(result).__name__}, ignoring")
            return None

        return _run
