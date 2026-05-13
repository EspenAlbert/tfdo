from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from tfdo._internal.check.models import (
    CheckResult,
    CredentialResult,
    DeclarationCase,
    DeclarationResult,
    ProviderCheckResult,
)
from tfdo._internal.config.provider_hints import ProviderHints
from tfdo._internal.config.resolver import ResolvedProvider, ResolvedRunDirConfig, resolve_run_dir
from tfdo._internal.settings import TfDoSettings

_MSG_A = "Unknown provider '{name}': not in provider_hints.yaml and not declared in any tfdo.yaml. Register it in provider_hints.yaml or declare it in the run-dir's tfdo.yaml."
_MSG_C = "Provider '{name}' is declared in a parent tfdo.yaml but has no provider_hints.yaml entry. Add a hints entry so tfdo can resolve the source and credentials."
_MSG_D = "Provider '{name}' is required by a module call but not declared in any tfdo.yaml or required_providers block. Declare it in the run-dir's tfdo.yaml."


def _check_declaration(rp: ResolvedProvider) -> DeclarationResult:
    if not rp.has_hints_entry:
        if not rp.is_declared_in_tfdo_yaml:
            return DeclarationResult(
                ok=False, case=DeclarationCase.no_hints_no_declaration, message=_MSG_A.format(name=rp.name)
            )
        if rp.is_force_injected:
            return DeclarationResult(ok=True, case=DeclarationCase.force_injected_no_hints)
        return DeclarationResult(
            ok=False, case=DeclarationCase.parent_constraint_no_hints, message=_MSG_C.format(name=rp.name)
        )
    if not rp.is_declared_in_tfdo_yaml and not rp.is_declared_in_hcl:
        return DeclarationResult(
            ok=False, case=DeclarationCase.undeclared_with_hints, message=_MSG_D.format(name=rp.name)
        )
    return DeclarationResult(ok=True)


def _check_credentials(name: str, hints: ProviderHints | None, env: Mapping[str, str]) -> CredentialResult:
    if hints is None or not hints.auth_bundles:
        return CredentialResult(satisfied=True)
    satisfied = hints.satisfied_bundles(env)
    if satisfied:
        return CredentialResult(satisfied=True, satisfied_bundle=satisfied[0].name)
    closest = hints.closest_bundle(env)
    if closest is None:
        return CredentialResult(satisfied=True)
    return CredentialResult(satisfied=False, closest_bundle=closest.bundle.name, missing_keys=closest.missing_keys)


def check_resolved(resolved: ResolvedRunDirConfig, os_env: Mapping[str, str]) -> CheckResult:
    results: list[ProviderCheckResult] = []
    for rp in resolved.required_providers:
        decl = _check_declaration(rp)
        hints = resolved.provider_hints.get(rp.name)
        creds = _check_credentials(rp.name, hints, os_env)
        results.append(ProviderCheckResult(name=rp.name, declaration=decl, credentials=creds))
    all_ok = all(r.declaration.ok and r.credentials.satisfied for r in results)
    return CheckResult(is_ok=all_ok, providers=results)


def check_run_dir(
    fixture_path: Path,
    env: str,
    run_dir_relative_path: str,
    os_env: Mapping[str, str] | None = None,
    settings: TfDoSettings | None = None,
) -> CheckResult:
    _os_env: Mapping[str, str] = os_env if os_env is not None else os.environ
    resolved = resolve_run_dir(
        fixture_path,
        env,
        run_dir_relative_path,
        settings=settings,
        os_env=_os_env,
    )
    return check_resolved(resolved, _os_env)
