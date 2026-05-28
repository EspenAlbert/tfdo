from __future__ import annotations

from tfdo._internal.output.models import ChangeMarker


def has_unknown_values(marker: ChangeMarker | None) -> bool:
    """Return True when Terraform after_unknown marks any unknown leaf."""
    if marker is False or marker is None:
        return False
    if marker is True:
        return True
    if isinstance(marker, dict):
        return any(has_unknown_values(value) for value in marker.values())
    if isinstance(marker, list):
        return any(has_unknown_values(value) for value in marker)
    return bool(marker)
