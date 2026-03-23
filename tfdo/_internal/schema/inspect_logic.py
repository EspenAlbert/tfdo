from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from tfdo._internal.schema import inspect as schema_inspect
from tfdo._internal.schema.models import ResourceSchema
from tfdo._internal.settings import TfDoSettings

KNOWN_PROVIDER_SOURCES: dict[str, str] = {
    "mongodbatlas": "mongodb/mongodbatlas",
}


def resolve_registry_source(*, provider: str, source: str | None) -> str:
    if source:
        return source
    if provider in KNOWN_PROVIDER_SOURCES:
        return KNOWN_PROVIDER_SOURCES[provider]
    raise ValueError(f"No default registry source for provider {provider!r}; pass --source (example: hashicorp/aws)")


def pick_provider_key(provider_schemas: dict[str, Any], *, local_name: str, source: str) -> str:
    keys = list(provider_schemas.keys())
    suffix = f"/{source}"
    by_source = [k for k in keys if k.endswith(suffix)]
    if len(by_source) == 1:
        return by_source[0]
    if len(by_source) > 1:
        raise ValueError(f"Ambiguous provider keys for source {source!r}: {by_source!r}")
    by_local = [k for k in keys if k.rpartition("/")[2] == local_name]
    if len(by_local) == 1:
        return by_local[0]
    if len(by_local) > 1:
        raise ValueError(f"Ambiguous provider keys for local name {local_name!r}: {by_local!r}")
    raise ValueError(f"Provider not found (source={source!r}, local={local_name!r}). Sample keys: {keys[:12]!r}")


class SchemaShowInput(BaseModel):
    settings: TfDoSettings
    provider: str
    source: str | None = None
    version: str = ">= 1.0"
    resource: str | None = None
    no_cache: bool = False


class SchemaShowResult(BaseModel):
    resource_names: list[str] = Field(default_factory=list)
    resource: ResourceSchema | None = None

    def to_canonical_json(self) -> str:
        payload: dict[str, Any] = {"resource_names": self.resource_names}
        if self.resource:
            payload["resource"] = self.resource.model_dump(mode="json", exclude_none=True)
        return json.dumps(payload, indent=2, sort_keys=True)


def schema_show(input_model: SchemaShowInput) -> SchemaShowResult:
    source = resolve_registry_source(provider=input_model.provider, source=input_model.source)
    raw = schema_inspect.fetch_providers_schema_json(
        input_model.settings,
        local_name=input_model.provider,
        source=source,
        version=input_model.version,
        no_cache=input_model.no_cache,
    )
    pschemas = raw.get("provider_schemas")
    if not isinstance(pschemas, dict):
        raise ValueError("Invalid schema JSON: provider_schemas missing or not an object")
    pkey = pick_provider_key(pschemas, local_name=input_model.provider, source=source)
    entry = pschemas[pkey]
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid provider entry for {pkey!r}")
    rschemas = entry.get("resource_schemas")
    if not isinstance(rschemas, dict):
        rschemas = {}
    names = sorted(rschemas.keys())
    if input_model.resource is None:
        return SchemaShowResult(resource_names=names)
    if input_model.resource not in rschemas:
        preview = names[:24]
        tail = "..." if len(names) > 24 else ""
        raise ValueError(f"Resource {input_model.resource!r} not found. Sample: {preview}{tail}")
    parsed = ResourceSchema.model_validate(rschemas[input_model.resource])
    return SchemaShowResult(resource_names=names, resource=parsed)
