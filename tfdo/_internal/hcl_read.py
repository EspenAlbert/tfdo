"""Read-only HCL parsing with v7-compatible output (stripped quotes, no block markers).

Use for extracting information from .tf files. Never write results back as HCL.
For modifying .tf content, use hcl_roundtrip instead.
"""

from __future__ import annotations

from typing import Any, TextIO

from hcl2.api import load as _hcl2_load
from hcl2.api import loads as _hcl2_loads
from hcl2.utils import SerializationOptions

_V7_COMPAT = SerializationOptions(
    strip_string_quotes=True,
    explicit_blocks=False,
    with_comments=False,
)


def hcl2_load(fp: TextIO) -> dict[str, Any]:
    return _hcl2_load(fp, serialization_options=_V7_COMPAT)


def hcl2_loads(text: str) -> dict[str, Any]:
    return _hcl2_loads(text, serialization_options=_V7_COMPAT)
