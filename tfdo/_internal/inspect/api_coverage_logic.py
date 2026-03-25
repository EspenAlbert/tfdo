from __future__ import annotations

import json
import logging
from pathlib import Path

from model_lib import parse
from pydantic import BaseModel, Field

from tfdo._internal.inspect import name_normalize
from tfdo._internal.inspect.name_normalize import NameMapping
from tfdo._internal.schema.inspect_logic import load_provider_resource_schemas_with_meta
from tfdo._internal.schema.resource_input_paths import resource_schema_input_paths
from tfdo._internal.settings import TfDoSettings

logger = logging.getLogger(__name__)

DEFAULT_SPEC_IGNORE_PATHS = frozenset({"links", "envelope", "totalCount", "results"})


class ApiResourceEntry(BaseModel):
    resource_type: str
    all_paths: list[str] = Field(default_factory=list)


class ApiAttributesFile(BaseModel):
    provider: str = ""
    resources: list[ApiResourceEntry] = Field(default_factory=list)


class ResourceKnown(BaseModel):
    known_schema_only: list[str] = Field(default_factory=list)
    known_spec_only: list[str] = Field(default_factory=list)
    name_overrides: dict[str, str] = Field(default_factory=dict)


class ResolvedKnown(BaseModel):
    known_schema_only: set[str] = Field(default_factory=set)
    known_spec_only: set[str] = Field(default_factory=set)
    name_overrides: dict[str, str] = Field(default_factory=dict)


class CoverageConfig(BaseModel):
    resource_type_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Map api-attributes resource_type to TF resource name, e.g. mongodbatlas_cluster_api: mongodbatlas_advanced_cluster",
    )
    include_resources: list[str] = Field(
        default_factory=list,
        description="Allowlist of api-attributes resource types to compare, e.g. [mongodbatlas_cluster_api, mongodbatlas_project_api]",
    )
    exclude_resources: list[str] = Field(
        default_factory=list,
        description="Blocklist applied after include_resources, e.g. [mongodbatlas_event_trigger_api]",
    )
    name_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Global snake_case rename: normalized_api_segment -> tf_name, e.g. bi_connector: bi_connector_config",
    )
    known_schema_only: list[str] = Field(
        default_factory=list,
        description="TF paths with no API equivalent, suppressed from schema_only output, e.g. [project_id, state_name]",
    )
    known_spec_only: list[str] = Field(
        default_factory=list,
        description="API paths with no TF equivalent, suppressed from api_only output, e.g. [links.href, links.rel]",
    )
    resources: dict[str, ResourceKnown] = Field(
        default_factory=dict,
        description="Per-resource overrides merged with globals, keyed by api-attributes resource_type",
    )

    def resolve(self, api_resource_type: str) -> ResolvedKnown:
        per_resource = self.resources.get(api_resource_type, ResourceKnown())
        return ResolvedKnown(
            known_schema_only=set(self.known_schema_only) | set(per_resource.known_schema_only),
            known_spec_only=set(self.known_spec_only) | set(per_resource.known_spec_only),
            name_overrides={**self.name_overrides, **per_resource.name_overrides},
        )


class ApiCoverageInput(BaseModel):
    settings: TfDoSettings
    api_attributes_file: Path
    provider: str = "mongodbatlas"
    source: str | None = None
    version: str = ">= 1.0"
    no_cache: bool = False
    resource_filter: list[str] = Field(default_factory=list)
    include_computed: bool = True
    coverage_config: CoverageConfig | None = None


class ResourceGapReport(BaseModel):
    resource_type: str
    api_resource_type: str
    api_paths_count: int
    schema_paths_count: int
    matched: int
    fuzzy_matched: dict[str, str] = Field(default_factory=dict)
    prefix_matched: dict[str, list[str]] = Field(default_factory=dict)
    api_only: list[str] = Field(default_factory=list)
    schema_only: list[str] = Field(default_factory=list)
    coverage_pct: float = 0.0


class CoverageSummary(BaseModel):
    total_resources: int
    avg_coverage_pct: float
    resources_with_gaps: int


