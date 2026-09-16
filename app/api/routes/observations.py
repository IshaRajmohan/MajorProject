"""
OWNER: Person C
POST /observations
GET  /observations?case_id=&fact_key_id=
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import require_role
from app.schemas.observation import ObservationCreate

router = APIRouter()

@router.post("")
async def create_observation(
    payload: ObservationCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("police", "court", "lawyer", "forensic", "admin")),
):
    raise NotImplementedError

@router.get("")
async def list_observations(
    case_id: str, fact_key_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("police", "court", "lawyer", "forensic", "citizen", "admin")),
):
    raise NotImplementedError
