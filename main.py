"""
NyayaOS-lite FastAPI — case dashboard API + static UI.

Structured case/CAMS state lives in PostgreSQL (DbRepository).
Physical upload bytes stay under data/cases/ and data/demo_cases/.
The legacy JSON FileRepository is not used at runtime.
Web UI → frontend/ (served at /)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from auth import router as auth_router
from config import DELTA, TAU, WEIGHTS
from db_repository import DATA_ROOT, DEMO_DATA_ROOT, DbRepository
from demo_data import (
    CASE_001_DESCRIPTION,
    CASE_001_ID,
    CASE_001_TITLE,
    case_001_documents,
    scenario_document,
)
from models import CaseCreate, TextIn
from pipeline import Pipeline
from seed import seed_dev_users

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


@app.post("/cases")
async def create_case(body: CaseCreate) -> Dict[str, Any]:
    return await pipeline.create_case(
        case_id=body.case_id,
        title=body.title,
        description=body.description,
    )


@app.get("/cases")
async def list_cases() -> List[Dict[str, Any]]:
    return await repo.list_cases()


@app.get("/cases/{case_id}")
async def get_case(case_id: str) -> Dict[str, Any]:
    try:
        return await pipeline.case_snapshot(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None


@app.post("/cases/{case_id}/text")
async def ingest_text(case_id: str, body: TextIn) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return await pipeline.ingest_text(
        case_id=case_id,
        text=body.text,
        source=body.source,
        source_type=body.source_type,
        title=body.title or "",
        force_fallback=body.force_fallback,
    )


@app.post("/cases/{case_id}/upload")
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    source: str = Form("user"),
    source_type: str = Form("unknown"),
    force_fallback: bool = Form(False),
    title: str = Form(""),
) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty upload")
    return await pipeline.ingest_upload(
        case_id=case_id,
        filename=file.filename or "upload.bin",
        data=data,
        source=source,
        source_type=source_type,
        content_type=file.content_type,
        force_fallback=force_fallback,
        title=title,
    )


@app.get("/cases/{case_id}/full")
async def full_case(case_id: str) -> Dict[str, Any]:
    try:
        await repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None
    return await pipeline.full_case_view(case_id)


@app.get("/cases/{case_id}/stakeholders")
async def stakeholders(case_id: str) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return {"case_id": case_id, "stakeholders": await repo.list_stakeholders(case_id)}


@app.get("/cases/{case_id}/observations")
async def get_observations(case_id: str) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return {"case_id": case_id, "observations": await repo.get_observations(case_id)}


@app.get("/cases/{case_id}/facts")
async def get_facts(case_id: str) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return {"case_id": case_id, "facts": await repo.get_facts(case_id)}


@app.get("/cases/{case_id}/history")
async def get_history(case_id: str) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return {"case_id": case_id, "history": await repo.get_history(case_id)}


@app.get("/cases/{case_id}/conflicts")
async def get_conflicts(case_id: str) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return {"case_id": case_id, "conflicts": await repo.get_conflicts(case_id)}


@app.get("/cases/{case_id}/provenance")
async def get_provenance(case_id: str) -> Dict[str, Any]:
    try:
        await repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None
    return await pipeline.provenance(case_id)


@app.get("/cases/{case_id}/documents")
async def get_documents(case_id: str) -> Dict[str, Any]:
    await repo.ensure_case(case_id)
    return {"case_id": case_id, "documents": await repo.get_documents(case_id)}


@app.post("/cases/{case_id}/resync")
async def resync(case_id: str) -> Dict[str, Any]:
    try:
        await repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None
    return await pipeline.resync(case_id)


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
