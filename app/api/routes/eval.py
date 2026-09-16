"""
OWNER: Person D
POST /eval/run -> triggers app.eval.runner and returns metrics as JSON.
"""
from fastapi import APIRouter, Depends
from app.core.security import require_role

router = APIRouter()

@router.post("/run")
async def run_eval(user=Depends(require_role("admin", "court"))):
    raise NotImplementedError
