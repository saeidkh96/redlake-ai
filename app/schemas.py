from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DatasetCreate(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=63,
        pattern=r"^[a-z][a-z0-9_-]*$",
        examples=["customer-events"],
    )
    description: str | None = Field(default=None, max_length=2000)


class DatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ContractField(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    data_type: Literal["string", "integer", "number", "boolean", "object", "array"]
    required: bool = True


class DataContractCreate(BaseModel):
    version: str = Field(min_length=1, max_length=32, pattern=r"^v?\d+\.\d+\.\d+$")
    fields: list[ContractField] = Field(min_length=1)
    allow_extra_fields: bool = True

    @field_validator("version")
    @classmethod
    def normalize_version(cls, value: str) -> str:
        return value if value.startswith("v") else f"v{value}"

    @model_validator(mode="after")
    def unique_field_names(self) -> DataContractCreate:
        names = [field.name for field in self.fields]
        if len(names) != len(set(names)):
            raise ValueError("Contract field names must be unique")
        return self


class DataContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dataset_id: UUID
    version: str
    schema_definition: dict[str, Any]
    is_active: bool
    created_at: datetime


class QualityCheckResponse(BaseModel):
    name: str
    passed: bool
    severity: str
    details: dict[str, Any]


class QualityReportResponse(BaseModel):
    status: Literal["passed", "failed"]
    checks: list[QualityCheckResponse]
    failed_checks: list[str]


class IngestionResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    source_kind: str
    source_format: str
    source_filename: str
    status: Literal["succeeded", "rejected", "failed"]
    object_uri: str | None
    bytes_received: int
    row_count: int
    checksum_sha256: str
    schema_profile: dict[str, Any]
    quality_report: QualityReportResponse
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    replayed: bool = False


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded"]
    dependencies: dict[str, str]


class ErrorResponse(BaseModel):
    detail: str
