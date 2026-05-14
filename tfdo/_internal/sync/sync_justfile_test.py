from __future__ import annotations

from pathlib import Path

import pytest
from zero_3rdparty.sections import CommentConfig, extract_sections

from tfdo._internal.settings import TfDoSettings
from tfdo._internal.sync.sync_justfile import (
    SECTION_ID,
    TOOL_NAME,
    SyncJustfileInput,
    sync_justfile,
)

_COMMENT = CommentConfig("#")


def _settings(tmp_path: Path) -> TfDoSettings:
    return TfDoSettings(work_dir=tmp_path)


def _make_env_dirs(tmp_path: Path, layout: dict[str, list[str]]) -> None:
    """layout: {env_name: [run_dir_names]}. Empty list = env dir only."""
    for env, run_dirs in layout.items():
        if run_dirs:
            for rd in run_dirs:
                (tmp_path / "envs" / env / rd).mkdir(parents=True)
        else:
            (tmp_path / "envs" / env).mkdir(parents=True)


def _section(justfile_path: Path) -> str:
    return extract_sections(justfile_path.read_text(), TOOL_NAME, _COMMENT).get(SECTION_ID, "")


def test_env_only_targets(tmp_path: Path) -> None:
    _make_env_dirs(tmp_path, {"dev": [], "prod": []})
    result = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))

    assert result.target_names == ["dev", "prod"]
    section = _section(result.justfile_path)
    assert "dev cmd *args:" in section
    assert "prod cmd *args:" in section
    assert "tfdo run --env dev {{cmd}}" in section
    assert "tfdo run --env prod {{cmd}}" in section


def test_run_dir_targets_use_app_flag(tmp_path: Path) -> None:
    _make_env_dirs(tmp_path, {"dev": ["networking", "app"]})
    result = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))

    assert result.target_names == ["dev-app", "dev-networking"]
    section = _section(result.justfile_path)
    assert "dev-networking cmd *args:" in section
    assert "--env dev --app networking" in section
    assert "dev-app cmd *args:" in section
    assert "--env dev --app app" in section


def test_second_run_is_idempotent(tmp_path: Path) -> None:
    _make_env_dirs(tmp_path, {"dev": [], "prod": []})
    sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    first = (tmp_path / "justfile").read_text()

    result2 = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    assert not result2.section_updated
    assert (tmp_path / "justfile").read_text() == first


def test_user_content_outside_markers_preserved(tmp_path: Path) -> None:
    preamble = 'set shell := ["bash", "-cu"]\n\ndefault:\n    just --list\n'
    justfile = tmp_path / "justfile"
    justfile.write_text(preamble)
    _make_env_dirs(tmp_path, {"dev": []})

    sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    content = justfile.read_text()
    assert content.startswith(preamble)

    sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    assert justfile.read_text() == content


@pytest.mark.parametrize("layout,expected", [({}, []), ({"staging": []}, ["staging"])])
def test_no_envs_produces_empty_targets(tmp_path: Path, layout: dict, expected: list) -> None:
    _make_env_dirs(tmp_path, layout)
    result = sync_justfile(SyncJustfileInput(settings=_settings(tmp_path)))
    assert result.target_names == expected
