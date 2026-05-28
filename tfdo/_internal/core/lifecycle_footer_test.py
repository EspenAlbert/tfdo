from pathlib import Path
from unittest.mock import patch

from tfdo._internal.core import binary, lifecycle_env, lifecycle_footer
from tfdo._internal.output import plan_artifacts
from tfdo._internal.output.plan_display import DetailLevel
from tfdo._internal.settings import TfDoSettings


def test_lifecycle_footer_lines_includes_artifacts_and_debug_log(tmp_path: Path) -> None:
    settings = TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)
    bin_path = plan_artifacts.plan_bin_path(tmp_path)
    bin_path.parent.mkdir(parents=True)
    bin_path.write_bytes(b"plan")
    plan_artifacts.plan_json_path(tmp_path).write_text("{}")

    with patch(f"{binary.__name__}.{binary.resolve_binary.__name__}", return_value="terraform"):
        lines = lifecycle_footer.lifecycle_footer_lines(settings, detail=DetailLevel.COMPACT)

    joined = "\n".join(lines)
    assert "Full plan:" in joined
    assert "Plan JSON:" in joined
    assert "Debug log:" in joined
    assert str(lifecycle_env.resolved_debug_log_path(tmp_path)) in joined
    assert "More depth:" in joined


def test_lifecycle_footer_lines_uses_custom_tf_log_path(tmp_path: Path, monkeypatch) -> None:
    custom_path = tmp_path / "custom-debug.log"
    monkeypatch.setenv("TF_LOG_PATH", str(custom_path))
    settings = TfDoSettings.for_testing(tmp_path, work_dir=tmp_path)

    lines = lifecycle_footer.lifecycle_footer_lines(settings, detail=DetailLevel.COMPACT)

    assert str(custom_path.resolve()) in "\n".join(lines)
