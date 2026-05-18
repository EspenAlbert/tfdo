from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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


class RefreshEvent(StreamEnvelope):
    hook: StreamHook | None = None


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
    source_range: DiagnosticRange | None = Field(default=None, validation_alias="range")
    snippet: DiagnosticSnippet | None = None


class DiagnosticEvent(StreamEnvelope):
    diagnostic: DiagnosticBody | None = None


class ChangeCounts(BaseModel):
    model_config = ConfigDict(extra="ignore")

    add: int = 0
    change: int = 0
    remove: int = 0


class ChangeSummaryEvent(StreamEnvelope):
    changes: ChangeCounts | None = None
