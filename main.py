"""
NyayaOS-lite FastAPI — Input → Gemini → JSON files → CAMS → Digital Twin.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import DELTA, TAU, WEIGHTS
from demo_data import (
    CASE_001_DESCRIPTION,
    CASE_001_ID,
    CASE_001_TITLE,
    case_001_documents,
    scenario_document,
)
from file_repository import repo
from models import CaseCreate, TextIn
from pipeline import pipeline

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"

app = FastAPI(
    title="nyayaos-lite",
    description="NyayaOS — Gemini extraction + file persistence + CAMS Digital Twin",
)

if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


@app.get("/")
def serve_frontend() -> FileResponse:
    index = FRONTEND / "index.html"
    if not index.exists():
        raise HTTPException(404, "frontend missing")
    return FileResponse(index)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "service": "nyayaos-lite",
        "pipeline": "text → Gemini/fallback → JSON files → CAMS → Digital Twin",
        "weights": WEIGHTS,
        "tau": TAU,
        "delta": DELTA,
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
        "note": "Synthetic research evaluation from evaluate.py — not mixed with demo case files.",
    }


@app.post("/api/reset")
def api_reset() -> Dict[str, str]:
    """Wipe demo case files (tests/demo only). Does not delete code."""
    repo.reset_all()
    return {"status": "ok", "message": "All case JSON files cleared under data/cases/"}


# ---- Cases ----


@app.post("/cases")
def create_case(body: CaseCreate) -> Dict[str, Any]:
    return pipeline.create_case(
        case_id=body.case_id,
        title=body.title,
        description=body.description,
    )


@app.get("/cases")
def list_cases() -> List[Dict[str, Any]]:
    return repo.list_cases()


@app.get("/cases/{case_id}")
def get_case(case_id: str) -> Dict[str, Any]:
    try:
        return pipeline.case_snapshot(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None


@app.post("/cases/{case_id}/text")
def ingest_text(case_id: str, body: TextIn) -> Dict[str, Any]:
    """Complete pipeline: text → extract → store → CAMS → twin → history."""
    repo.ensure_case(case_id)
    return pipeline.ingest_text(
        case_id=case_id,
        text=body.text,
        source=body.source,
        source_type=body.source_type,
        title=body.title or "",
        force_fallback=body.force_fallback,
    )


@app.get("/cases/{case_id}/observations")
def get_observations(case_id: str) -> Dict[str, Any]:
    repo.ensure_case(case_id)
    return {"case_id": case_id, "observations": repo.get_observations(case_id)}


@app.get("/cases/{case_id}/facts")
def get_facts(case_id: str) -> Dict[str, Any]:
    repo.ensure_case(case_id)
    return {"case_id": case_id, "facts": repo.get_facts(case_id)}


@app.get("/cases/{case_id}/history")
def get_history(case_id: str) -> Dict[str, Any]:
    repo.ensure_case(case_id)
    return {"case_id": case_id, "history": repo.get_history(case_id)}


@app.get("/cases/{case_id}/conflicts")
def get_conflicts(case_id: str) -> Dict[str, Any]:
    repo.ensure_case(case_id)
    return {"case_id": case_id, "conflicts": repo.get_conflicts(case_id)}


@app.get("/cases/{case_id}/provenance")
def get_provenance(case_id: str) -> Dict[str, Any]:
    try:
        return pipeline.provenance(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None


@app.get("/cases/{case_id}/documents")
def get_documents(case_id: str) -> Dict[str, Any]:
    repo.ensure_case(case_id)
    return {"case_id": case_id, "documents": repo.get_documents(case_id)}


@app.post("/cases/{case_id}/resync")
def resync(case_id: str) -> Dict[str, Any]:
    try:
        repo.get_case(case_id)
    except KeyError:
        raise HTTPException(404, f"case not found: {case_id}") from None
    return pipeline.resync(case_id)


# Legacy endpoints for simulate.py compatibility
@app.get("/cases/{case_id}/state")
def legacy_state(case_id: str) -> Dict[str, Any]:
    facts = repo.get_facts(case_id)
    unresolved = [
        k for k, v in repo.get_conflicts(case_id).items() if v.get("status") == "unresolved"
    ]
    return {
        "case_id": case_id,
        "facts": {
            k: {
                "fact_key": k,
                "value": v.get("value"),
                "confidence": v.get("confidence"),
                "resolved": v.get("status") == "resolved",
                "last_updated": v.get("last_updated"),
                "supporting_observation_ids": v.get("supporting_observation_ids") or [],
            }
            for k, v in facts.items()
        },
        "unresolved": unresolved,
    }


@app.post("/cases/{case_id}/observations")
def legacy_obs(case_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Legacy direct observation ingest used by simulate.py.
    Wraps a single structured claim as a mini text pipeline step without Gemini.
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    repo.ensure_case(case_id)
    now = datetime.now(timezone.utc)
    oid = str(uuid4())
    conf = float(body.get("extraction_reliability", 0.8))
    obs = {
        "observation_id": oid,
        "case_id": case_id,
        "source": body.get("source_id", "legacy"),
        "source_id": body.get("source_id", "legacy"),
        "source_type": body.get("source_type", "unknown"),
        "fact_key": body["fact_key"],
        "value": body["value"],
        "event_time": body.get("event_time") or now.isoformat(),
        "ingestion_time": body.get("ingestion_time") or now.isoformat(),
        "evidence": body.get("evidence") or "(direct observation)",
        "extraction_confidence": conf,
        "extraction_reliability": conf,
        "status": "recorded",
        "document_id": None,
    }
    repo.append_observations(case_id, [obs])
    decision = pipeline._run_cams_for_fact(case_id, body["fact_key"], trigger_observation_id=oid)
    # Shape expected by simulate.py
    return {
        "case_id": case_id,
        "fact_key": body["fact_key"],
        "decided": decision["decided"],
        "accepted_value": decision.get("selected_value"),
        "previous_value": decision.get("previous_value"),
        "unresolved": decision.get("unresolved"),
        "C1": decision.get("C1"),
        "C2": decision.get("C2"),
        "margin": decision.get("margin"),
        "tau": decision.get("tau"),
        "delta": decision.get("delta"),
        "candidates": decision.get("candidates") or [],
        "message": decision.get("reason") or decision.get("explanation"),
    }


@app.get("/cases/{case_id}/unresolved")
def legacy_unresolved(case_id: str) -> Dict[str, Any]:
    conflicts = repo.get_conflicts(case_id)
    return {
        "case_id": case_id,
        "unresolved": [k for k, v in conflicts.items() if v.get("status") == "unresolved"],
    }


# ---- Demo ----


@app.post("/demo/case-001")
def demo_case_001(reset: bool = True) -> Dict[str, Any]:
    if reset:
        if repo.exists(CASE_001_ID):
            repo.delete_case_dir(CASE_001_ID)
    pipeline.create_case(CASE_001_ID, CASE_001_TITLE, CASE_001_DESCRIPTION)
    steps = []
    for doc in case_001_documents():
        result = pipeline.ingest_text(
            CASE_001_ID,
            text=doc["text"],
            source=doc["source_id"],
            source_type=doc["source_type"],
            title=doc.get("title") or "",
            force_fallback=True,  # deterministic demo
        )
        steps.append({"scenario": doc.get("scenario"), "result": result})
    return {
        "case_id": CASE_001_ID,
        "steps": steps,
        "snapshot": pipeline.case_snapshot(CASE_001_ID),
    }


@app.post("/demo/scenario/{name}")
def demo_scenario(name: str, case_id: str = Query(default=CASE_001_ID)) -> Dict[str, Any]:
    repo.ensure_case(case_id, title=CASE_001_TITLE if case_id == CASE_001_ID else case_id)
    key = name.lower().strip()
    if key in ("full", "full-demo", "case-001"):
        return demo_case_001(reset=True)

    if key in ("corroboration",):
        outs = []
        for d in case_001_documents():
            if d.get("scenario") == "corroboration":
                outs.append(
                    pipeline.ingest_text(
                        case_id,
                        text=d["text"],
                        source=d["source_id"],
                        source_type=d["source_type"],
                        title=d.get("title") or "",
                        force_fallback=True,
                    )
                )
        return {"scenario": name, "results": outs, "snapshot": pipeline.case_snapshot(case_id)}

    try:
        doc = scenario_document(name)
    except KeyError as e:
        raise HTTPException(400, str(e)) from e
    result = pipeline.ingest_text(
        case_id,
        text=doc["text"],
        source=doc["source_id"],
        source_type=doc["source_type"],
        title=doc.get("title") or "",
        force_fallback=True,
    )
    return {"scenario": name, "result": result, "snapshot": pipeline.case_snapshot(case_id)}
