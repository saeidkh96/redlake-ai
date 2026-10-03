from __future__ import annotations

import pytest

from app.services.contracts import PayloadParseError, evaluate_quality, parse_payload


def test_csv_profile_infers_scalar_types() -> None:
    parsed = parse_payload(
        "csv",
        b"id,active,score,name\n1,true,9.5,Ada\n2,false,10.0,Grace\n",
    )

    assert len(parsed.rows) == 2
    assert parsed.schema_profile["field_count"] == 4
    by_name = {field["name"]: field for field in parsed.schema_profile["fields"]}
    assert by_name["id"]["data_type"] == "integer"
    assert by_name["active"]["data_type"] == "boolean"
    assert by_name["score"]["data_type"] == "number"


def test_quality_rejects_missing_required_value() -> None:
    parsed = parse_payload("json", b'[{"id": 1, "event_type": null}]')
    report = evaluate_quality(
        parsed,
        {
            "allow_extra_fields": False,
            "fields": [
                {"name": "id", "data_type": "integer", "required": True},
                {"name": "event_type", "data_type": "string", "required": True},
            ],
        },
    )

    assert report["status"] == "failed"
    assert "contract.required_values.event_type" in report["failed_checks"]


def test_csv_rejects_duplicate_headers() -> None:
    with pytest.raises(PayloadParseError, match="unique"):
        parse_payload("csv", b"id,id\n1,2\n")


def test_number_contract_accepts_integer_values() -> None:
    parsed = parse_payload("json", b'[{"value": 1}, {"value": 2.5}]')
    report = evaluate_quality(
        parsed,
        {
            "allow_extra_fields": False,
            "fields": [{"name": "value", "data_type": "number", "required": True}],
        },
    )

    assert report["status"] == "passed"
