from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)


class StreamEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    level: str | None = Field(default=None, alias="@level")
    message: str | None = Field(default=None, alias="@message")
    module: str | None = Field(default=None, alias="@module")
    timestamp: str | None = Field(default=None, alias="@timestamp")


class StreamResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    addr: str


class StreamHook(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resource: StreamResource | None = None
    action: str | None = None
    elapsed_seconds: float | None = None
    provisioner: str | None = None
    output: str | None = None


class RefreshEvent(StreamEnvelope):
    hook: StreamHook | None = None


class ApplyHookEvent(StreamEnvelope):
    hook: StreamHook | None = None


class PlannedChangeResource(BaseModel):
    model_config = ConfigDict(extra="ignore")

    addr: str


class PlannedChangeBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    resource: PlannedChangeResource
    action: str


class PlannedChangeEvent(StreamEnvelope):
    change: PlannedChangeBody | None = None


class DiagnosticPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line: int
    column: int
    byte: int | None = None


class DiagnosticRange(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filename: str
    start: DiagnosticPosition
    end: DiagnosticPosition


class DiagnosticSnippet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    context: str | None = None
    code: str
    start_line: int
    highlight_start_offset: int
    highlight_end_offset: int


class DiagnosticBody(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    severity: str | None = None
    summary: str
    detail: str | None = None
    address: str | None = None
    source_range: DiagnosticRange | None = Field(default=None, validation_alias="range")
    snippet: DiagnosticSnippet | None = None


class DiagnosticEvent(StreamEnvelope):
    diagnostic: DiagnosticBody | None = None


class ChangeCounts(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    add: int = 0
    change: int = 0
    remove: int = 0
    operation: str | None = None
    import_: int | None = Field(default=None, alias="import")


class ChangeSummaryEvent(StreamEnvelope):
    changes: ChangeCounts | None = None


class ApplyOutputValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sensitive: bool = False
    type: str | None = None
    value: object | None = None
    action: str | None = None


class OutputsEvent(StreamEnvelope):
    outputs: dict[str, ApplyOutputValue] = Field(default_factory=dict)


class StreamParseFailureRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    timestamp: str
    error_type: str
    message: str
    line: str
    details: list[str] = Field(default_factory=list)

    @classmethod
    def from_exception(cls, line: str, exc: Exception) -> StreamParseFailureRecord:
        return cls(
            timestamp=datetime.now(UTC).isoformat(),
            error_type=type(exc).__name__,
            message=str(exc),
            line=line,
            details=_failure_details(exc),
        )

    def to_ndjson_line(self) -> str:
        return self.model_dump_json() + "\n"


def parse_stream_line(line: str, *, settings: TfDoSettings | None = None) -> dict[str, object] | None:
    try:
        data = json.loads(line)
        StreamEnvelope.model_validate(data)
        return data
    except (json.JSONDecodeError, ValidationError) as exc:
        settings = settings or TfDoSettings.from_env()
        logger.debug(f"skipping invalid apply stream line: {line[:120]!r}")
        _append_stream_parse_failure(settings, line, exc)
        return None


def _append_stream_parse_failure(settings: TfDoSettings, line: str, exc: Exception) -> None:
    failure_path = settings.cache_root / TfDoSettings.STREAM_PARSE_FAILURE_FILENAME
    failure_path.parent.mkdir(parents=True, exist_ok=True)
    record = StreamParseFailureRecord.from_exception(line, exc)
    with failure_path.open("a") as f:
        f.write(record.to_ndjson_line())


def _failure_details(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        return [str(e) for e in exc.errors()]
    return []
