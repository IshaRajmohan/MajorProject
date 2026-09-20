"""
Case-specific RBAC for NyayaOS (Task 3).

Authorization flow for every real-case request:

    authenticated user → case exists → ACTIVE case_access (ADMIN bypasses)
    → case_role capability check → resource filtering → allow / 403 / 404

Status semantics:
  401 — no/invalid JWT or inactive user (handled by auth.get_current_active_user)
  404 — case (or access/submission target) does not exist
  403 — authenticated but not authorized for this case/resource

Capabilities are deny-by-default per case_role. Roles with restricted scope
(FORENSIC, CITIZEN) get *filtered* 200 responses through the pure ``filter_*``
helpers: FORENSIC only sees forensic fact keys / forensic-sourced observations
and documents; CITIZEN only sees citizen fact keys + CITIZEN_VISIBLE documents
and is denied observations, CAMS conflicts/history/provenance entirely.

Nothing here writes Twin/observation/CAMS state: mutations only happen through
the pipeline endpoints (ingest, resync, approved citizen submissions).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_active_user
from db import get_db
from db_models import AccessStatus, Case, CaseAccess, SystemRole, User

# ---- capabilities (deny-by-default per case_role) ----

CASE_VIEW = "case:view"
CASE_EDIT_META = "case:edit_meta"
CASE_MANAGE_ACCESS = "case:manage_access"
DOC_UPLOAD = "doc:upload"
DOC_VIEW = "doc:view"
DOC_SET_CITIZEN_VISIBILITY = "doc:set_citizen_visibility"
STAKEHOLDER_VIEW = "stakeholder:view"
OBS_VIEW = "obs:view"
TWIN_VIEW = "twin:view"
CONFLICT_VIEW = "conflict:view"
HISTORY_VIEW = "history:view"
PROVENANCE_VIEW = "provenance:view"
CAMS_INGEST = "cams:ingest"
CAMS_RESYNC = "cams:resync"
SUBMISSION_CREATE = "submission:create"
SUBMISSION_LIST = "submission:list"
SUBMISSION_REVIEW = "submission:review"

_ADMIN_CAPS: FrozenSet[str] = frozenset(
    {
        CASE_VIEW,
        CASE_EDIT_META,
        CASE_MANAGE_ACCESS,
        DOC_VIEW,
        STAKEHOLDER_VIEW,
        OBS_VIEW,
        TWIN_VIEW,
        CONFLICT_VIEW,
        HISTORY_VIEW,
        PROVENANCE_VIEW,
        SUBMISSION_LIST,
    }
)

_COURT_CAPS: FrozenSet[str] = frozenset(
    {
        CASE_VIEW,
        CASE_EDIT_META,
        CASE_MANAGE_ACCESS,
        DOC_UPLOAD,
        DOC_VIEW,
        DOC_SET_CITIZEN_VISIBILITY,
        STAKEHOLDER_VIEW,
        OBS_VIEW,
        TWIN_VIEW,
        CONFLICT_VIEW,
        HISTORY_VIEW,
        PROVENANCE_VIEW,
        CAMS_INGEST,
        CAMS_RESYNC,
        SUBMISSION_LIST,
        SUBMISSION_REVIEW,
    }
)

_FIELD_CAPS: FrozenSet[str] = frozenset(
    {
        CASE_VIEW,
        DOC_UPLOAD,
        DOC_VIEW,
        STAKEHOLDER_VIEW,
        OBS_VIEW,
        TWIN_VIEW,
        CONFLICT_VIEW,
        HISTORY_VIEW,
        PROVENANCE_VIEW,
        CAMS_INGEST,
        CAMS_RESYNC,
    }
)

_FORENSIC_CAPS: FrozenSet[str] = frozenset(
    {
        CASE_VIEW,
        DOC_UPLOAD,
        DOC_VIEW,
        STAKEHOLDER_VIEW,
        OBS_VIEW,
        TWIN_VIEW,
        CONFLICT_VIEW,
        HISTORY_VIEW,
        PROVENANCE_VIEW,
        CAMS_INGEST,
    }
)

_CITIZEN_CAPS: FrozenSet[str] = frozenset(
    {
        CASE_VIEW,
        DOC_VIEW,
        TWIN_VIEW,
        SUBMISSION_CREATE,
        SUBMISSION_LIST,
    }
)

ROLE_CAPABILITIES: Dict[SystemRole, FrozenSet[str]] = {
    SystemRole.ADMIN: _ADMIN_CAPS,
    SystemRole.COURT: _COURT_CAPS,
    SystemRole.POLICE: _FIELD_CAPS,
    SystemRole.LAWYER: _FIELD_CAPS,
    SystemRole.FORENSIC: _FORENSIC_CAPS,
    SystemRole.CITIZEN: _CITIZEN_CAPS,
}

# Case roles a user can be assigned to on a case. ADMIN is system-wide only —
# it is deliberately not a valid case_role.
ASSIGNABLE_CASE_ROLES: Tuple[str, ...] = ("COURT", "POLICE", "LAWYER", "FORENSIC", "CITIZEN")

# Fact keys a FORENSIC assignee may see (Twin/conflicts/history/provenance).
FORENSIC_FACT_KEYS: FrozenSet[str] = frozenset(
    {
        "weapon_type",
        "victim_injury",
        "cause_of_injury",
        "evidence_finding",
        "finding_limitation",
        "forensic_result",
        "sample_type",
        "sample_result",
    }
)

# Fact keys a CITIZEN assignee may see.
CITIZEN_FACT_KEYS: FrozenSet[str] = frozenset(
    {
        "case_status",
        "hearing_date",
        "next_hearing_date",
        "court_name",
        "case_stage",
        "public_order_status",
        "filing_date",
    }
)

# Ingestion identity is derived from case_role — the client never picks it.
ROLE_SOURCE_TYPE: Dict[str, str] = {
    "COURT": "court",
    "POLICE": "police",
    "LAWYER": "lawyer",
    "FORENSIC": "forensic",
    "CITIZEN": "citizen",
}

# Roles allowed to create cases (POST /cases); COURT creators are auto-assigned.
CASE_CREATOR_ROLES: FrozenSet[SystemRole] = frozenset({SystemRole.ADMIN, SystemRole.COURT})

PUBLIC_VISIBILITY = "CITIZEN_VISIBLE"
INTERNAL_VISIBILITY = "INTERNAL"


@dataclass(frozen=True)
class CaseAuth:
    """Resolved per-request authorization context for one case."""

    user: User
    case_row: Case
    role: str  # effective role label: "ADMIN" (system bypass) or the case_role value
    is_admin: bool
    permissions: FrozenSet[str]

    @property
    def case_number(self) -> str:
        return self.case_row.case_number

    def can(self, capability: str) -> bool:
        return capability in self.permissions


def permissions_for_role(role: str) -> FrozenSet[str]:
    """Capabilities for an effective role label ("ADMIN" or a case_role value)."""
    if role == SystemRole.ADMIN.value:
        return _ADMIN_CAPS
    try:
        return ROLE_CAPABILITIES.get(SystemRole(role), frozenset())
    except ValueError:
        return frozenset()


def context_for(user: User, case_row: Case, role: str) -> CaseAuth:
    """CaseAuth for a known (case, effective role) pair — used by case listing."""
    return CaseAuth(
        user=user,
        case_row=case_row,
        role=role,
        is_admin=role == SystemRole.ADMIN.value,
        permissions=permissions_for_role(role),
    )


# ---- case lookup / resolution ----


async def _case_by_number(
    session: AsyncSession, case_number: str, demo: bool = False
) -> Optional[Case]:
    return (
        await session.execute(
            select(Case).where(Case.case_number == case_number, Case.is_demo == demo)
        )
    ).scalar_one_or_none()


async def _active_access(
    session: AsyncSession, user_id: Any, case_uuid: Any
) -> Optional[CaseAccess]:
    return (
        await session.execute(
            select(CaseAccess).where(
                CaseAccess.user_id == user_id,
                CaseAccess.case_id == case_uuid,
                CaseAccess.status == AccessStatus.ACTIVE,
            )
        )
    ).scalar_one_or_none()


async def resolve_case_auth(
    session: AsyncSession, user: User, case_number: str, *, demo: bool = False
) -> CaseAuth:
    """Authenticated user → case exists (404) → ACTIVE access (403) → context."""
    case_row = await _case_by_number(session, case_number, demo=demo)
    if case_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"case not found: {case_number}")

    if user.system_role == SystemRole.ADMIN:
        return CaseAuth(
            user=user,
            case_row=case_row,
            role=SystemRole.ADMIN.value,
            is_admin=True,
            permissions=_ADMIN_CAPS,
        )

    access = await _active_access(session, user.id, case_row.id)
    if access is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"no active access to case {case_number}",
        )
    case_role = access.case_role
    return CaseAuth(
        user=user,
        case_row=case_row,
        role=case_role.value if hasattr(case_role, "value") else str(case_role),
        is_admin=False,
        permissions=ROLE_CAPABILITIES.get(case_role, frozenset()),
    )


def require_case(capability: str, demo: bool = False):
    """Dependency factory: resolve the case and enforce one capability."""

    async def _dependency(
        case_id: str,
        user: User = Depends(get_current_active_user),
        session: AsyncSession = Depends(get_db),
    ) -> CaseAuth:
        ctx = await resolve_case_auth(session, user, case_id, demo=demo)
        if not ctx.can(capability):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"role {ctx.role} may not perform {capability} on case {case_id}",
            )
        return ctx

    return _dependency


async def list_visible_cases(
    session: AsyncSession, user: User, *, demo: bool = False
) -> List[Tuple[Case, str]]:
    """(case, effective role) pairs: ADMIN sees all; others only ACTIVE cases."""
    if user.system_role == SystemRole.ADMIN:
        rows = (
            await session.execute(
                select(Case)
                .where(Case.is_demo == demo)
                .order_by(Case.created_at, Case.case_number)
            )
        ).scalars().all()
        return [(row, SystemRole.ADMIN.value) for row in rows]

    rows = (
        await session.execute(
            select(Case, CaseAccess.case_role)
            .join(CaseAccess, CaseAccess.case_id == Case.id)
            .where(
                Case.is_demo == demo,
                CaseAccess.user_id == user.id,
                CaseAccess.status == AccessStatus.ACTIVE,
            )
            .order_by(Case.created_at, Case.case_number)
        )
    ).all()
    return [(case_row, _enum_value(case_role)) for case_row, case_role in rows]


async def get_case_row(
    session: AsyncSession, case_number: str, *, demo: bool = False
) -> Case:
    """Fetch a case row by human case_number; 404 when it does not exist."""
    row = await _case_by_number(session, case_number, demo=demo)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"case not found: {case_number}")
    return row


# ---- case access management (ADMIN + assigned COURT) ----


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _access_to_dict(row: CaseAccess, user: Optional[User]) -> Dict[str, Any]:
    return {
        "user_id": str(row.user_id),
        "email": user.email if user is not None else None,
        "system_role": _enum_value(user.system_role) if user is not None else None,
        "case_role": _enum_value(row.case_role),
        "status": _enum_value(row.status),
        "granted_by": str(row.granted_by) if row.granted_by else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def grant_case_access(
    session: AsyncSession, case_row: Case, actor: User, email: str, case_role: str
) -> Dict[str, Any]:
    """Upsert-style grant that can never create duplicate rows."""
    if case_role not in ASSIGNABLE_CASE_ROLES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"invalid case_role {case_role!r}; expected one of {list(ASSIGNABLE_CASE_ROLES)}",
        )
    target = (
        await session.execute(
            select(User).where(User.email == (email or "").strip().lower())
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"user not found: {email}")

    row = (
        await session.execute(
            select(CaseAccess).where(
                CaseAccess.user_id == target.id, CaseAccess.case_id == case_row.id
            )
        )
    ).scalar_one_or_none()

    if row is None:
        row = CaseAccess(
            user_id=target.id,
            case_id=case_row.id,
            case_role=SystemRole[case_role],
            status=AccessStatus.ACTIVE,
            granted_by=actor.id,
        )
        session.add(row)
        await session.commit()
    elif row.status == AccessStatus.ACTIVE and _enum_value(row.case_role) == case_role:
        pass  # idempotent: same user, same case, same role
    elif row.status == AccessStatus.ACTIVE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"user already has ACTIVE {_enum_value(row.case_role)} access; revoke first",
        )
    else:  # REVOKED → reactivate with the requested role
        row.status = AccessStatus.ACTIVE
        row.case_role = SystemRole[case_role]
        row.granted_by = actor.id
        await session.commit()
    return _access_to_dict(row, target)


async def revoke_case_access(
    session: AsyncSession, case_row: Case, user_id: Any
) -> Dict[str, Any]:
    row = (
        await session.execute(
            select(CaseAccess).where(
                CaseAccess.case_id == case_row.id, CaseAccess.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is None or row.status != AccessStatus.ACTIVE:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "no active access for this user on this case"
        )
    row.status = AccessStatus.REVOKED
    await session.commit()
    return _access_to_dict(row, None)


async def list_case_access(session: AsyncSession, case_row: Case) -> List[Dict[str, Any]]:
    rows = (
        await session.execute(
            select(CaseAccess)
            .where(CaseAccess.case_id == case_row.id)
            .order_by(CaseAccess.created_at)
        )
    ).scalars().all()
    user_ids = {r.user_id for r in rows}
    users: Dict[Any, User] = {}
    if user_ids:
        users = {
            u.id: u
            for u in (
                await session.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars()
        }
    return [_access_to_dict(r, users.get(r.user_id)) for r in rows]


# ---- ingestion identity / visibility ----


def source_type_for(ctx: CaseAuth) -> str:
    """Server-derived source_type; client-supplied values are ignored."""
    return ROLE_SOURCE_TYPE[ctx.role]


def resolve_visibility(ctx: CaseAuth, requested: Optional[str]) -> str:
    """CITIZEN_VISIBLE can only be set by a COURT assignee; default INTERNAL."""
    if (
        requested
        and str(requested).strip().upper() == PUBLIC_VISIBILITY
        and ctx.can(DOC_SET_CITIZEN_VISIBILITY)
    ):
        return PUBLIC_VISIBILITY
    return INTERNAL_VISIBILITY


def default_source_id(ctx: CaseAuth) -> str:
    return f"{ctx.role.lower()}:{ctx.user.email}"


# ---- resource filtering (pure functions) ----


def filter_case_meta(meta: Dict[str, Any], ctx: CaseAuth) -> Dict[str, Any]:
    if ctx.role == SystemRole.CITIZEN.value:
        return {k: v for k, v in meta.items() if k != "description"}
    return dict(meta)


def filter_facts(facts: Dict[str, Any], ctx: CaseAuth) -> Dict[str, Any]:
    if ctx.role == SystemRole.FORENSIC.value:
        return {k: v for k, v in facts.items() if k in FORENSIC_FACT_KEYS}
    if ctx.role == SystemRole.CITIZEN.value:
        return {k: v for k, v in facts.items() if k in CITIZEN_FACT_KEYS}
    return dict(facts)


def filter_conflicts(conflicts: Dict[str, Any], ctx: CaseAuth) -> Dict[str, Any]:
    if ctx.role == SystemRole.FORENSIC.value:
        return {k: v for k, v in conflicts.items() if k in FORENSIC_FACT_KEYS}
    if ctx.role == SystemRole.CITIZEN.value:
        return {}
    return dict(conflicts)


def filter_observations(
    observations: List[Dict[str, Any]], ctx: CaseAuth
) -> List[Dict[str, Any]]:
    if ctx.role == SystemRole.CITIZEN.value:
        return []
    if ctx.role == SystemRole.FORENSIC.value:
        return [o for o in observations if o.get("source_type") == "forensic"]
    return list(observations)


def filter_documents(
    documents: List[Dict[str, Any]], ctx: CaseAuth
) -> List[Dict[str, Any]]:
    if ctx.role == SystemRole.CITIZEN.value:
        return [d for d in documents if d.get("visibility") == PUBLIC_VISIBILITY]
    if ctx.role == SystemRole.FORENSIC.value:
        return [d for d in documents if d.get("source_type") == "forensic"]
    return list(documents)


def filter_history(
    history: List[Dict[str, Any]], ctx: CaseAuth
) -> List[Dict[str, Any]]:
    if ctx.role == SystemRole.CITIZEN.value:
        return []
    if ctx.role == SystemRole.FORENSIC.value:
        return [h for h in history if h.get("fact_key") in FORENSIC_FACT_KEYS]
    return list(history)


def filter_provenance(prov: Dict[str, Any], ctx: CaseAuth) -> Dict[str, Any]:
    inner = prov.get("provenance") or {}
    if ctx.role == SystemRole.CITIZEN.value:
        inner = {}
    elif ctx.role == SystemRole.FORENSIC.value:
        inner = {k: v for k, v in inner.items() if k in FORENSIC_FACT_KEYS}
    return {**prov, "provenance": inner}


def filter_stakeholders(
    stakeholders: List[Dict[str, Any]],
    ctx: CaseAuth,
    allowed_documents: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    if ctx.role == SystemRole.CITIZEN.value:
        docs = allowed_documents or []
        pairs = {(d.get("source_type"), d.get("source_id")) for d in docs}
        return [
            s
            for s in stakeholders
            if (s.get("source_type"), s.get("source_id")) in pairs
        ]
    if ctx.role == SystemRole.FORENSIC.value:
        return [s for s in stakeholders if s.get("source_type") == "forensic"]
    return list(stakeholders)


def _filter_timeline(
    timeline: List[Dict[str, Any]],
    documents: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    doc_ids = {d.get("document_id") for d in documents}
    hist_keys = {(h.get("fact_key"), h.get("timestamp")) for h in history}
    out: List[Dict[str, Any]] = []
    for entry in timeline:
        kind = entry.get("kind")
        if kind == "document" and entry.get("document_id") in doc_ids:
            out.append(entry)
        elif kind == "cams_decision" and (entry.get("fact_key"), entry.get("at")) in hist_keys:
            out.append(entry)
    return out


def filter_full_view(view: Dict[str, Any], ctx: CaseAuth) -> Dict[str, Any]:
    documents = filter_documents(view.get("documents") or [], ctx)
    observations = filter_observations(view.get("observations") or [], ctx)
    history = filter_history(view.get("history") or [], ctx)
    twin = filter_facts(view.get("twin") or {}, ctx)
    conflicts = filter_conflicts(view.get("conflicts") or {}, ctx)
    stakeholders = filter_stakeholders(
        view.get("stakeholders") or [], ctx, documents
    )
    timeline = _filter_timeline(view.get("timeline") or [], documents, history)

    out = dict(view)
    out["case"] = filter_case_meta(view.get("case") or {}, ctx)
    out["documents"] = documents
    out["observations"] = observations
    out["history"] = history
    out["twin"] = twin
    out["conflicts"] = conflicts
    out["stakeholders"] = stakeholders
    out["timeline"] = timeline
    out["summary"] = {
        "documents": len(documents),
        "observations": len(observations),
        "history_events": len(history),
        "twin_facts": len(twin),
        "conflicts": len(conflicts),
        "stakeholders": len(stakeholders),
    }
    return out


def filter_ingest_result(result: Dict[str, Any], ctx: CaseAuth) -> Dict[str, Any]:
    """Filter pipeline mutation responses (ingest/resync) for restricted roles.

    FORENSIC gets scoped facts/conflicts/history and a filtered case view;
    full-view roles pass through unchanged.
    """
    if ctx.role not in (SystemRole.FORENSIC.value, SystemRole.CITIZEN.value):
        return result
    out = dict(result)
    out["facts"] = filter_facts(result.get("facts") or {}, ctx)
    out["conflicts"] = filter_conflicts(result.get("conflicts") or {}, ctx)
    out["history_tail"] = filter_history(result.get("history_tail") or [], ctx)
    if result.get("case_view"):
        out["case_view"] = filter_full_view(result["case_view"], ctx)
    return out


async def filtered_case_snapshot(
    repo: Any, ctx: CaseAuth, case_id: str, snapshot: Dict[str, Any]
) -> Dict[str, Any]:
    """Recompute a case_snapshot with role filtering applied to counts/lists."""
    documents = filter_documents(await repo.get_documents(case_id), ctx)
    observations = filter_observations(await repo.get_observations(case_id), ctx)
    history = filter_history(await repo.get_history(case_id), ctx)
    stakeholders = filter_stakeholders(
        await repo.list_stakeholders(case_id), ctx, documents
    )
    out = filter_case_meta(dict(snapshot), ctx)
    out["facts"] = filter_facts(snapshot.get("facts") or {}, ctx)
    out["conflicts"] = filter_conflicts(snapshot.get("conflicts") or {}, ctx)
    out["observation_count"] = len(observations)
    out["document_count"] = len(documents)
    out["history_count"] = len(history)
    out["stakeholders"] = stakeholders
    return out
