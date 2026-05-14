from __future__ import annotations

import copy
from collections.abc import Callable, Iterable
from typing import Any

import hcl2
from hcl2.rules.base import AttributeRule, BlockRule, StartRule
from hcl2.rules.expressions import ExprTermRule
from hcl2.rules.literal_rules import IdentifierRule
from hcl2.rules.strings import StringRule
from pydantic import BaseModel

_BLOCK_MARKER = "__is_block__"
_HCL_PATCH_FRAGMENT_BLOCK = "zzz_tfdo_hcl_patch_fragment"


class HclLiteral(BaseModel, frozen=True):
    value: Any


class HclVarRef(BaseModel, frozen=True):
    path: str


class HclAttrRef(BaseModel, frozen=True):
    path: str


class HclExpression(BaseModel, frozen=True):
    expression: str


type HclValue = HclLiteral | HclVarRef | HclAttrRef | HclExpression | list["HclValue"] | dict[str, "HclValue"]


def _label_to_str(label: Any) -> str:
    if isinstance(label, IdentifierRule):
        return label.serialize()
    if isinstance(label, StringRule):
        raw = label.serialize()
        if isinstance(raw, str) and len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
            return raw[1:-1]
        return str(raw)
    return str(label.serialize())


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _quoted_label(value: str) -> str:
    return f'"{_strip_wrapping_quotes(value)}"'


def _is_hcl_string(value: str) -> bool:
    return len(value) >= 2 and value[0] == '"' and value[-1] == '"'


def _is_hcl_expression(value: str) -> bool:
    if value.startswith("${") and value.endswith("}"):
        return True
    if "." in value and " " not in value and "/" not in value:
        return True
    return False


def _to_hcl_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if _is_hcl_string(value) or _is_hcl_expression(value):
        return value
    return f'"{value}"'


def _is_attr_reference_path(value: str) -> bool:
    if value.startswith("var."):
        return False
    segments = value.split(".")
    if len(segments) < 2:
        return False
    for segment in segments:
        if not segment:
            return False
        if not (segment[0].isalpha() or segment[0] == "_"):
            return False
        if not all(char.isalnum() or char == "_" for char in segment):
            return False
    return True


def _parse_interpolation(value: str) -> HclVarRef | HclAttrRef | HclExpression:
    expression = value[2:-1].strip()
    if expression.startswith("var."):
        return HclVarRef(path=expression)
    if _is_attr_reference_path(expression):
        return HclAttrRef(path=expression)
    return HclExpression(expression=expression)


def _parse_hcl_value(value: Any) -> HclValue:
    if isinstance(value, dict):
        return {key: _parse_hcl_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_parse_hcl_value(item) for item in value]
    if isinstance(value, str) and _is_hcl_string(value):
        return HclLiteral(value=_strip_wrapping_quotes(value))
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return _parse_interpolation(value)
    return HclLiteral(value=value)


def block_labels(block: BlockRule) -> list[str]:
    return [_label_to_str(label) for label in block.labels]


def find_block_index(tree: StartRule, label_path: Iterable[str]) -> int:
    target = list(label_path)
    for index, child in enumerate(tree.body.children):
        if isinstance(child, BlockRule) and block_labels(child) == target:
            return index
    raise ValueError(f"no block with labels {target} found")


def block_exists(tree: StartRule, label_path: Iterable[str]) -> bool:
    try:
        find_block_index(tree, label_path)
    except ValueError:
        return False
    return True


def first_block(tree: StartRule) -> BlockRule:
    for child in tree.body.children:
        if isinstance(child, BlockRule):
            return child
    raise ValueError("no block found in tree")


def _append_block(original: str, block_dict: dict[str, Any]) -> str:
    new_block_text = hcl2.reconstruct(hcl2.from_dict(block_dict))
    return original.rstrip("\n") + "\n\n" + new_block_text


def _delete_block(original: str, label_path: Iterable[str]) -> str:
    tree = hcl2.parses(original, discard_comments=False)
    index = find_block_index(tree, label_path)
    tree.body.children.pop(index)
    return hcl2.reconstruct(tree)


def splice_block(original: str, block_dict: dict[str, Any], label_path: Iterable[str]) -> str:
    tree = hcl2.parses(original, discard_comments=False)
    new_block = first_block(hcl2.from_dict(block_dict))
    tree.body.children[find_block_index(tree, label_path)] = new_block
    return hcl2.reconstruct(tree)


