"""
OWNER: Person C
GET /twin/{case_id}
GET /twin/{case_id}/facts/{fact_key_id}
GET /twin/{case_id}/facts/{fact_key_id}/decisions
GET /twin/{case_id}/facts/{fact_key_id}/versions
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User
from app.schemas.observation import SyncDecisionOut, TwinFactOut, TwinStateOut, TwinStateVersionOut
from app.services.observation_service import ObservationService

router = APIRouter()

TWIN_READERS = ("police", "court", "lawyer", "forensic", "citizen", "admin")


def _http_from_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    code = status.HTTP_404_NOT_FOUND if "not found" in message.lower() else status.HTTP_400_BAD_REQUEST
    return HTTPException(code, message)


@router.get("/{case_id}", response_model=TwinStateOut, summary="Get Justice Twin for a case")
async def get_twin(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*TWIN_READERS)),
):
    service = ObservationService(db)
    try:
        facts = await service.get_twin_facts(case_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return TwinStateOut(case_id=case_id, facts=[TwinFactOut(**f) for f in facts])


@router.get(
    "/{case_id}/facts/{fact_key_id}",
    response_model=TwinFactOut,
    summary="Get one twin fact",
)
async def get_twin_fact(
    case_id: str,
    fact_key_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*TWIN_READERS)),
):
    service = ObservationService(db)
    try:
        fact = await service.get_twin_fact(case_id, fact_key_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
    return TwinFactOut(**fact)


@router.get(
    "/{case_id}/facts/{fact_key_id}/decisions",
    response_model=list[SyncDecisionOut],
    summary="List CAMS sync decisions for a fact",
)
async def list_fact_decisions(
    case_id: str,
    fact_key_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*TWIN_READERS)),
):
    service = ObservationService(db)
    try:
        return await service.list_decisions(case_id, fact_key_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc


@router.get(
    "/{case_id}/facts/{fact_key_id}/versions",
    response_model=list[TwinStateVersionOut],
    summary="List ODFS versions for a fact",
)
async def list_fact_versions(
    case_id: str,
    fact_key_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*TWIN_READERS)),
):
    service = ObservationService(db)
    try:
        return await service.list_versions(case_id, fact_key_id)
    except ValueError as exc:
        raise _http_from_value_error(exc) from exc
