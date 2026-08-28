#!/usr/bin/env python3
"""Validate PetroLab contracts without network access or third-party packages."""

from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
EXAMPLES = ROOT / "examples" / "contracts"
APPROVED = ROOT / "docs" / "design" / "reference" / "screens"

REQUIRED_DOCS = (
    "README.md",
    "AGENTS.md",
    "docs/product/PRODUCT_UX_MASTER_SPECIFICATION.md",
    "docs/product/DOMAIN_MODEL.md",
    "docs/product/SCIENTIFIC_RULES.md",
    "docs/product/USER_SCENARIOS.md",
    "docs/product/UI_ACCEPTANCE.md",
    "docs/architecture/ARCHITECTURE.md",
)

REQUIRED_APPROVED_SCREENS = (
    "analyses-approved-v1.png",
    "plotting-approved-v1.png",
    "thin-sections-approved-v1.png",
    "thin-sections-precision-point-v1.png",
    "thin-sections-media-attachment-v1.png",
)

REQUIRED_ARCHITECTURE_TERMS = (
    "Selection",
    "Work Group",
    "Plot Specification",
    "Spatial Annotation",
    "provenance",
    "React",
    "Tauri",
    "Python",
    "SQLite",
)


class ContractError(ValueError):
    pass


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read valid JSON from {path.relative_to(ROOT)}: {exc}")
    if not isinstance(value, dict):
        fail(f"JSON root must be an object: {path.relative_to(ROOT)}")
    return value


def validate_required_files() -> None:
    for relative in REQUIRED_DOCS:
        if not (ROOT / relative).is_file():
            fail(f"required document is missing: {relative}")
    for name in REQUIRED_APPROVED_SCREENS:
        if not (APPROVED / name).is_file():
            fail(f"approved design evidence is missing: {name}")
    drafts = sorted(APPROVED.glob("*draft*"))
    if drafts:
        fail("draft images are present in approved references: " + ", ".join(p.name for p in drafts))
    for image in APPROVED.glob("*.png"):
        if not image.with_suffix(".md").is_file():
            fail(f"approved screen has no metadata sidecar: {image.name}")


def validate_architecture_language() -> None:
    text = (ROOT / "docs/architecture/ARCHITECTURE.md").read_text(encoding="utf-8")
    missing = [term for term in REQUIRED_ARCHITECTURE_TERMS if term not in text]
    if missing:
        fail("architecture contract is missing terms: " + ", ".join(missing))


def _matches_type(value: Any, expected: str) -> bool:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return checks[expected](value)


def _resolve_ref(
    ref: str,
    root_schema: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if ref.startswith("#/"):
        target: Any = root_schema
        for token in ref[2:].split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
        return target, root_schema
    name, _, fragment = ref.partition("#")
    if name not in schemas:
        raise ContractError(f"unknown schema reference {ref!r}")
    target = schemas[name]
    external_root = target
    if fragment.startswith("/"):
        for token in fragment[1:].split("/"):
            target = target[token.replace("~1", "/").replace("~0", "~")]
    return target, external_root


def _validate(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
    path: str = "$",
) -> None:
    if "$ref" in schema:
        target, target_root = _resolve_ref(schema["$ref"], root_schema, schemas)
        _validate(value, target, target_root, schemas, path)
        return

    if "oneOf" in schema:
        matches = 0
        messages = []
        for candidate in schema["oneOf"]:
            try:
                _validate(value, candidate, root_schema, schemas, path)
                matches += 1
            except ContractError as exc:
                messages.append(str(exc))
        if matches != 1:
            raise ContractError(
                f"{path}: expected exactly one oneOf match, got {matches}; {' | '.join(messages)}"
            )
        return

    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_matches_type(value, option) for option in options):
            raise ContractError(f"{path}: expected type {options}, got {type(value).__name__}")

    if "const" in schema and value != schema["const"]:
        raise ContractError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ContractError(f"{path}: value {value!r} is not in enum")

    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise ContractError(f"{path}: missing required properties {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ContractError(f"{path}: unexpected properties {extras}")
        for key, child in value.items():
            if key in properties:
                _validate(child, properties[key], root_schema, schemas, f"{path}.{key}")

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ContractError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ContractError(f"{path}: too many items")
        if schema.get("uniqueItems"):
            canonical = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(canonical) != len(set(canonical)):
                raise ContractError(f"{path}: items must be unique")
        prefix = schema.get("prefixItems", [])
        for index, child_schema in enumerate(prefix):
            if index < len(value):
                _validate(value[index], child_schema, root_schema, schemas, f"{path}[{index}]")
        items = schema.get("items")
        if isinstance(items, dict):
            for index, child in enumerate(value[len(prefix) :], start=len(prefix)):
                _validate(child, items, root_schema, schemas, f"{path}[{index}]")
        elif items is False and len(value) > len(prefix):
            raise ContractError(f"{path}: additional array items are forbidden")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ContractError(f"{path}: string is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise ContractError(f"{path}: string is too long")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ContractError(f"{path}: string does not match {schema['pattern']!r}")
        if schema.get("format") == "uuid":
            try:
                uuid.UUID(value)
            except ValueError as exc:
                raise ContractError(f"{path}: invalid UUID") from exc
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ContractError(f"{path}: invalid date-time") from exc

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ContractError(f"{path}: value is below minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ContractError(f"{path}: value is below exclusive minimum")


def validate_schemas_and_examples() -> None:
    schemas = {path.name: load_json(path) for path in sorted(SCHEMAS.glob("*.schema.json"))}
    if not schemas:
        fail("no JSON Schemas found")
    ids: set[str] = set()
    for name, schema in schemas.items():
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            fail(f"schema {name} must declare JSON Schema 2020-12")
        schema_id = schema.get("$id")
        if not schema_id or schema_id in ids:
            fail(f"schema {name} has a missing or duplicate $id")
        ids.add(schema_id)
        if schema.get("type") != "object" or not schema.get("title"):
            fail(f"schema {name} must describe a titled object")

    examples = sorted(EXAMPLES.glob("*.json"))
    if not examples:
        fail("no contract examples found")
    for path in examples:
        instance = load_json(path)
        contract = instance.pop("$contract", None)
        if contract not in schemas:
            fail(f"{path.name} refers to unknown contract {contract!r}")
        try:
            _validate(instance, schemas[contract], schemas[contract], schemas)
        except ContractError as exc:
            fail(f"{path.name} does not satisfy {contract}: {exc}")


def main() -> None:
    validate_required_files()
    validate_architecture_language()
    validate_schemas_and_examples()
    print("PetroLab contracts are valid.")


if __name__ == "__main__":
    main()

