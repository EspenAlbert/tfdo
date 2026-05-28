from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from tfdo._internal.output.models import PlanOutput
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

PLAN_PARSE_FAILURE_FILENAME = "plan_parse_failure.json"


class PlanParseFailureRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: str
    source_path: str
    error_type: str
    message: str
    lines: list[str]

    @classmethod
    def from_exception(cls, path: Path, exc: Exception, raw_text: str) -> PlanParseFailureRecord:
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            source_path=str(path),
            error_type=type(exc).__name__,
            message=str(exc),
            lines=_failure_lines(exc, raw_text),
        )

    def to_ndjson_line(self) -> str:
        return self.model_dump_json() + "\n"


def parse_plan_file(path: Path, *, settings: TfDoSettings | None = None) -> PlanOutput:
    settings = settings or TfDoSettings.from_env()
    raw_text = path.read_text()
    try:
        data = json.loads(raw_text)
        return PlanOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning(f"failed to parse plan file {path}", exc_info=True)
        _append_parse_failure(settings, path, exc, raw_text)
        raise


def _append_parse_failure(
    settings: TfDoSettings,
    path: Path,
    exc: Exception,
    raw_text: str,
) -> None:
    failure_path = settings.cache_root / PLAN_PARSE_FAILURE_FILENAME
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    record = PlanParseFailureRecord.from_exception(path, exc, raw_text)
    with failure_path.open("a") as f:
        f.write(record.to_ndjson_line())


def _failure_lines(exc: Exception, raw_text: str) -> list[str]:
    if isinstance(exc, ValidationError):
        return [str(e) for e in exc.errors()]
    return raw_text.splitlines()
