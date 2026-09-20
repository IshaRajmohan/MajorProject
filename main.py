"""
NyayaOS-lite FastAPI — case dashboard API + static UI.

Structured case/CAMS state lives in PostgreSQL (DbRepository).
Physical upload bytes stay under data/cases/ and data/demo_cases/.
The legacy JSON FileRepository is not used at runtime.
Web UI → frontend/ (served at /)

Every /cases/* route requires a valid JWT and is authorized per case by
rbac.py: ADMIN bypasses case_access system-wide, everyone else needs an
ACTIVE case_access row whose case_role holds the endpoint capability.
Client-supplied source identity/visibility is ignored — it is derived
server-side from the caller's case_role.

Public (no auth) routes — intentional, and safe by design:
  GET  /                     static UI shell (no case data)
  POST /auth/login           credential exchange; 401 on bad credentials
                             (GET /auth/me is protected — it returns the
                             caller's own identity, needs a valid JWT)
  GET  /api/health           service/storage config, CAMS constants
  GET  /api/config           CAMS weights/tau/delta, public demo metadata
  GET  /api/evaluation       synthetic evaluation report (results.md)
  POST /api/reset-demo       wipes ONLY is_demo=True rows + data/demo_cases/
  POST /demo/case-001        seeds the synthetic demo case (is_demo=True)
  POST /demo/scenario/{name} seeds a synthetic demo scenario (is_demo=True)

The demo routes operate exclusively through demo_repo/demo_pipeline
(DbRepository(demo=True)); they cannot read or mutate real is_demo=False
cases, and /api/reset-demo's reset_all() is demo-scoped. ADMIN-only system
user management lives in users_api.py (/users) and never grants case access
(case_access stays exclusive to /cases/{case_id}/access).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

import rbac
from auth import get_current_active_user, router as auth_router
from config import DELTA, TAU, WEIGHTS
from db import get_db
from db_models import SystemRole, User
from db_repository import DbRepository, case_to_dict
from paths import DATA_ROOT, DEMO_DATA_ROOT
from demo_data import (
    CASE_001_DESCRIPTION,
    CASE_001_ID,
    CASE_001_TITLE,
    case_001_documents,
    scenario_document,
)
from models import (
    AccessGrantIn,
    CaseCreate,
    CasePatch,
    SubmissionCreate,
    SubmissionReviewIn,
    TextIn,
)
from pipeline import Pipeline
from seed import seed_dev_users
from users_api import router as users_router

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"

repo = DbRepository(demo=False)
demo_repo = DbRepository(demo=True)
pipeline = Pipeline(repository=repo)
demo_pipeline = Pipeline(repository=demo_repo)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await seed_dev_users()
    yield


app = FastAPI(
    title="nyayaos-lite",
    description="NyayaOS — officer/lawyer case dashboard. Structured state in PostgreSQL.",
    lifespan=lifespan,
)
app.include_router(auth_router)
app.include_router(users_router)


@app.get("/api/health")
async def health() -> Dict[str, Any]:
    return {
        "service": "nyayaos-lite",
        "pipeline": "text → Gemini/fallback → PostgreSQL → CAMS → Digital Twin",
        "storage": "postgresql",
        "weights": WEIGHTS,
        "tau": TAU,
        "delta": DELTA,
        "real_cases_root": str(DATA_ROOT),
        "demo_cases_root": str(DEMO_DATA_ROOT),
        "disclaimer": "CAMS confidence is not legal truth. Evaluation data is synthetic.",
    }


@app.get("/api/config")
def api_config() -> Dict[str, Any]:
    return {"weights": WEIGHTS, "tau": TAU, "delta": DELTA}


@app.get("/api/evaluation")
def api_evaluation() -> Dict[str, Any]:
    md = ROOT / "results.md"
    return {
        "markdown": md.read_text() if md.exists() else "",
        "note": "Synthetic research evaluation from evaluate.py — not mixed with case files.",
    }


@app.post("/api/reset-demo")
async def api_reset_demo() -> Dict[str, str]:
    """Wipe ONLY demo-scoped PostgreSQL rows + data/demo_cases/. Never touches real cases."""
    await demo_repo.reset_all()
    return {
        "status": "ok",
        "message": f"Cleared demo cases under {DEMO_DATA_ROOT}",
    }


# ---- Real cases (PostgreSQL, is_demo=False) ----
# Auth chain per route: JWT (401) → case exists (404) → ACTIVE case_access
# holding the capability (403) → role-filtered response.


@app.post("/cases")
async def create_case(
    body: CaseCreate,
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    if user.system_role not in rbac.CASE_CREATOR_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"system role {user.system_role.value} may not create cases",
        )
    if body.case_id and await repo.exists(body.case_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"case already exists: {body.case_id}"
        )
    meta = await pipeline.create_case(
        case_id=body.case_id,
        title=body.title,
        description=body.description,
        case_type=body.case_type,
        case_status=body.case_status,
        filing_date=body.filing_date,
        court_name=body.court_name,
        next_hearing_date=body.next_hearing_date,
    )
    if user.system_role == SystemRole.COURT:
        case_row = await rbac.get_case_row(session, meta["case_id"])
        await rbac.grant_case_access(session, case_row, user, user.email, "COURT")
    return meta


@app.get("/cases")
async def list_cases(
    user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    pairs = await rbac.list_visible_cases(session, user)
    out: List[Dict[str, Any]] = []
    for row, role in pairs:
        meta = rbac.filter_case_meta(case_to_dict(row), rbac.context_for(user, row, role))
        meta["role"] = role
        out.append(meta)
    return out


@app.get("/cases/{case_id}")
async def get_case(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CASE_VIEW)),
) -> Dict[str, Any]:
    snapshot = await pipeline.case_snapshot(ctx.case_number)
    return await rbac.filtered_case_snapshot(repo, ctx, ctx.case_number, snapshot)


@app.patch("/cases/{case_id}")
async def update_case(
    case_id: str,
    body: CasePatch,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CASE_EDIT_META)),
) -> Dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "no metadata fields supplied"
        )
    meta = await repo.update_case(ctx.case_number, patch)
    return rbac.filter_case_meta(meta, ctx)


@app.post("/cases/{case_id}/text")
async def ingest_text(
    case_id: str,
    body: TextIn,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CAMS_INGEST)),
) -> Dict[str, Any]:
    result = await pipeline.ingest_text(
        case_id=ctx.case_number,
        text=body.text,
        source=rbac.default_source_id(ctx),
        source_type=rbac.source_type_for(ctx),
        title=body.title or "",
        force_fallback=body.force_fallback,
        visibility=rbac.resolve_visibility(ctx, body.visibility),
    )
    return rbac.filter_ingest_result(result, ctx)


@app.post("/cases/{case_id}/upload")
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    force_fallback: bool = Form(False),
    title: str = Form(""),
    visibility: str = Form(""),
    source: str = Form(""),
    source_type: str = Form(""),
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.DOC_UPLOAD)),
) -> Dict[str, Any]:
    # ``source``/``source_type`` accepted for compatibility but ignored —
    # identity always comes from the caller's case_role.
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty upload")
    result = await pipeline.ingest_upload(
        case_id=ctx.case_number,
        filename=file.filename or "upload.bin",
        data=data,
        source=rbac.default_source_id(ctx),
        source_type=rbac.source_type_for(ctx),
        content_type=file.content_type,
        force_fallback=force_fallback,
        title=title,
        visibility=rbac.resolve_visibility(ctx, visibility),
    )
    return rbac.filter_ingest_result(result, ctx)


@app.get("/cases/{case_id}/full")
async def full_case(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CASE_VIEW)),
) -> Dict[str, Any]:
    view = await pipeline.full_case_view(ctx.case_number)
    return rbac.filter_full_view(view, ctx)


@app.get("/cases/{case_id}/stakeholders")
async def stakeholders(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.STAKEHOLDER_VIEW)),
) -> Dict[str, Any]:
    rows = await repo.list_stakeholders(ctx.case_number)
    return {
        "case_id": ctx.case_number,
        "stakeholders": rbac.filter_stakeholders(rows, ctx),
    }


@app.get("/cases/{case_id}/observations")
async def get_observations(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.OBS_VIEW)),
) -> Dict[str, Any]:
    rows = await repo.get_observations(ctx.case_number)
    return {
        "case_id": ctx.case_number,
        "observations": rbac.filter_observations(rows, ctx),
    }


@app.get("/cases/{case_id}/facts")
async def get_facts(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.TWIN_VIEW)),
) -> Dict[str, Any]:
    facts = await repo.get_facts(ctx.case_number)
    return {"case_id": ctx.case_number, "facts": rbac.filter_facts(facts, ctx)}


@app.get("/cases/{case_id}/history")
async def get_history(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.HISTORY_VIEW)),
) -> Dict[str, Any]:
    rows = await repo.get_history(ctx.case_number)
    return {"case_id": ctx.case_number, "history": rbac.filter_history(rows, ctx)}


@app.get("/cases/{case_id}/conflicts")
async def get_conflicts(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CONFLICT_VIEW)),
) -> Dict[str, Any]:
    rows = await repo.get_conflicts(ctx.case_number)
    return {"case_id": ctx.case_number, "conflicts": rbac.filter_conflicts(rows, ctx)}


@app.get("/cases/{case_id}/provenance")
async def get_provenance(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.PROVENANCE_VIEW)),
) -> Dict[str, Any]:
    prov = await pipeline.provenance(ctx.case_number)
    return rbac.filter_provenance(prov, ctx)


@app.get("/cases/{case_id}/documents")
async def get_documents(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.DOC_VIEW)),
) -> Dict[str, Any]:
    rows = await repo.get_documents(ctx.case_number)
    return {
        "case_id": ctx.case_number,
        "documents": rbac.filter_documents(rows, ctx),
    }


@app.post("/cases/{case_id}/resync")
async def resync(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CAMS_RESYNC)),
) -> Dict[str, Any]:
    result = await pipeline.resync(ctx.case_number)
    return rbac.filter_ingest_result(result, ctx)


# ---- Case access management (ADMIN + assigned COURT) ----


@app.post("/cases/{case_id}/access")
async def grant_access(
    case_id: str,
    body: AccessGrantIn,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CASE_MANAGE_ACCESS)),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    granted = await rbac.grant_case_access(
        session, ctx.case_row, ctx.user, body.email, body.case_role
    )
    return {"case_id": ctx.case_number, "access": granted}


@app.get("/cases/{case_id}/access")
async def get_access(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CASE_MANAGE_ACCESS)),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    rows = await rbac.list_case_access(session, ctx.case_row)
    return {"case_id": ctx.case_number, "access": rows}


@app.delete("/cases/{case_id}/access/{user_id}")
async def revoke_access(
    case_id: str,
    user_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.CASE_MANAGE_ACCESS)),
    session: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    try:
        target_id = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"user not found: {user_id}"
        ) from None
    revoked = await rbac.revoke_case_access(session, ctx.case_row, target_id)
    return {"case_id": ctx.case_number, "access": revoked}


# ---- Citizen submissions (PENDING until an assigned COURT reviews) ----


@app.post("/cases/{case_id}/submissions")
async def create_submission(
    case_id: str,
    body: SubmissionCreate,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.SUBMISSION_CREATE)),
) -> Dict[str, Any]:
    if not (body.text or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "submission text is required"
        )
    submission = await repo.create_submission(
        ctx.case_number,
        submitted_by=ctx.user.id,
        title=body.title or "",
        text=body.text,
    )
    return {"case_id": ctx.case_number, "submission": submission}


@app.get("/cases/{case_id}/submissions")
async def list_submissions(
    case_id: str,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.SUBMISSION_LIST)),
) -> Dict[str, Any]:
    own_only = ctx.user.id if ctx.role == SystemRole.CITIZEN.value else None
    rows = await repo.list_submissions(ctx.case_number, submitted_by=own_only)
    return {"case_id": ctx.case_number, "submissions": rows}


@app.post("/cases/{case_id}/submissions/{submission_id}/review")
async def review_submission(
    case_id: str,
    submission_id: str,
    body: SubmissionReviewIn,
    ctx: rbac.CaseAuth = Depends(rbac.require_case(rbac.SUBMISSION_REVIEW)),
) -> Dict[str, Any]:
    try:
        claimed = await repo.decide_submission(
            ctx.case_number,
            submission_id,
            decision=body.decision,
            reviewer_id=ctx.user.id,
            note=body.note,
        )
    except (KeyError, ValueError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"submission not found: {submission_id}"
        ) from None
    if claimed is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "submission was already reviewed"
        )

    if body.decision == "REJECT":
        return {"case_id": ctx.case_number, "submission": claimed, "ingestion": None}

    try:
        result = await pipeline.ingest_text(
            case_id=ctx.case_number,
            text=claimed["text"],
            source=f"citizen:{claimed.get('submitted_by_email') or claimed['submitted_by']}",
            source_type=rbac.ROLE_SOURCE_TYPE["CITIZEN"],
            title=claimed.get("title") or "",
            force_fallback=body.force_fallback,
            visibility=rbac.INTERNAL_VISIBILITY,
        )
    except Exception as exc:  # revert the claim so the submission can be retried
        await repo.revert_submission(
            submission_id, note=f"approval failed, reverted to PENDING: {exc}"
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"approval failed; submission reverted to PENDING: {exc}",
        ) from exc

    await repo.attach_submission_document(submission_id, result["document"]["document_id"])
    refreshed = await repo.get_submission(ctx.case_number, submission_id)
    return {
        "case_id": ctx.case_number,
        "submission": refreshed,
        "ingestion": rbac.filter_ingest_result(result, ctx),
    }


# ---- Demo (PostgreSQL is_demo=True + data/demo_cases/ uploads) ----


@app.post("/demo/case-001")
async def demo_case_001(reset: bool = False) -> Dict[str, Any]:
    """
    Synthetic CASE-001 demo. Writes only demo-scoped PostgreSQL rows + data/demo_cases/.
    reset=True clears demo data only — never real cases.
    """
    if reset:
        await demo_repo.reset_all()
    await demo_pipeline.create_case(CASE_001_ID, CASE_001_TITLE, CASE_001_DESCRIPTION)
    steps = []
    for doc in case_001_documents():
        result = await demo_pipeline.ingest_text(
            CASE_001_ID,
            text=doc["text"],
            source=doc["source_id"],
            source_type=doc["source_type"],
            title=doc.get("title") or "",
            force_fallback=True,
        )
        steps.append({"scenario": doc.get("scenario"), "result": result})
    return {
        "case_id": CASE_001_ID,
        "storage": str(demo_repo.root / CASE_001_ID),
        "steps": steps,
        "snapshot": await demo_pipeline.case_snapshot(CASE_001_ID),
    }


@app.post("/demo/scenario/{name}")
async def demo_scenario(name: str, case_id: str = Query(default=CASE_001_ID)) -> Dict[str, Any]:
    """Scenario buttons — always use demo_pipeline (is_demo=True)."""
    await demo_repo.ensure_case(
        case_id, title=CASE_001_TITLE if case_id == CASE_001_ID else case_id
    )
    key = name.lower().strip()
    if key in ("full", "full-demo", "case-001"):
        return await demo_case_001(reset=False)

    if key in ("corroboration",):
        outs = []
        for d in case_001_documents():
            if d.get("scenario") == "corroboration":
                outs.append(
                    await demo_pipeline.ingest_text(
                        case_id,
                        text=d["text"],
                        source=d["source_id"],
                        source_type=d["source_type"],
                        title=d.get("title") or "",
                        force_fallback=True,
                    )
                )
        return {
            "scenario": name,
            "storage": str(demo_repo.root / case_id),
            "results": outs,
            "snapshot": await demo_pipeline.case_snapshot(case_id),
        }

    try:
        doc = scenario_document(name)
    except KeyError as e:
        raise HTTPException(400, str(e)) from e
    result = await demo_pipeline.ingest_text(
        case_id,
        text=doc["text"],
        source=doc["source_id"],
        source_type=doc["source_type"],
        title=doc.get("title") or "",
        force_fallback=True,
    )
    return {
        "scenario": name,
        "storage": str(demo_repo.root / case_id),
        "result": result,
        "snapshot": await demo_pipeline.case_snapshot(case_id),
    }


# ---- Static case dashboard (must be last so API routes win) ----


@app.get("/")
def serve_dashboard() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/assets", StaticFiles(directory=str(FRONTEND)), name="assets")
