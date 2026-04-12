from __future__ import annotations

from pathlib import Path

from tfdo._internal.config.scan import _infer_pattern, scan_for_run_dirs

TF_BACKEND = 'terraform {\n  backend "s3" {\n    bucket = "test"\n  }\n}\n'


def test_infer_pattern_envs_apps():
    paths = ["envs/dev/api", "envs/dev/web", "envs/staging/api", "envs/staging/web"]
    assert _infer_pattern(paths) == "envs/{env}/{app}"


def test_infer_pattern_single_variable():
    paths = ["apps/api", "apps/web"]
    assert _infer_pattern(paths) == "apps/{app}"


def test_infer_pattern_returns_none_for_mixed_depths():
    paths = ["envs/dev/api", "standalone"]
    assert _infer_pattern(paths) is None


def test_infer_pattern_returns_none_for_single_path():
    assert _infer_pattern(["envs/dev/api"]) is None


def test_scan_for_run_dirs(tmp_path: Path):
    for rd in ["envs/dev/api", "envs/staging/web"]:
        d = tmp_path / rd
        d.mkdir(parents=True)
        (d / "main.tf").write_text(TF_BACKEND)
    (tmp_path / ".git").mkdir()

    result = scan_for_run_dirs(tmp_path)
    assert len(result.directories) == 2
    assert result.inferred_pattern == "envs/{env}/{app}"


def test_scan_skips_hidden_dirs(tmp_path: Path):
    hidden = tmp_path / ".terraform" / "modules"
    hidden.mkdir(parents=True)
    (hidden / "main.tf").write_text(TF_BACKEND)

    result = scan_for_run_dirs(tmp_path)
    assert result.directories == []