def _find_resource_attrs(doc: dict[str, Any], resource_type: str, resource_name: str) -> dict[str, Any]:
    resources = doc.get("resource")
    if not isinstance(resources, list):
        raise ValueError("document has no resource list")

    for block in resources:
        if not isinstance(block, dict):
            continue
        for block_resource_type, by_name in block.items():
            if _strip_wrapping_quotes(str(block_resource_type)) != resource_type:
                continue
            if not isinstance(by_name, dict):
                continue
            for block_resource_name, attrs in by_name.items():
                if _strip_wrapping_quotes(str(block_resource_name)) != resource_name:
                    continue
                if isinstance(attrs, dict):
                    return attrs

    raise ValueError(f"resource {resource_type}.{resource_name} not found")


def _find_module_attrs(doc: dict[str, Any], module_name: str) -> dict[str, Any]:
    modules = doc.get("module")
    if not isinstance(modules, list):
        raise ValueError(f"module {module_name} not found")

    for block in modules:
        if not isinstance(block, dict):
            continue
        for block_module_name, attrs in block.items():
            if _strip_wrapping_quotes(str(block_module_name)) != module_name:
                continue
            if isinstance(attrs, dict):
                return attrs

    raise ValueError(f"module {module_name} not found")


def _build_resource_block_dict(resource_type: str, resource_name: str, attrs: dict[str, Any]) -> dict[str, Any]:
    attrs_with_marker = {_BLOCK_MARKER: True, **attrs}
    return {"resource": [{_quoted_label(resource_type): {_quoted_label(resource_name): attrs_with_marker}}]}


def _build_module_block_dict(module_name: str, attrs: dict[str, Any]) -> dict[str, Any]:
    attrs_with_marker = {_BLOCK_MARKER: True, **attrs}
    return {"module": [{_quoted_label(module_name): attrs_with_marker}]}


def _find_terraform_attrs(doc: dict[str, Any]) -> dict[str, Any] | None:
    terraform = doc.get("terraform")
    if not isinstance(terraform, list) or not terraform:
        return None
    first = terraform[0]
    if not isinstance(first, dict):
        return None
    return first


def _build_terraform_block_dict(attrs: dict[str, Any]) -> dict[str, Any]:
    return {"terraform": [{_BLOCK_MARKER: True, **attrs}]}


def _ensure_block_dict(block_data: Any) -> dict[str, Any]:
    if isinstance(block_data, dict):
        return block_data
    return {_BLOCK_MARKER: True}


def read_resource_block_attrs(original: str, resource_type: str, resource_name: str) -> dict[str, Any]:
    doc = hcl2.loads(original)
    attrs = copy.deepcopy(_find_resource_attrs(doc, resource_type, resource_name))
    attrs.pop(_BLOCK_MARKER, None)
    return attrs


def read_module_block_attrs(original: str, module_name: str) -> dict[str, Any]:
    doc = hcl2.loads(original)
    attrs = copy.deepcopy(_find_module_attrs(doc, module_name))
    attrs.pop(_BLOCK_MARKER, None)
    return attrs


def read_resource_block_values(original: str, resource_type: str, resource_name: str) -> dict[str, HclValue]:
    attrs = read_resource_block_attrs(original, resource_type, resource_name)
    return {key: _parse_hcl_value(value) for key, value in attrs.items()}


def read_module_block_values(original: str, module_name: str) -> dict[str, HclValue]:
    attrs = read_module_block_attrs(original, module_name)
    return {key: _parse_hcl_value(value) for key, value in attrs.items()}


def update_resource_block(
    original: str,
    resource_type: str,
    resource_name: str,
    mutation: Callable[[dict[str, Any]], None],
) -> str:
    attrs = read_resource_block_attrs(original, resource_type, resource_name)
    mutation(attrs)
    block_dict = _build_resource_block_dict(resource_type, resource_name, attrs)
    return splice_block(original, block_dict, ("resource", resource_type, resource_name))


def rename_resource_block(original: str, resource_type: str, old_name: str, new_name: str) -> str:
    attrs = read_resource_block_attrs(original, resource_type, old_name)
    new_block = _build_resource_block_dict(resource_type, new_name, attrs)
    return splice_block(original, new_block, ("resource", resource_type, old_name))


