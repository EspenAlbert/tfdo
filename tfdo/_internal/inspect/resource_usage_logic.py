from __future__ import annotations

import json
import logging
from pathlib import Path

from hcl2.api import load as hcl2_load
from pydantic import BaseModel, Field

from tfdo._internal.core.tf_files import iter_tf_files
from tfdo._internal.inspect import hcl_resource_paths as hrp
from tfdo._internal.inspect.description_search_logic import (
    MatchingSchemaResource,
    search_resource_descriptions,
)
from tfdo._internal.inspect.hcl_resource_paths import HclParseError
from tfdo._internal.inspect.hcl_schema_paths import collect_resource_body_paths_assisted
from tfdo._internal.inspect.schema_input_classify_logic import (
    SchemaInputClassifyInput,
    SchemaInputClassifyMode,
    SchemaInputClassifyResult,
    SchemaInputClassifyRowInput,
    classify_schema_inputs,
    schema_input_classify_payload,
)
from tfdo._internal.schema.inspect_logic import (
    load_provider_resource_schemas_with_meta,
    resolve_registry_source,
)
from tfdo._internal.schema.models import ResourceSchema
from tfdo._internal.schema.resource_input_paths import resource_schema_input_paths
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

_V1_OUTPUT_PATHS_MSG = "Output path comparison is not implemented; use input-only (default). Omit --no-input-only."


class ProviderMeta(BaseModel):
    source: str
    version: str


class SchemaSearch(BaseModel):
    description_keywords: list[str] = Field(default_factory=list)
    resource_ignore: list[str] = Field(default_factory=list)
    include_data_sources: bool = False

    @property
    def has_search_criteria(self) -> bool:
        return bool(self.description_keywords)


class ResourceUsageResult(BaseModel):
    providers: dict[str, ProviderMeta]
    classify: SchemaInputClassifyResult
    matching_schema_resources: list[MatchingSchemaResource] | None = None

    def to_canonical_json(self, *, error_paths_relative_to: Path | None = None) -> str:
        payload = schema_input_classify_payload(self.classify, error_paths_relative_to=error_paths_relative_to)
        payload["providers"] = {k: v.model_dump(mode="json") for k, v in sorted(self.providers.items())}
        if self.matching_schema_resources is not None:
            payload["matching_schema_resources"] = [r.model_dump(mode="json") for r in self.matching_schema_resources]
        return json.dumps(payload, indent=2, sort_keys=True)


def _resource_type_cli_namespace(resource_type: str) -> str:
    return resource_type.partition("_")[0]


def _extend_rows_from_parsed(
    parsed: dict,
    tf_file: Path,
    resource_schemas: dict[str, ResourceSchema],
    provider: str,
    rows_in: list[SchemaInputClassifyRowInput],
) -> None:
    for top in parsed.get("resource") or []:
        if not isinstance(top, dict):
            continue
        for rtype, labels_obj in top.items():
            if not isinstance(labels_obj, dict):
                continue
            for label, body in labels_obj.items():
                if not isinstance(body, dict):
                    continue
                addr = f"{rtype}.{label}"
                schema = resource_schemas.get(rtype)
                if schema is None:
                    if _resource_type_cli_namespace(rtype) == provider:
                        logger.warning(
                            f"Skipping {addr!r} in {tf_file}: resource type not in loaded schema for provider {provider!r}"
                        )
                    continue
                schema_paths = resource_schema_input_paths(schema)
                assisted = collect_resource_body_paths_assisted(body, schema)
                config_paths = frozenset(assisted.attribute_paths | assisted.unknown_in_config)
                rows_in.append(
                    SchemaInputClassifyRowInput(
                        file=tf_file,
                        address=addr,
                        schema_input_paths=schema_paths,
                        config_paths=config_paths,
                        invalid_in_config=assisted.invalid_in_config,
                    )
                )


class ResourceUsageInput(BaseModel):
    settings: TfDoSettings
    root: Path
    mode: SchemaInputClassifyMode = Field(default=SchemaInputClassifyMode.ALL)
    input_only: bool = True
    provider: str
    source: str | None = None
    version: str = ">= 1.0"
    no_cache: bool = False
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    schema_search: SchemaSearch | None = None


def inspect_resource_usage(input_model: ResourceUsageInput) -> ResourceUsageResult:
    if not input_model.input_only:
        raise ValueError(_V1_OUTPUT_PATHS_MSG)
    resolved_source = resolve_registry_source(provider=input_model.provider, source=input_model.source)
    resource_schemas, resolved_version = load_provider_resource_schemas_with_meta(
        settings=input_model.settings,
        provider=input_model.provider,
        source=input_model.source,
        version=input_model.version,
        no_cache=input_model.no_cache,
    )
    provider_meta = ProviderMeta(source=resolved_source, version=resolved_version)
    rows_in: list[SchemaInputClassifyRowInput] = []
    errors: list[HclParseError] = []
    root_resolved = input_model.root.resolve()
    for path in iter_tf_files(
        input_model.root,
        input_model.include_patterns,
        input_model.exclude_patterns,
    ):
        rel_file = path.resolve().relative_to(root_resolved)
        try:
            with path.open(encoding="utf-8") as f:
                parsed = hcl2_load(f)
        except Exception as exc:
            errors.append(hrp._to_parse_error(path, exc))
            continue
        _extend_rows_from_parsed(parsed, rel_file, resource_schemas, input_model.provider, rows_in)
    classified = classify_schema_inputs(SchemaInputClassifyInput(mode=input_model.mode, errors=errors, rows=rows_in))
    matching: list[MatchingSchemaResource] | None = None
    if input_model.schema_search is not None and input_model.schema_search.has_search_criteria:
        row_resource_names = {row.address.partition(".")[0] for row in rows_in}
        matching = search_resource_descriptions(
            resource_schemas,
            keywords=input_model.schema_search.description_keywords,
            row_resource_names=row_resource_names,
        )
    return ResourceUsageResult(
        providers={input_model.provider: provider_meta},
        classify=classified,
        matching_schema_resources=matching,
    )
