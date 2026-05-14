from __future__ import annotations

from pathlib import Path

import pytest
from zero_3rdparty.sections import CommentConfig, extract_sections

from tfdo._internal.settings import TfDoSettings
from tfdo._internal.sync.sync_justfile import (
    SECTION_ID,
    TOOL_NAME,
    SyncJustfileInput,
    SyncTargetGroup,
    sync_justfile,
)

_COMMENT = CommentConfig("#")


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings(work_dir=tmp_path)


def _make_env_dirs(tmp_path: Path, envs: list[str]) -> None:
    for env in envs:
        (tmp_path / "envs" / env).mkdir(parents=True)


def _extract_ci_section(content: str) -> str:
    return extract_sections(content, TOOL_NAME, _COMMENT).get(SECTION_ID, "")


def test_two_envs_generates_all_targets(tmp_path: Path) -> None:
    _make_env_dirs(tmp_path, ["dev", "prod"])
    result = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))

    assert result.env_names == ["dev", "prod"]
    assert result.section_updated
    content = result.justfile_path.read_text()
    for verb in ("plan", "apply", "destroy", "init"):
        assert f"{verb}-env env:" in content
        assert f"tfdo run --env {{{{env}}}} {verb}" in content


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    _make_env_dirs(tmp_path, ["dev"])
    sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    first = (tmp_path / "justfile").read_text()

    result2 = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    assert not result2.section_updated
    assert (tmp_path / "justfile").read_text() == first


def test_user_content_outside_markers_preserved(tmp_path: Path) -> None:
    preamble = 'set shell := ["bash", "-cu"]\n\ndefault:\n    just --list\n'
    justfile = tmp_path / "justfile"
    justfile.write_text(preamble)

    sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    content = justfile.read_text()
    assert content.startswith(preamble)

    sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    assert justfile.read_text() == content


def test_deselecting_group_omits_target(tmp_path: Path) -> None:
    selected = [SyncTargetGroup.PLAN, SyncTargetGroup.APPLY]
    result = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path), selected_groups=selected))
    section = _extract_ci_section(result.justfile_path.read_text())
    assert "plan-env" in section
    assert "apply-env" in section
    assert "destroy-env" not in section
    assert "init-env" not in section


@pytest.mark.parametrize("env_dirs,expected", [([], []), (["staging"], ["staging"])])
def test_env_discovery(tmp_path: Path, env_dirs: list[str], expected: list[str]) -> None:
    _make_env_dirs(tmp_path, env_dirs)
    result = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    assert result.env_names == expected
