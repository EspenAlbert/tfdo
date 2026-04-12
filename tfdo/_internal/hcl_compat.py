from __future__ import annotations

from typing import IO, Any

from hcl2.api import load as _hcl2_load
from hcl2.utils import SerializationOptions

_V7_COMPAT = SerializationOptions(
    strip_string_quotes=True,
    explicit_blocks=False,
    with_comments=False,
)


def hcl2_load(fp: IO[str]) -> dict[str, Any]:
    return _hcl2_load(fp, serialization_options=_V7_COMPAT)
