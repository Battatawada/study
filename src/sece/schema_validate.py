"""Optional JSON Schema validation for SECE artifacts."""

from __future__ import annotations

from typing import Any

from sece.validate import _report


def validate_schema(doc: dict[str, Any], schema: dict[str, Any], stage: str) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        warnings.append("jsonschema not installed — schema validation skipped")
        return _report(stage, errors, warnings)

    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as exc:
        errors.append(str(exc.message))
    return _report(stage, errors, warnings)
