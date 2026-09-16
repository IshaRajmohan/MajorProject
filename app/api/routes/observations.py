"""
OWNER: Person C
POST /observations
GET  /observations?case_id=&fact_key_id=
GET  /observations/{observation_id}
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User
from app.schemas.observation import (
    IngestResponse,
    ObservationCreate,
    ObservationResponse,
    SyncResultOut,
)
from app.services.observation_service import ObservationService

router = APIRouter()

OBSERVATION_WRITERS = ("police", "court", "lawyer", "forensic", "admin")
OBSERVATION_READERS = ("police", "court", "lawyer", "forensic", "citizen", "admin")


def _http_from_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(code, message)


def _ingest_response(result: dict) -> IngestResponse:
    sync = result["sync"]
    winner = sync.winner
    return IngestResponse(
        observation=ObservationResponse.model_validate(result["observation"]),
        sync=SyncResultOut(
            decision=sync.decision,
            c1=sync.c1,
            c2=sync.c2,
            explanation=sync.explanation,
            winner_observation_id=None if winner is None else winner.observation_id,
            scores=sync.scores,
        ),
        twin_updated=result["twin_updated"],
        fact_key_id=result["fact_key_id"],
        is_duplicate=result.get("is_duplicate", False),
    )


@router.post(
    "",
    response_model=IngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an observation and run CAMS",
)
async def create_observation(
    payload: ObservationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(*OBSERVATION_WRITERS)),
):
    service = ObservationService(db)
    try:
        result = await service.ingest(payload, user)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return _ingest_response(result)


@router.get(
    "",
    response_model=list[ObservationResponse],
    summary="List observations for a case",
)
async def list_observations(
    case_id: str,
    fact_key_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*OBSERVATION_READERS)),
):
    service = ObservationService(db)
    try:
        rows = await service.list_observations(case_id, fact_key_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return rows


@router.get(
    "/{observation_id}",
    response_model=ObservationResponse,
    summary="Get a single observation",
)
async def get_observation(
    observation_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*OBSERVATION_READERS)),
):
    service = ObservationService(db)
    try:
        return await service.get_observation(observation_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
