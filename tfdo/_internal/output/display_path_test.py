from __future__ import annotations

from tfdo._internal.output.display_path import inline_json


def test_inline_json_unwraps_json_object_string() -> None:
    raw = '{"name": "api-live-rat", "version": "1.0.0"}'
    assert inline_json(raw) == '{"name":"api-live-rat","version":"1.0.0"}'


def test_inline_json_keeps_plain_string() -> None:
    assert inline_json("./output/config.json") == '"./output/config.json"'


def test_inline_json_keeps_invalid_json_prefix() -> None:
    assert inline_json("{not json") == '"{not json"'
