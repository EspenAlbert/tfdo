from tfdo._internal.output.apply_live_mode import ApplyLiveMode, resolve_apply_live_mode


def test_resolve_apply_live_mode_single_dir() -> None:
    assert resolve_apply_live_mode(orchestration_active=False, parallel=10, interactive=True) == ApplyLiveMode.FULL


def test_resolve_apply_live_mode_orchestration_parallel_thresholds() -> None:
    assert resolve_apply_live_mode(orchestration_active=True, parallel=4, interactive=True) == ApplyLiveMode.FULL
    assert resolve_apply_live_mode(orchestration_active=True, parallel=5, interactive=True) == ApplyLiveMode.COMPACT
