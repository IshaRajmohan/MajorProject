"""
OWNER: Person A
POST   /cases
GET    /cases
GET    /cases/{id}
PUT    /cases/{id}
POST   /cases/{id}/entities
GET    /cases/{id}/entities
GET    /cases/{id}/entities/{entity_id}
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_role
from app.models.case import Case, Entity
from app.models.user import User
from app.schemas.case import (
    CaseCreate,
    CaseResponse,
    CaseUpdate,
    EntityCreate,
    EntityResponse,
)

router = APIRouter()

CASE_READERS = ("police", "court", "lawyer", "forensic", "citizen", "admin")
CASE_WRITERS = ("court", "admin", "police")
ENTITY_WRITERS = ("police", "court", "lawyer", "forensic", "admin")


async def _get_case_or_404(db: AsyncSession, case_id: str) -> Case:
    result = await db.execute(select(Case).where(Case.id == case_id))
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case


@router.post(
    "",
    response_model=CaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a case",
)
async def create_case(
    payload: CaseCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*CASE_WRITERS)),
):
    existing = await db.execute(select(Case).where(Case.case_number == payload.case_number))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Case number already exists")

    case = Case(
        case_number=payload.case_number,
        title=payload.title,
        status=payload.status,
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return case


@router.get("", response_model=list[CaseResponse], summary="List cases")
async def list_cases(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*CASE_READERS)),
):
    result = await db.execute(select(Case).order_by(Case.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{case_id}", response_model=CaseResponse, summary="Get case by id")
async def get_case(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*CASE_READERS)),
):
    return await _get_case_or_404(db, case_id)


@router.put("/{case_id}", response_model=CaseResponse, summary="Update a case")
async def update_case(
    case_id: str,
    payload: CaseUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*CASE_WRITERS)),
):
    case = await _get_case_or_404(db, case_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No fields to update")
    for key, value in data.items():
        setattr(case, key, value)
    await db.commit()
    await db.refresh(case)
    return case


@router.post(
    "/{case_id}/entities",
    response_model=EntityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add an entity to a case",
)
async def create_entity(
    case_id: str,
    payload: EntityCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*ENTITY_WRITERS)),
):
    await _get_case_or_404(db, case_id)
    entity = Entity(
        case_id=case_id,
        entity_type=payload.entity_type,
        label=payload.label,
        attributes=payload.attributes or {},
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return entity


@router.get(
    "/{case_id}/entities",
    response_model=list[EntityResponse],
    summary="List entities for a case",
)
async def list_entities(
    case_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*CASE_READERS)),
):
    await _get_case_or_404(db, case_id)
    result = await db.execute(select(Entity).where(Entity.case_id == case_id))
    return list(result.scalars().all())


@router.get(
    "/{case_id}/entities/{entity_id}",
    response_model=EntityResponse,
    summary="Get a single entity",
)
async def get_entity(
    case_id: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*CASE_READERS)),
):
    await _get_case_or_404(db, case_id)
    result = await db.execute(
        select(Entity).where(Entity.id == entity_id, Entity.case_id == case_id)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")
    return entity
