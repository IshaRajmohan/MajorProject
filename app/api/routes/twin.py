"""
OWNER: Person C
GET /twin/{case_id}
GET /twin/{case_id}/facts/{fact_key_id}
GET /twin/{case_id}/facts/{fact_key_id}/decisions
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import require_role

router = APIRouter()

@router.get("/{case_id}")
async def get_twin(case_id: str, db: AsyncSession = Depends(get_db),
                    user=Depends(require_role(
                        "police", "court", "lawyer", "forensic", "citizen", "admin"))):
    raise NotImplementedError