def update_module_block(
    original: str,
    module_name: str,
    mutation: Callable[[dict[str, Any]], None],
) -> str:
    attrs = read_module_block_attrs(original, module_name)
    mutation(attrs)
    block_dict = _build_module_block_dict(module_name, attrs)
    return splice_block(original, block_dict, ("module", module_name))


def _attribute_rhs_expression(attr_name: str, attr_value: str) -> ExprTermRule:
    fragment_hcl = f"{_HCL_PATCH_FRAGMENT_BLOCK} {{\n  {attr_name} = {attr_value}\n}}\n"
    frag_tree = hcl2.parses(fragment_hcl, discard_comments=False)
    patch_block = first_block(frag_tree)
    for child in patch_block.body.children:
        if isinstance(child, AttributeRule) and child.identifier.serialize() == attr_name:
            return child.expression
    msg = f"failed to parse fragment for attribute {attr_name!r}"
    raise ValueError(msg)


def patch_module_block_attributes(original: str, module_name: str, attributes: dict[str, str]) -> str:
    """Swap attribute RHS nodes in-place so inter-attribute comments stay in the body."""

    tree = hcl2.parses(original, discard_comments=False)
    block_index = find_block_index(tree, ("module", module_name))
    block = tree.body.children[block_index]
    if not isinstance(block, BlockRule):
        raise ValueError(f"expected module block, got {type(block).__name__}")
    for attr_name, attr_value in attributes.items():
        new_expr = _attribute_rhs_expression(attr_name, attr_value)
        for child in block.body.children:
            if isinstance(child, AttributeRule) and child.identifier.serialize() == attr_name:
                new_expr.set_index(2)
                new_expr.set_parent(child)
                child._children[2] = new_expr
                break
        else:
            raise ValueError(f"attribute {attr_name!r} not found in module {module_name!r}")
    return hcl2.reconstruct(tree)


def rename_module_block(original: str, old_name: str, new_name: str) -> str:
    attrs = read_module_block_attrs(original, old_name)
    new_block = _build_module_block_dict(new_name, attrs)
    return splice_block(original, new_block, ("module", old_name))


def add_resource_block(original: str, resource_type: str, resource_name: str, attrs: dict[str, Any]) -> str:
    tree = hcl2.parses(original, discard_comments=False)
    label_path = ("resource", resource_type, resource_name)
    if block_exists(tree, label_path):
        raise ValueError(f"block already exists for labels {list(label_path)}")
    return _append_block(original, _build_resource_block_dict(resource_type, resource_name, attrs))


def delete_resource_block(original: str, resource_type: str, resource_name: str) -> str:
    return _delete_block(original, ("resource", resource_type, resource_name))


def add_module_block(original: str, module_name: str, attrs: dict[str, Any]) -> str:
    tree = hcl2.parses(original, discard_comments=False)
    label_path = ("module", module_name)
    if block_exists(tree, label_path):
        raise ValueError(f"block already exists for labels {list(label_path)}")
    return _append_block(original, _build_module_block_dict(module_name, attrs))


def delete_module_block(original: str, module_name: str) -> str:
    return _delete_block(original, ("module", module_name))


def delete_variable_block(original: str, var_name: str) -> str:
    return _delete_block(original, ("variable", var_name))


def delete_output_block(original: str, output_name: str) -> str:
    return _delete_block(original, ("output", output_name))


def delete_provider_block(original: str, provider_name: str) -> str:
    return _delete_block(original, ("provider", provider_name))


def delete_terraform_block(original: str) -> str:
    return _delete_block(original, ("terraform",))


def update_required_providers(
    original: str,
    providers: dict[str, dict[str, Any]],
    *,
    required_version: str | None = None,
) -> str:
    doc = hcl2.loads(original)
    terraform_attrs = copy.deepcopy(_find_terraform_attrs(doc)) or {}
    terraform_attrs.pop(_BLOCK_MARKER, None)

    if required_version is not None:
        terraform_attrs["required_version"] = _to_hcl_string(required_version)

    required_providers = terraform_attrs.get("required_providers")
    provider_block: dict[str, Any]
    if isinstance(required_providers, list) and required_providers:
        provider_block = _ensure_block_dict(copy.deepcopy(required_providers[0]))
    else:
        provider_block = {_BLOCK_MARKER: True}

    for provider_name, patch in providers.items():
        existing = provider_block.get(provider_name, {})
        provider_attrs = copy.deepcopy(existing) if isinstance(existing, dict) else {}
        for key, value in patch.items():
            provider_attrs[key] = _to_hcl_string(value)
        provider_block[provider_name] = provider_attrs

    terraform_attrs["required_providers"] = [provider_block]
    block_dict = _build_terraform_block_dict(terraform_attrs)

    tree = hcl2.parses(original, discard_comments=False)
    if block_exists(tree, ("terraform",)):
        return splice_block(original, block_dict, ("terraform",))
    return _append_block(original, block_dict)


