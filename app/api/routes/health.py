from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from app.schemas import ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health/live", summary="Liveness probe")
async def liveness(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "service": request.app.state.settings.app_name,
        "version": request.app.state.settings.app_version,
    }


@router.get("/health/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness(request: Request) -> ReadinessResponse:
    dependencies: dict[str, str] = {}
    try:
        with request.app.state.database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        dependencies["database"] = "ok"
    except Exception:
        dependencies["database"] = "unavailable"

    try:
        request.app.state.object_store.ensure_ready()
        dependencies["object_store"] = "ok"
    except Exception:
        dependencies["object_store"] = "unavailable"

    response = ReadinessResponse(
        status="ok" if all(value == "ok" for value in dependencies.values()) else "degraded",
        dependencies=dependencies,
    )
    if response.status != "ok":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=response.model_dump()
        )
    return response
