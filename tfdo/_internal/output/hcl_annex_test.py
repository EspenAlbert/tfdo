from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from tfdo._internal.output.hcl_annex import find_resource_change, render_hcl_annex_as_tf, strip_marked_paths
from tfdo._internal.output.parser import parse_plan_file
from tfdo._internal.output.testdata_paths import TESTDATA_DIR
from tfdo._internal.schema.models import ResourceSchema

BUCKET_ADDRESS = "module.gcp.module.log_integration[0].google_storage_bucket.atlas[0]"
_SCHEMA_DIR = TESTDATA_DIR / "schemas"


@dataclass(frozen=True)
class AnnexTfCase:
    fixture_name: str
    address: str
    attr_name: str
    schema_name: str
    basename: str


ANNEX_TF_CASES = (
    AnnexTfCase(
        "09_create_atlas_compact.json",
        BUCKET_ADDRESS,
        "lifecycle_rule",
        "google_storage_bucket.json",
        "09_bucket_lifecycle_rule",
    ),
)


def _load_schema(name: str) -> ResourceSchema:
    return ResourceSchema.model_validate(json.loads((_SCHEMA_DIR / name).read_text()))


def test_strip_marked_paths_removes_unknown_leaves():
    value = {"a": {"keep": 1, "drop": 2}, "remove": 3}
    marks = {"a": {"drop": True}, "remove": True}
    assert strip_marked_paths(value, marks) == {"a": {"keep": 1}}


def test_strip_marked_paths_empty_dict_does_not_strip_without_leaf_marks():
    value = {"secret": {"token": "x"}, "ok": 1}
    assert strip_marked_paths(value, {"secret": {}}) == value
    assert strip_marked_paths(value, {"secret": {"token": True}}) == {"ok": 1}


@pytest.mark.parametrize("case", ANNEX_TF_CASES, ids=lambda case: case.basename)
def test_hcl_annex_regression_tf(case: AnnexTfCase, file_regression) -> None:
    plan = parse_plan_file(TESTDATA_DIR / case.fixture_name)
    resource = find_resource_change(plan, address=case.address)
    schema = _load_schema(case.schema_name)
    tf_text = render_hcl_annex_as_tf(resource, case.attr_name, schema=schema)
    assert tf_text is not None
    file_regression.check(tf_text, basename=case.basename, extension=".tf")
