from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest
from httpx import AsyncClient


async def create_dataset(client: AsyncClient, name: str = "customer-events") -> None:
    response = await client.post(
        "/api/v1/datasets",
        json={"name": name, "description": "Customer event records"},
    )
    assert response.status_code == 201, response.text


async def create_contract(client: AsyncClient, dataset_name: str = "customer-events") -> None:
    response = await client.post(
        f"/api/v1/datasets/{dataset_name}/contracts",
        json={
            "version": "0.1.0",
            "allow_extra_fields": False,
            "fields": [
                {"name": "event_id", "data_type": "integer", "required": True},
                {"name": "event_type", "data_type": "string", "required": True},
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["version"] == "v0.1.0"


@pytest.mark.anyio
async def test_health_and_openapi_are_available(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/health/live")).json()["status"] == "ok"
    readiness = await client.get("/api/v1/health/ready")
    assert readiness.status_code == 200
    assert readiness.json()["dependencies"] == {"database": "ok", "object_store": "ok"}
    assert (await client.get("/openapi.json")).status_code == 200
    assert "redlake_http_requests_total" in (await client.get("/metrics")).text


@pytest.mark.anyio
async def test_csv_ingestion_records_profile_and_raw_object(client: AsyncClient) -> None:
    await create_dataset(client)
    await create_contract(client)

    response = await client.post(
        "/api/v1/datasets/customer-events/ingestions",
        headers={"Idempotency-Key": "events-001"},
        files={
            "file": (
                "events.csv",
                b"event_id,event_type\n1,signup\n2,purchase\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["row_count"] == 2
    assert payload["quality_report"]["status"] == "passed"
    assert payload["object_uri"].startswith("file://")
    assert Path(urlparse(payload["object_uri"]).path).exists()
    assert payload["replayed"] is False


@pytest.mark.anyio
async def test_idempotency_replays_same_content_without_new_run(client: AsyncClient) -> None:
    await create_dataset(client)
    body = b'[{"event_id": 1, "event_type": "signup"}]'
    request = {
        "headers": {"Idempotency-Key": "events-001"},
        "files": {"file": ("events.json", body, "application/json")},
    }

    first = await client.post("/api/v1/datasets/customer-events/ingestions", **request)
    second = await client.post("/api/v1/datasets/customer-events/ingestions", **request)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["replayed"] is True
    runs = (await client.get("/api/v1/datasets/customer-events/ingestions")).json()
    assert len(runs) == 1


@pytest.mark.anyio
async def test_idempotency_key_with_changed_content_is_conflict(client: AsyncClient) -> None:
    await create_dataset(client)
    first = await client.post(
        "/api/v1/datasets/customer-events/ingestions",
        headers={"Idempotency-Key": "events-001"},
        files={"file": ("events.json", b'[{"event_id": 1}]', "application/json")},
    )
    second = await client.post(
        "/api/v1/datasets/customer-events/ingestions",
        headers={"Idempotency-Key": "events-001"},
        files={"file": ("events.json", b'[{"event_id": 2}]', "application/json")},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert "different content" in second.json()["detail"]


@pytest.mark.anyio
async def test_contract_failure_is_quarantined(client: AsyncClient) -> None:
    await create_dataset(client)
    await create_contract(client)

    response = await client.post(
        "/api/v1/datasets/customer-events/ingestions",
        files={"file": ("events.csv", b"event_id,event_type\n1,\n", "text/csv")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "rejected"
    assert payload["quality_report"]["status"] == "failed"
    assert "contract.required_values.event_type" in payload["quality_report"]["failed_checks"]
    assert "/quarantine/" in payload["object_uri"]


@pytest.mark.anyio
async def test_unsupported_file_type_is_rejected(client: AsyncClient) -> None:
    await create_dataset(client)

    response = await client.post(
        "/api/v1/datasets/customer-events/ingestions",
        files={"file": ("events.txt", b"nope", "text/plain")},
    )

    assert response.status_code == 415
