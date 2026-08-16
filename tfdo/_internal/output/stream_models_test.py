from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from tfdo._internal.output.stream_models import OutputsEvent, coerce_output_type, parse_stream_line
from tfdo._internal.settings import TfDoSettings


def test_parse_failure_appends_to_cache_ndjson(tmp_path: Path) -> None:
    settings = TfDoSettings.for_testing(tmp_path)
    failure_path = settings.cache_root / TfDoSettings.STREAM_PARSE_FAILURE_FILENAME
    bad_line = "{not json"

    assert parse_stream_line(bad_line, settings=settings) is None

    record = json.loads(failure_path.read_text().strip())
    assert record["line"] == bad_line
    assert record["error_type"] == "JSONDecodeError"

    assert parse_stream_line('{"type": 1}', settings=settings) is None
    records = failure_path.read_text().strip().splitlines()
    assert len(records) == 2
    assert json.loads(records[1])["error_type"] == ValidationError.__name__


def test_coerce_output_type() -> None:
    assert coerce_output_type("string") == "string"
    assert coerce_output_type(["object", {"k": "string"}]) == ["object", {"k": "string"}]
    assert coerce_output_type(None) is None
    assert coerce_output_type(42) is None


def test_outputs_event_complex_type() -> None:
    object_type = ["object", {"phase_a_rotation_rfc3339": "string"}]
    event = OutputsEvent.model_validate(
        {
            "type": "outputs",
            "outputs": {
                "rotation_schedule": {
                    "sensitive": False,
                    "type": object_type,
                    "value": {"phase_a_rotation_rfc3339": "2026-01-01T00:00:00Z"},
                }
            },
        }
    )
    entry = event.outputs["rotation_schedule"]
    assert entry.type == object_type
    assert entry.value == {"phase_a_rotation_rfc3339": "2026-01-01T00:00:00Z"}
