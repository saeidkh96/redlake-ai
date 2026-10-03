from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.observability import INGESTION_RUNS
from app.db.models import DataContract, Dataset, IngestionRun
from app.services.contracts import PayloadParseError, evaluate_quality, parse_payload
from app.storage import ObjectStore

logger = logging.getLogger(__name__)


class IdempotencyConflict(ValueError):
    pass


class UnsupportedSourceFormat(ValueError):
    pass


def source_format_from_filename(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    formats = {".csv": "csv", ".json": "json"}
    try:
        return formats[suffix]
    except KeyError as error:
        raise UnsupportedSourceFormat(
            "Only .csv and .json files are supported in v0.1.0"
        ) from error


def _safe_filename(filename: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name)
    return normalized[:180] or "upload"


def _quality_report_for_parse_error(message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "checks": [
            {
                "name": "payload.parse",
                "passed": False,
                "severity": "error",
                "details": {"message": message},
            }
        ],
        "failed_checks": ["payload.parse"],
    }


def get_active_contract(db: Session, dataset_id: object) -> DataContract | None:
    return db.scalar(
        select(DataContract)
        .where(DataContract.dataset_id == dataset_id, DataContract.is_active.is_(True))
        .order_by(DataContract.created_at.desc())
    )


def ingest_file(
    *,
    db: Session,
    storage: ObjectStore,
    dataset: Dataset,
    filename: str,
    content_type: str,
    body: bytes,
    idempotency_key: str | None,
) -> tuple[IngestionRun, bool]:
    """Capture raw bytes once and make the catalog record the source of truth for its outcome."""

    source_format = source_format_from_filename(filename)
    checksum = hashlib.sha256(body).hexdigest()

    if idempotency_key:
        existing = db.scalar(
            select(IngestionRun).where(
                IngestionRun.dataset_id == dataset.id,
                IngestionRun.idempotency_key == idempotency_key,
            )
        )
        if existing:
            if existing.checksum_sha256 != checksum:
                raise IdempotencyConflict(
                    "The supplied Idempotency-Key was already used with different content"
                )
            return existing, True

    contract = get_active_contract(db, dataset.id)
    try:
        parsed = parse_payload(source_format, body)
        quality_report = evaluate_quality(
            parsed,
            contract.schema_definition if contract else None,
        )
        schema_profile = parsed.schema_profile
        row_count = len(parsed.rows)
    except PayloadParseError as error:
        quality_report = _quality_report_for_parse_error(str(error))
        schema_profile = {"field_count": 0, "fields": []}
        row_count = 0

    run = IngestionRun(
        dataset_id=dataset.id,
        source_kind="file",
        source_format=source_format,
        source_filename=_safe_filename(filename),
        idempotency_key=idempotency_key,
        checksum_sha256=checksum,
        status="processing",
        bytes_received=len(body),
        row_count=row_count,
        schema_profile=schema_profile,
        quality_report=quality_report,
    )
    db.add(run)
    db.flush()

    now = datetime.now(UTC)
    prefix = "raw" if quality_report["status"] == "passed" else "quarantine"
    object_key = f"{prefix}/{dataset.name}/{now:%Y/%m/%d}/{run.id}/{run.source_filename}"
    try:
        stored_object = storage.put_bytes(object_key, body, content_type)
    except Exception as error:
        logger.exception("Object storage write failed", extra={"ingestion_run_id": str(run.id)})
        run.status = "failed"
        run.error_message = "Raw object storage write failed"
        run.completed_at = datetime.now(UTC)
        db.commit()
        INGESTION_RUNS.labels(status=run.status, source_format=run.source_format).inc()
        raise RuntimeError("Raw object storage write failed") from error

    run.object_uri = stored_object.uri
    run.status = "succeeded" if quality_report["status"] == "passed" else "rejected"
    run.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(run)
    INGESTION_RUNS.labels(status=run.status, source_format=run.source_format).inc()
    logger.info(
        "Ingestion run completed",
        extra={"ingestion_run_id": str(run.id), "status": run.status, "dataset": dataset.name},
    )
    return run, False
