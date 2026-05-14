from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple

import yaml
from ask_shell._internal.interactive import ChoiceTyped
from pydantic import BaseModel, Field


class ProviderHintsError(ValueError):
    pass


class UnknownInheritsFromError(ProviderHintsError):
    def __init__(self, provider: str, bundle: str, missing_ref: str) -> None:
        super().__init__(
            f"provider '{provider}': bundle '{bundle}' references inherits_from='{missing_ref}' which does not exist"
        )


class UnknownProviderError(ProviderHintsError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"provider '{provider}' not found in registry")


class VariableMapping(BaseModel):
    env: str
    tf_var: str
    provider_attr: str | None = None


class ModuleHint(BaseModel):
    source: str
    alias: str


class ModuleChoice(NamedTuple):
    provider: str
    hint: ModuleHint


class BundleRequirements(NamedTuple):
    secrets: list[str]
    variables: list[str]

    @property
    def all_keys(self) -> list[str]:
        return self.secrets + self.variables


class AuthBundle(BaseModel):
    name: str
    secrets: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    inherits_from: str | None = None

    def effective_requirements(self, bundles_by_name: dict[str, AuthBundle]) -> BundleRequirements:
        if self.inherits_from is None:
            return BundleRequirements(list(self.secrets), list(self.variables))
        parent = bundles_by_name[self.inherits_from]
        parent_reqs = parent.effective_requirements(bundles_by_name)
        return BundleRequirements(
            secrets=list(dict.fromkeys(parent_reqs.secrets + self.secrets)),
            variables=list(dict.fromkeys(parent_reqs.variables + self.variables)),
        )

    def is_satisfied(self, env: Mapping[str, str], bundles_by_name: dict[str, AuthBundle] | None = None) -> bool:
        reqs = self.effective_requirements(bundles_by_name or {})
        return all(k in env for k in reqs.all_keys)


class ClosestBundle(NamedTuple):
    bundle: AuthBundle
    missing_keys: list[str]


class ProviderHints(BaseModel):
    source: str | None = None
    auth_bundles: list[AuthBundle] = Field(default_factory=list)
    auth_variables: list[VariableMapping] = Field(default_factory=list)
    variable_options: list[VariableMapping] = Field(default_factory=list)
    required_config: list[str] = Field(default_factory=list)
    modules: list[ModuleHint] = Field(default_factory=list)

    def _bundles_by_name(self) -> dict[str, AuthBundle]:
        return {b.name: b for b in self.auth_bundles}

    def satisfied_bundles(self, env: Mapping[str, str]) -> list[AuthBundle]:
        by_name = self._bundles_by_name()
        return [b for b in self.auth_bundles if b.is_satisfied(env, by_name)]

    def closest_bundle(self, env: Mapping[str, str]) -> ClosestBundle | None:
        if not self.auth_bundles:
            return None
        by_name = self._bundles_by_name()
        best: ClosestBundle | None = None
        for bundle in self.auth_bundles:
            reqs = bundle.effective_requirements(by_name)
            missing = [k for k in reqs.all_keys if k not in env]
            if best is None or len(missing) < len(best.missing_keys):
                best = ClosestBundle(bundle=bundle, missing_keys=missing)
        return best


def _validate_provider_hints(provider: str, hints: ProviderHints) -> None:
    names = {b.name for b in hints.auth_bundles}
    for bundle in hints.auth_bundles:
        if bundle.inherits_from is not None and bundle.inherits_from not in names:
            raise UnknownInheritsFromError(provider, bundle.name, bundle.inherits_from)


def load_provider_hints(path: Path) -> dict[str, ProviderHints]:
    if not path.is_file():
        return {}
    raw: dict[str, object] = yaml.safe_load(path.read_text()) or {}
    registry: dict[str, ProviderHints] = {}
    for provider, data in raw.items():
        hints = ProviderHints.model_validate(data or {})
        _validate_provider_hints(provider, hints)
        registry[provider] = hints
    return registry


def get_provider_hints(registry: dict[str, ProviderHints], provider: str) -> ProviderHints:
    if provider not in registry:
        raise UnknownProviderError(provider)
    return registry[provider]


def available_module_choices(
    providers: list[str], registry: dict[str, ProviderHints], *, checked: bool = False
) -> list[ChoiceTyped[ModuleChoice]]:
    """Return interactive choices for all modules available to the given providers."""
    result: list[ChoiceTyped[ModuleChoice]] = []
    for provider in providers:
        hints = registry.get(provider)
        if not hints or not hints.modules:
            continue
        for mhint in hints.modules:
            mc = ModuleChoice(provider=provider, hint=mhint)
            result.append(ChoiceTyped(name=f"{provider}: {mhint.alias}", value=mc, checked=checked))
    return result
