from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any


class PayloadParseError(ValueError):
    """Raised when a CSV or JSON upload cannot be safely interpreted as tabular records."""


@dataclass(frozen=True)
class ParsedPayload:
    source_format: str
    rows: list[dict[str, Any]]
    field_names: list[str]
    schema_profile: dict[str, Any]


_INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")
_NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")


def _coerce_csv_value(value: str | None) -> Any:
    if value is None or value == "":
        return None
    normalized = value.strip()
    if normalized.lower() == "true":
        return True
    if normalized.lower() == "false":
        return False
    if _INTEGER_PATTERN.match(normalized):
        try:
            return int(normalized)
        except ValueError:
            return value
    if _NUMBER_PATTERN.match(normalized):
        try:
            return float(normalized)
        except ValueError:
            return value
    return value


def _parse_csv(body: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PayloadParseError("CSV must be UTF-8 encoded") from error

    try:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise PayloadParseError("CSV must contain a header row")
        field_names = [name.strip() if name else "" for name in reader.fieldnames]
        if not all(field_names):
            raise PayloadParseError("CSV header names cannot be empty")
        if len(set(field_names)) != len(field_names):
            raise PayloadParseError("CSV header names must be unique")

        rows: list[dict[str, Any]] = []
        for line_number, raw_row in enumerate(reader, start=2):
            if None in raw_row:
                raise PayloadParseError(f"CSV row {line_number} has more values than the header")
            row = {
                field_name: _coerce_csv_value(raw_row.get(original_name))
                for field_name, original_name in zip(field_names, reader.fieldnames, strict=True)
            }
            if any(value is not None for value in row.values()):
                rows.append(row)
        return rows, field_names
    except csv.Error as error:
        raise PayloadParseError("CSV parsing failed") from error


def _parse_json(body: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PayloadParseError("JSON must be valid UTF-8 JSON") from error

    if isinstance(decoded, dict):
        rows = [decoded]
    elif isinstance(decoded, list) and all(isinstance(item, dict) for item in decoded):
        rows = decoded
    else:
        raise PayloadParseError("JSON input must be an object or an array of objects")

    field_names: list[str] = []
    for row in rows:
        for field_name in row:
            if not isinstance(field_name, str) or not field_name.strip():
                raise PayloadParseError("JSON field names must be non-empty strings")
            if field_name not in field_names:
                field_names.append(field_name)
    return rows, field_names


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unknown"


def _canonical_type(observed_types: set[str]) -> str:
    non_null_types = observed_types - {"null"}
    if not non_null_types:
        return "null"
    if non_null_types <= {"integer", "number"} and "number" in non_null_types:
        return "number"
    if len(non_null_types) == 1:
        return next(iter(non_null_types))
    return "mixed"


def _build_profile(rows: list[dict[str, Any]], field_names: list[str]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for field_name in field_names:
        types = {_value_type(row.get(field_name)) for row in rows}
        fields.append(
            {
                "name": field_name,
                "data_type": _canonical_type(types),
                "nullable": "null" in types or any(field_name not in row for row in rows),
                "observed_types": sorted(types),
            }
        )
    return {"field_count": len(field_names), "fields": fields}


def parse_payload(source_format: str, body: bytes) -> ParsedPayload:
    normalized_format = source_format.lower()
    if normalized_format == "csv":
        rows, field_names = _parse_csv(body)
    elif normalized_format == "json":
        rows, field_names = _parse_json(body)
    else:
        raise PayloadParseError(f"Unsupported source format: {source_format}")
    return ParsedPayload(
        source_format=normalized_format,
        rows=rows,
        field_names=field_names,
        schema_profile=_build_profile(rows, field_names),
    )


def _is_type_compatible(expected: str, observed: str) -> bool:
    if observed == "null":
        return True
    if expected == "number" and observed in {"integer", "number"}:
        return True
    return expected == observed


def evaluate_quality(
    parsed: ParsedPayload,
    contract_definition: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return an auditable quality report; failed error checks reject the ingestion."""

    checks: list[dict[str, Any]] = [
        {
            "name": "payload.non_empty",
            "passed": bool(parsed.rows),
            "severity": "error",
            "details": {"row_count": len(parsed.rows)},
        },
        {
            "name": "schema.field_names_unique",
            "passed": len(parsed.field_names) == len(set(parsed.field_names)),
            "severity": "error",
            "details": {"field_count": len(parsed.field_names)},
        },
    ]

    if contract_definition:
        expected_fields = contract_definition.get("fields", [])
        expected_by_name = {field["name"]: field for field in expected_fields}
        expected_names = set(expected_by_name)
        actual_names = set(parsed.field_names)
        missing_fields = sorted(expected_names - actual_names)
        checks.append(
            {
                "name": "contract.required_columns",
                "passed": not missing_fields,
                "severity": "error",
                "details": {"missing_fields": missing_fields},
            }
        )

        if not contract_definition.get("allow_extra_fields", True):
            unexpected_fields = sorted(actual_names - expected_names)
            checks.append(
                {
                    "name": "contract.no_unexpected_columns",
                    "passed": not unexpected_fields,
                    "severity": "error",
                    "details": {"unexpected_fields": unexpected_fields},
                }
            )

        for field_name, field in expected_by_name.items():
            if field_name not in actual_names:
                continue
            null_count = sum(row.get(field_name) is None for row in parsed.rows)
            if field["required"]:
                checks.append(
                    {
                        "name": f"contract.required_values.{field_name}",
                        "passed": null_count == 0,
                        "severity": "error",
                        "details": {"null_count": null_count},
                    }
                )

            observed = {
                _value_type(row.get(field_name))
                for row in parsed.rows
                if row.get(field_name) is not None
            }
            incompatible = sorted(
                value_type
                for value_type in observed
                if not _is_type_compatible(field["data_type"], value_type)
            )
            checks.append(
                {
                    "name": f"contract.data_type.{field_name}",
                    "passed": not incompatible,
                    "severity": "error",
                    "details": {
                        "expected": field["data_type"],
                        "observed": sorted(observed),
                        "incompatible": incompatible,
                    },
                }
            )

    failed_checks = [
        check["name"] for check in checks if not check["passed"] and check["severity"] == "error"
    ]
    return {
        "status": "passed" if not failed_checks else "failed",
        "checks": checks,
        "failed_checks": failed_checks,
    }
