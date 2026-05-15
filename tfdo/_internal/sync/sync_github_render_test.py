from __future__ import annotations

from tfdo._internal.config.config_model import TfDoConfig
from tfdo._internal.sync.sync_github import _render_manual_workflow


def test_manual_workflow_maps_secrets_and_vars_to_job_env() -> None:
    got = _render_manual_workflow(
        ["dev", "prod"],
        TfDoConfig(),
        ["MONGODB_ATLAS_API_KEY", "AWS_ROLE_ARN"],
        ["AWS_REGION"],
        [],
    )
    job = got["job-manual"]
    assert "    env:" in job
    assert "      MONGODB_ATLAS_API_KEY: ${{ secrets.MONGODB_ATLAS_API_KEY }}" in job
    assert "      AWS_ROLE_ARN: ${{ secrets.AWS_ROLE_ARN }}" in job
    assert "      AWS_REGION: ${{ vars.AWS_REGION }}" in job


def test_manual_workflow_omits_empty_env_block() -> None:
    got = _render_manual_workflow(["dev"], TfDoConfig(), [], [], [])
    assert "    env:" not in got["job-manual"]
