"""FastAPI app for nyayaos-lite — live qualitative CAMS demo."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException

from cams import synchronize
from models import DecisionResult, Observation, ObservationIn
from store import store

app = FastAPI(title="nyayaos-lite", description="CAMS — Confidence-Aware Multi-Source Synchronization")


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": "nyayaos-lite", "cams": "Confidence-Aware Multi-Source Synchronization"}


@app.post("/cases/{case_id}/observations", response_model=DecisionResult)
def ingest_observation(case_id: str, body: ObservationIn) -> DecisionResult:
    obs = Observation(
        case_id=case_id,
        fact_key=body.fact_key,
        value=body.value,
        source_id=body.source_id,
        source_type=body.source_type,
        event_time=body.event_time,
        ingestion_time=body.ingestion_time or datetime.now(timezone.utc),
        extraction_reliability=body.extraction_reliability,
    )
    store.add_observation(obs)

    all_for_fact = store.get_observations(case_id, body.fact_key)
    timeline = store.timeline_event_times(case_id)
    previous = store.get_fact_value(case_id, body.fact_key)

    decision = synchronize(
        case_id=case_id,
        fact_key=body.fact_key,
        observations=all_for_fact,
        timeline=timeline,
        previous_value=previous,
    )

    if decision.decided:
        top = decision.candidates[0]
        store.set_fact(
            case_id,
            body.fact_key,
            decision.accepted_value,
            confidence=top.confidence,
            supporting_ids=top.supporting_observation_ids,
        )
    else:
        store.mark_unresolved(case_id, body.fact_key, retain_existing=True)

    return decision


@app.get("/cases/{case_id}/state")
def get_state(case_id: str) -> Dict[str, Any]:
    state = store.get_state(case_id)
    return {
        "case_id": state.case_id,
        "facts": {k: v.model_dump() for k, v in state.facts.items()},
        "unresolved": store.get_unresolved(case_id),
    }


@app.get("/cases/{case_id}/observations")
def get_observations(case_id: str) -> List[Dict[str, Any]]:
    return [o.model_dump() for o in store.get_observations(case_id)]


@app.get("/cases/{case_id}/facts/{fact_key}/candidates")
def get_candidates(case_id: str, fact_key: str) -> Dict[str, Any]:
    obs = store.get_observations(case_id, fact_key)
    if not obs and case_id not in store.states:
        raise HTTPException(status_code=404, detail="case not found")
    timeline = store.timeline_event_times(case_id)
    previous = store.get_fact_value(case_id, fact_key)
    decision = synchronize(
        case_id=case_id,
        fact_key=fact_key,
        observations=obs,
        timeline=timeline,
        previous_value=previous,
    )
    return decision.model_dump()


@app.get("/cases/{case_id}/unresolved")
def get_unresolved(case_id: str) -> Dict[str, Any]:
    store.ensure_case(case_id)
    return {"case_id": case_id, "unresolved": store.get_unresolved(case_id)}