def remove_required_providers(original: str, provider: str) -> str:
    doc = hcl2.loads(original)
    terraform_attrs = copy.deepcopy(_find_terraform_attrs(doc))
    if terraform_attrs is None:
        raise ValueError(f"provider {provider} not found")

    required_providers = terraform_attrs.get("required_providers")
    if not isinstance(required_providers, list) or not required_providers:
        raise ValueError(f"provider {provider} not found")

    provider_block = _ensure_block_dict(copy.deepcopy(required_providers[0]))
    if provider not in provider_block:
        raise ValueError(f"provider {provider} not found")

    provider_block.pop(provider)
    marker_only_block = list(provider_block.keys()) == [_BLOCK_MARKER]
    if marker_only_block:
        return delete_required_providers_section(original)

    terraform_attrs.pop(_BLOCK_MARKER, None)
    terraform_attrs["required_providers"] = [provider_block]
    block_dict = _build_terraform_block_dict(terraform_attrs)
    return splice_block(original, block_dict, ("terraform",))


def _build_backend_entry(backend_type: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    return [{_quoted_label(backend_type): {_BLOCK_MARKER: True, **config}}]


def add_backend_block(original: str, backend_type: str, config: dict[str, Any]) -> str:
    doc = hcl2.loads(original)
    terraform_attrs = copy.deepcopy(_find_terraform_attrs(doc)) or {}
    terraform_attrs.pop(_BLOCK_MARKER, None)
    if "backend" in terraform_attrs:
        raise ValueError("backend block already exists")
    terraform_attrs["backend"] = _build_backend_entry(backend_type, config)
    block_dict = _build_terraform_block_dict(terraform_attrs)
    tree = hcl2.parses(original, discard_comments=False)
    if block_exists(tree, ("terraform",)):
        return splice_block(original, block_dict, ("terraform",))
    return _append_block(original, block_dict)


def update_backend_block(original: str, backend_type: str, config: dict[str, Any]) -> str:
    doc = hcl2.loads(original)
    terraform_attrs = copy.deepcopy(_find_terraform_attrs(doc))
    if terraform_attrs is None or "backend" not in terraform_attrs:
        raise ValueError("no backend block found")
    terraform_attrs.pop(_BLOCK_MARKER, None)
    terraform_attrs["backend"] = _build_backend_entry(backend_type, config)
    block_dict = _build_terraform_block_dict(terraform_attrs)
    return splice_block(original, block_dict, ("terraform",))


def remove_backend_block(original: str) -> str:
    doc = hcl2.loads(original)
    terraform_attrs = copy.deepcopy(_find_terraform_attrs(doc))
    if terraform_attrs is None or "backend" not in terraform_attrs:
        raise ValueError("no backend block found")
    terraform_attrs.pop(_BLOCK_MARKER, None)
    terraform_attrs.pop("backend")
    if not terraform_attrs:
        return _delete_block(original, ("terraform",))
    block_dict = _build_terraform_block_dict(terraform_attrs)
    return splice_block(original, block_dict, ("terraform",))


def delete_required_providers_section(original: str) -> str:
    doc = hcl2.loads(original)
    terraform_attrs = copy.deepcopy(_find_terraform_attrs(doc))
    if terraform_attrs is None:
        raise ValueError("required_providers section not found")

    terraform_attrs.pop(_BLOCK_MARKER, None)
    if "required_providers" not in terraform_attrs:
        raise ValueError("required_providers section not found")

    terraform_attrs.pop("required_providers")
    if not terraform_attrs:
        return _delete_block(original, ("terraform",))

    block_dict = _build_terraform_block_dict(terraform_attrs)
    return splice_block(original, block_dict, ("terraform",))
