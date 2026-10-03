from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db.models import DataContract, Dataset, IngestionRun
from app.schemas import (
    DataContractCreate,
    DataContractResponse,
    DatasetCreate,
    DatasetResponse,
    ErrorResponse,
    IngestionResponse,
)
from app.services.ingestion import IdempotencyConflict, UnsupportedSourceFormat, ingest_file

router = APIRouter(tags=["catalog", "ingestion"])


def _dataset_or_404(db: Session, dataset_name: str) -> Dataset:
    dataset = db.scalar(select(Dataset).where(Dataset.name == dataset_name))
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
    return dataset


def _ingestion_response(run: IngestionRun, *, replayed: bool = False) -> IngestionResponse:
    return IngestionResponse(
        id=run.id,
        dataset_id=run.dataset_id,
        source_kind=run.source_kind,
        source_format=run.source_format,
        source_filename=run.source_filename,
        status=run.status,
        object_uri=run.object_uri,
        bytes_received=run.bytes_received,
        row_count=run.row_count,
        checksum_sha256=run.checksum_sha256,
        schema_profile=run.schema_profile,
        quality_report=run.quality_report,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
        replayed=replayed,
    )


@router.post(
    "/datasets",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def create_dataset(payload: DatasetCreate, db: Session = Depends(get_db)) -> Dataset:
    dataset = Dataset(**payload.model_dump())
    db.add(dataset)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Dataset name already exists"
        ) from error
    db.refresh(dataset)
    return dataset


@router.get("/datasets", response_model=list[DatasetResponse])
async def list_datasets(db: Session = Depends(get_db)) -> Sequence[Dataset]:
    return db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()


@router.get("/datasets/{dataset_name}", response_model=DatasetResponse)
async def get_dataset(dataset_name: str, db: Session = Depends(get_db)) -> Dataset:
    return _dataset_or_404(db, dataset_name)


@router.post(
    "/datasets/{dataset_name}/contracts",
    response_model=DataContractResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def create_contract(
    dataset_name: str,
    payload: DataContractCreate,
    db: Session = Depends(get_db),
) -> DataContract:
    dataset = _dataset_or_404(db, dataset_name)
    contract = DataContract(
        dataset_id=dataset.id,
        version=payload.version,
        schema_definition={
            "fields": [field.model_dump() for field in payload.fields],
            "allow_extra_fields": payload.allow_extra_fields,
        },
        is_active=True,
    )
    db.execute(
        update(DataContract)
        .where(DataContract.dataset_id == dataset.id, DataContract.is_active.is_(True))
        .values(is_active=False)
    )
    db.add(contract)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Contract version already exists for this dataset",
        ) from error
    db.refresh(contract)
    return contract


@router.get("/datasets/{dataset_name}/contracts", response_model=list[DataContractResponse])
async def list_contracts(
    dataset_name: str,
    db: Session = Depends(get_db),
) -> Sequence[DataContract]:
    dataset = _dataset_or_404(db, dataset_name)
    return db.scalars(
        select(DataContract)
        .where(DataContract.dataset_id == dataset.id)
        .order_by(DataContract.created_at.desc())
    ).all()


@router.post(
    "/datasets/{dataset_name}/ingestions",
    response_model=IngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def upload_file(
    dataset_name: str,
    response: Response,
    request: Request,
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    dataset = _dataset_or_404(db, dataset_name)
    filename = file.filename or "upload"
    limit = request.app.state.settings.max_upload_bytes
    body = await file.read(limit + 1)
    if len(body) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds the {limit}-byte v0.1.0 limit",
        )

    try:
        run, replayed = ingest_file(
            db=db,
            storage=request.app.state.object_store,
            dataset=dataset,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
            body=body,
            idempotency_key=idempotency_key,
        )
    except UnsupportedSourceFormat as error:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(error)
        ) from error
    except IdempotencyConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    if replayed:
        response.status_code = status.HTTP_200_OK
    return _ingestion_response(run, replayed=replayed)


@router.get("/datasets/{dataset_name}/ingestions", response_model=list[IngestionResponse])
async def list_ingestions(
    dataset_name: str,
    db: Session = Depends(get_db),
) -> list[IngestionResponse]:
    dataset = _dataset_or_404(db, dataset_name)
    runs = db.scalars(
        select(IngestionRun)
        .where(IngestionRun.dataset_id == dataset.id)
        .order_by(IngestionRun.started_at.desc())
    ).all()
    return [_ingestion_response(run) for run in runs]


@router.get("/ingestions/{ingestion_id}", response_model=IngestionResponse)
async def get_ingestion(ingestion_id: UUID, db: Session = Depends(get_db)) -> IngestionResponse:
    run = db.get(IngestionRun, ingestion_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ingestion run not found")
    return _ingestion_response(run)
