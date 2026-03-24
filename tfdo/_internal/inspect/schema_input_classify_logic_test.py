from pathlib import Path

from tfdo._internal.inspect.hcl_resource_paths import HclParseError
from tfdo._internal.inspect.schema_input_classify_logic import (
    SchemaInputClassifyInput,
    SchemaInputClassifyMode,
    SchemaInputClassifyRowInput,
    classify_schema_inputs,
)


def test_rows_sorted_by_address_then_file() -> None:
    rows = [
        SchemaInputClassifyRowInput(
            file=Path("z.tf"),
            address="b.r",
            schema_input_paths=frozenset({"a"}),
            config_paths=frozenset({"a"}),
        ),
        SchemaInputClassifyRowInput(
            file=Path("a.tf"),
            address="a.r",
            schema_input_paths=frozenset({"a"}),
            config_paths=frozenset({"a"}),
        ),
        SchemaInputClassifyRowInput(
            file=Path("m.tf"),
            address="a.r",
            schema_input_paths=frozenset({"b"}),
            config_paths=frozenset({"b"}),
        ),
    ]
    result = classify_schema_inputs(SchemaInputClassifyInput(mode=SchemaInputClassifyMode.INCLUDED, rows=rows))
    assert [r.address for r in result.rows] == ["a.r", "a.r", "b.r"]


def test_all_mode_json_omits_empty_unknown_and_invalid() -> None:
    row = SchemaInputClassifyRowInput(
        file=Path("a.tf"),
        address="x.y",
        schema_input_paths=frozenset({"k"}),
        config_paths=frozenset({"k"}),
    )
    text = classify_schema_inputs(
        SchemaInputClassifyInput(mode=SchemaInputClassifyMode.ALL, rows=[row])
    ).to_canonical_json()
    assert "unknown_in_config" not in text
    assert "invalid_in_config" not in text


def test_classify_all_mode_partitions_unknown_and_invalid() -> None:
    row = SchemaInputClassifyRowInput(
        file=Path("a.tf"),
        address="aws_instance.app",
        schema_input_paths=frozenset({"ami", "subnet_id", "block.disk_size"}),
        config_paths=frozenset({"ami", "weird", "block.disk_size"}),
        invalid_in_config=frozenset({"block.disk_size"}),
    )
    inp = SchemaInputClassifyInput(mode=SchemaInputClassifyMode.ALL, rows=[row])
    result = classify_schema_inputs(inp)
    r0 = result.rows[0]
    assert r0.included == ["ami", "block.disk_size"]
    assert r0.excluded == ["subnet_id"]
    assert r0.unknown_in_config == ["weird"]
    assert r0.invalid_in_config == ["block.disk_size"]


def test_classify_included_and_excluded_strip_other_fields() -> None:
    row = SchemaInputClassifyRowInput(
        file=Path("m.tf"),
        address="null_resource.x",
        schema_input_paths=frozenset({"a", "b"}),
        config_paths=frozenset({"a"}),
    )
    inc = classify_schema_inputs(SchemaInputClassifyInput(mode=SchemaInputClassifyMode.INCLUDED, rows=[row])).rows[0]
    assert inc.included == ["a"]
    assert inc.excluded is None
    assert inc.unknown_in_config is None
    assert inc.invalid_in_config is None
    exc = classify_schema_inputs(SchemaInputClassifyInput(mode=SchemaInputClassifyMode.EXCLUDED, rows=[row])).rows[0]
    assert exc.excluded == ["b"]
    assert exc.included is None


def test_canonical_json_always_has_errors_key() -> None:
    payload = classify_schema_inputs(SchemaInputClassifyInput(mode=SchemaInputClassifyMode.ALL)).to_canonical_json()
    assert '"errors": []' in payload
    assert '"rows": []' in payload


def test_errors_relativized_and_sorted() -> None:
    root = Path("/tmp/ws")
    err = HclParseError(path=Path("/tmp/ws/mod/x.tf"), message="boom")
    also = HclParseError(path=Path("/tmp/ws/a.tf"), message="a")
    inp = SchemaInputClassifyInput(
        mode=SchemaInputClassifyMode.INCLUDED,
        errors=[err, also],
    )
    result = classify_schema_inputs(inp)
    text = result.to_canonical_json(error_paths_relative_to=root)
    assert "mod/x.tf" in text
    assert "/tmp/ws" not in text


def test_error_outside_root_keeps_path_in_json() -> None:
    root = Path("/tmp/ws")
    err = HclParseError(path=Path("/other/x.tf"), message="x")
    result = classify_schema_inputs(SchemaInputClassifyInput(mode=SchemaInputClassifyMode.INCLUDED, errors=[err]))
    text = result.to_canonical_json(error_paths_relative_to=root)
    assert "other" in text
