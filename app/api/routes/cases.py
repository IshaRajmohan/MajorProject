"""
OWNER: Person A
POST /cases
GET  /cases/{id}
GET  /cases/{id}/entities
POST /cases/{id}/entities
"""
from fastapi import APIRouter, Depends
from app.core.security import require_role

router = APIRouter()

@router.post("")
async def create_case(payload: dict, user=Depends(require_role("court", "admin"))):
    raise NotImplementedError

@router.get("/{case_id}")
async def get_case(case_id: str, user=Depends(require_role(
    "police", "court", "lawyer", "forensic", "citizen", "admin"))):
    raise NotImplementedError
