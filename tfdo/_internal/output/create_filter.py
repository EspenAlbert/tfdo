from __future__ import annotations


def is_empty_create_value(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}