class ApiCoverageResult(BaseModel):
    provider: str
    version: str
    resources: list[ResourceGapReport] = Field(default_factory=list)
    summary: CoverageSummary = CoverageSummary(total_resources=0, avg_coverage_pct=0.0, resources_with_gaps=0)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2, sort_keys=True)


def _load_api_attributes(path: Path) -> ApiAttributesFile:
    return parse.parse_model(path, t=ApiAttributesFile)


def _build_gap_report(
    api_resource_type: str,
    resource_type: str,
    api_paths: set[str],
    tf_paths: frozenset[str],
    resolved: ResolvedKnown,
) -> ResourceGapReport:
    filtered_tf = {p for p in tf_paths if p not in resolved.known_schema_only}

    normalized_ignore = {name_normalize.normalize_api_path(p) for p in resolved.known_spec_only}
    spec_ignore_normalized = {name_normalize.normalize_api_path(p) for p in DEFAULT_SPEC_IGNORE_PATHS}
    all_ignore = normalized_ignore | spec_ignore_normalized

    filtered_api = {p for p in api_paths if name_normalize.normalize_api_path(p) not in all_ignore}

    mapping: NameMapping = name_normalize.build_name_mapping(
        filtered_api, filtered_tf, overrides=resolved.name_overrides
    )

    total_matched = len(mapping.matched) + len(mapping.fuzzy_matched) + len(mapping.prefix_matched)
    api_count = len(filtered_api)
    coverage = (total_matched / api_count * 100) if api_count else 0.0

    return ResourceGapReport(
        resource_type=resource_type,
        api_resource_type=api_resource_type,
        api_paths_count=api_count,
        schema_paths_count=len(filtered_tf),
        matched=len(mapping.matched),
        fuzzy_matched=mapping.fuzzy_matched,
        prefix_matched=mapping.prefix_matched,
        api_only=sorted(mapping.api_only),
        schema_only=sorted(mapping.tf_only),
        coverage_pct=round(coverage, 1),
    )


def inspect_api_coverage(input_model: ApiCoverageInput) -> ApiCoverageResult:
    config = input_model.coverage_config or CoverageConfig()
    api_file = _load_api_attributes(input_model.api_attributes_file)

    resource_schemas, resolved_version = load_provider_resource_schemas_with_meta(
        settings=input_model.settings,
        provider=input_model.provider,
        source=input_model.source,
        version=input_model.version,
        no_cache=input_model.no_cache,
    )

    include_set = set(config.include_resources) if config.include_resources else None
    exclude_set = set(config.exclude_resources)
    filter_set = set(input_model.resource_filter) if input_model.resource_filter else None

    reports: list[ResourceGapReport] = []
    for entry in api_file.resources:
        tf_type = config.resource_type_mapping.get(entry.resource_type, entry.resource_type)
        explicitly_requested = filter_set and (tf_type in filter_set or entry.resource_type in filter_set)
        if not explicitly_requested:
            if include_set and entry.resource_type not in include_set:
                continue
            if entry.resource_type in exclude_set:
                continue
        if filter_set and not explicitly_requested:
            continue

        schema = resource_schemas.get(tf_type)
        if schema is None:
            logger.warning(f"No TF schema for {tf_type!r} (api: {entry.resource_type!r}), reporting zero coverage")
            reports.append(
                ResourceGapReport(
                    resource_type=tf_type,
                    api_resource_type=entry.resource_type,
                    api_paths_count=len(entry.all_paths),
                    schema_paths_count=0,
                    matched=0,
                )
            )
            continue

        tf_paths = resource_schema_input_paths(schema, max_depth=10, include_computed=input_model.include_computed)
        api_paths = set(entry.all_paths)
        resolved = config.resolve(entry.resource_type)
        reports.append(_build_gap_report(entry.resource_type, tf_type, api_paths, tf_paths, resolved))

    total = len(reports)
    avg_pct = sum(r.coverage_pct for r in reports) / total if total else 0.0
    gaps = sum(1 for r in reports if r.api_only or r.schema_only)

    return ApiCoverageResult(
        provider=input_model.provider,
        version=resolved_version,
        resources=reports,
        summary=CoverageSummary(
            total_resources=total,
            avg_coverage_pct=round(avg_pct, 1),
            resources_with_gaps=gaps,
        ),
    )
