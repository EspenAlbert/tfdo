from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class DeclarationCase(StrEnum):
    no_hints_no_declaration = "no_hints_no_declaration"
    force_injected_no_hints = "force_injected_no_hints"
    parent_constraint_no_hints = "parent_constraint_no_hints"
    undeclared_with_hints = "undeclared_with_hints"


class DeclarationResult(BaseModel):
    ok: bool
    case: DeclarationCase | None = None
    message: str = ""


class CredentialResult(BaseModel):
    satisfied: bool
    satisfied_bundle: str | None = None
    closest_bundle: str | None = None
    missing_keys: list[str] = Field(default_factory=list)


class ProviderCheckResult(BaseModel):
    name: str
    declaration: DeclarationResult
    credentials: CredentialResult


class CheckResult(BaseModel):
    is_ok: bool
    providers: list[ProviderCheckResult] = Field(default_factory=list)
