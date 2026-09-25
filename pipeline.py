"""
End-to-end pipeline:
  text/OCR → Gemini (or fallback) → observations (PostgreSQL) → CAMS → Digital Twin → history/conflicts
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from cams import synchronize
from config import DELTA, TAU, WEIGHTS
import console_log as clog
from db_repository import DbRepository
from gemini_extractor import extract_from_text
from models import Observation
from ocr import ocr_file


def _parse_dt(value: Any, fallback: Optional[datetime] = None) -> datetime:
    if value is None or value == "":
        return fallback or datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return fallback or datetime.now(timezone.utc)


def _obs_from_dict(d: Dict[str, Any]) -> Observation:
    return Observation(
        observation_id=d.get("observation_id") or str(uuid4()),
        case_id=d["case_id"],
        fact_key=d["fact_key"],
        value=d["value"],
        source_id=d.get("source_id") or d.get("source") or "unknown",
        source_type=d.get("source_type") or "unknown",
        event_time=_parse_dt(d.get("event_time")),
        ingestion_time=_parse_dt(d.get("ingestion_time")),
        extraction_reliability=float(
            d.get("extraction_reliability", d.get("extraction_confidence", 0.7))
        ),
        evidence=d.get("evidence") or "",
        status=d.get("status") or "recorded",
        document_id=d.get("document_id"),
    )


def _plain_english(decision: Any, top_factors: Optional[Dict[str, float]] = None) -> str:
    parts: List[str] = []
    if decision.decided:
        parts.append(f"The system ACCEPTED “{decision.accepted_value}” for {decision.fact_key}.")
        if decision.C1 is not None:
            parts.append(f"Top confidence C1={decision.C1:.3f} met threshold τ={decision.tau}.")
        if decision.C2 is not None and decision.margin is not None:
            parts.append(
                f"It beat the next candidate by margin {decision.margin:.3f} (need ≥ δ={decision.delta})."
            )
    else:
        parts.append(
            f"The system ABSTAINED on {decision.fact_key} and did not replace the current Digital Twin value."
        )
        parts.append(decision.message)
        parts.append("All competing observations are kept for provenance.")

    if top_factors:
        a = top_factors.get("source_authority")
        t = top_factors.get("temporal_consistency")
        x = top_factors.get("cross_source_corroboration")
        e = top_factors.get("extraction_reliability")
        if a is not None and a >= 0.8:
            parts.append("This source type is considered more authoritative for this fact (high A).")
        if a is not None and a <= 0.4:
            parts.append("This source type has lower authority for this fact (low A).")
        if t is not None and t < 0.5:
            parts.append("The event timing looks inconsistent with the case timeline (low T).")
        if t is not None and t >= 0.85:
            parts.append("The event timing fits the known timeline well (high T).")
        if x is not None and x >= 0.66:
            parts.append("This value is supported by multiple distinct sources (high X).")
        if x is not None and x <= 0.34:
            parts.append("Few distinct sources agree on this value (low X).")
        if e is not None and e < 0.4:
            parts.append("Extraction confidence for this claim is low (low E).")
        if e is not None and e >= 0.85:
            parts.append("Extraction confidence for this claim is high (high E).")

    if not decision.decided and decision.C2 is not None and decision.margin is not None:
        if decision.margin < decision.delta:
            parts.append(
                "The evidence is inconsistent or too close to call, so the system did not replace the current state."
            )
    return " ".join(parts)


class Pipeline:
    def __init__(self, repository: Optional[DbRepository] = None) -> None:
        self.repo = repository or DbRepository()

    async def create_case(
        self,
        case_id: Optional[str] = None,
        title: str = "Untitled case",
        description: str = "",
        case_type: Optional[str] = None,
        case_status: Optional[str] = None,
        filing_date: Any = None,
        court_name: Optional[str] = None,
        next_hearing_date: Any = None,
    ) -> Dict[str, Any]:
        meta = await self.repo.create_case(
            case_id=case_id,
            title=title,
            description=description,
            case_type=case_type,
            case_status=case_status,
            filing_date=filing_date,
            court_name=court_name,
            next_hearing_date=next_hearing_date,
        )
        clog.banner("CREATE CASE", meta["case_id"])
        clog.kv("title", meta.get("title"))
        clog.kv("folder", str(self.repo.root / meta["case_id"]))
        clog.done("case folder ready (stakeholders/ + uploads/ created)")
        return meta

    async def ingest_text(
        self,
        case_id: str,
        text: str,
        source: str = "user",
        source_type: str = "unknown",
        title: str = "",
        force_fallback: bool = False,
        ocr_meta: Optional[Dict[str, Any]] = None,
        visibility: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.repo.ensure_case(case_id)
        now = datetime.now(timezone.utc)
        document_id = str(uuid4())

        clog.banner("INPUT", case_id)
        clog.kv("source", f"{source_type} / {source}")
        clog.kv("chars", len(text or ""))
        clog.kv("title", title or "(none)")
        if ocr_meta:
            clog.kv("came_from_ocr", ocr_meta.get("method"))
            clog.detail(ocr_meta.get("note") or "")

        previous_obs = len(await self.repo.get_observations(case_id))
        previous_docs = len(await self.repo.get_documents(case_id))
        clog.step(f"Case already has {previous_docs} documents and {previous_obs} observations (kept)")

        clog.banner("EXTRACTION (Gemini or fallback)", case_id)
        clog.step("Gemini extracts facts + quotes only — it does NOT resolve conflicts")
        extraction = extract_from_text(text, source_type=source_type, force_fallback=force_fallback)
        clog.kv("extractor", extraction["extractor"])
        clog.detail(extraction["note"])
        for f in extraction["facts"]:
            clog.detail(
                f"fact {f['fact_key']} = {f['value']!r}  E={f.get('extraction_confidence')}  "
                f"evidence={f.get('evidence')!r}"
            )

        doc = {
            "document_id": document_id,
            "case_id": case_id,
            "source": source,
            "source_id": source,
            "source_type": source_type,
            "title": title or f"{source_type}:{source}",
            "text": text,
            "ingestion_time": now.isoformat(),
            "extractor": extraction["extractor"],
            "extractor_note": extraction["note"],
            "ocr": ocr_meta,
            "visibility": visibility or "INTERNAL",
        }
        await self.repo.append_document(case_id, doc)
        clog.banner("DATABASE STORAGE", case_id)
        clog.step("Appended document row (never deletes old ones)")
        clog.kv(
            "stakeholder_folder",
            str(self.repo.stakeholder_dir(case_id, source_type, source)),
        )

        new_obs: List[Dict[str, Any]] = []
        for fact in extraction["facts"]:
            event_time = _parse_dt(fact.get("event_time"), fallback=now)
            conf = float(fact.get("extraction_confidence", 0.7))
            oid = str(uuid4())
            obs = {
                "observation_id": oid,
                "case_id": case_id,
                "source": source,
                "source_id": source,
                "source_type": source_type,
                "fact_key": fact["fact_key"],
                "value": fact["value"],
                "event_time": event_time.isoformat(),
                "ingestion_time": now.isoformat(),
                "evidence": fact.get("evidence") or "",
                "extraction_confidence": conf,
                "extraction_reliability": conf,
                "status": "recorded",
                "document_id": document_id,
            }
            new_obs.append(obs)

        if new_obs:
            await self.repo.append_observations(case_id, new_obs)
            clog.step(f"Appended {len(new_obs)} observation rows")
            clog.kv("total_observations_now", len(await self.repo.get_observations(case_id)))

        fact_keys = sorted({o["fact_key"] for o in new_obs}) or []
        decisions = []
        for fk in fact_keys:
            decisions.append(
                await self._run_cams_for_fact(case_id, fk, trigger_document_id=document_id)
            )

        result = {
            "case_id": case_id,
            "document": doc,
            "extraction": {
                "extractor": extraction["extractor"],
                "note": extraction["note"],
                "facts": extraction["facts"],
            },
            "observations_created": new_obs,
            "decisions": decisions,
            "facts": await self.repo.get_facts(case_id),
            "conflicts": await self.repo.get_conflicts(case_id),
            "history_tail": (await self.repo.get_history(case_id))[-len(decisions) :] if decisions else [],
            "case_view": await self.full_case_view(case_id),
        }
        clog.banner("CASE SNAPSHOT AFTER THIS UPDATE", case_id)
        clog.kv("documents", len(await self.repo.get_documents(case_id)))
        clog.kv("observations", len(await self.repo.get_observations(case_id)))
        clog.kv("twin_facts", list((await self.repo.get_facts(case_id)).keys()))
        clog.kv("conflicts", list((await self.repo.get_conflicts(case_id)).keys()) or "(none)")
        clog.done("pipeline finished — prior case data preserved")
        return result

    async def ingest_upload(
        self,
        case_id: str,
        filename: str,
        data: bytes,
        source: str = "user",
        source_type: str = "unknown",
        content_type: Optional[str] = None,
        force_fallback: bool = False,
        title: str = "",
        visibility: Optional[str] = None,
    ) -> Dict[str, Any]:
        clog.banner("UPLOAD / OCR", case_id)
        clog.kv("filename", filename)
        clog.kv("bytes", len(data))
        clog.kv("content_type", content_type or "(unknown)")
        clog.kv("stakeholder", f"{source_type}/{source}")

        ocr = ocr_file(data, filename=filename, content_type=content_type)
        clog.kv("ocr_ok", ocr.get("ok"))
        clog.kv("ocr_method", ocr.get("method"))
        clog.detail(ocr.get("note") or "")
        if ocr.get("text"):
            preview = ocr["text"][:240].replace("\n", " / ")
            clog.detail(f"text preview: {preview}{'…' if len(ocr['text']) > 240 else ''}")

        upload_record = await self.repo.save_upload(
            case_id=case_id,
            source_type=source_type,
            source_id=source,
            filename=filename,
            data=data,
            extracted_text=ocr.get("text") or "",
            extra_meta={"ocr_method": ocr.get("method"), "ocr_note": ocr.get("note")},
        )
        clog.step("Saved raw file under case/uploads and stakeholders/.../documents")
        clog.kv("saved_as", upload_record.get("stored_filename"))
        if upload_record.get("extracted_text_path"):
            clog.kv("extracted_md", str(upload_record["extracted_text_path"]))
            clog.detail("Extracted text saved to disk before Gemini — inspect it to check extraction quality")

        if not ocr.get("ok"):
            clog.done("OCR produced no text — file stored; paste text to continue extraction")
            return {
                "case_id": case_id,
                "ocr": ocr,
                "upload": upload_record,
                "pipeline_ran": False,
                "message": ocr.get("note"),
                "case_view": await self.full_case_view(case_id),
            }

        result = await self.ingest_text(
            case_id=case_id,
            text=ocr["text"],
            source=source,
            source_type=source_type,
            title=title or f"OCR:{filename}",
            force_fallback=force_fallback,
            visibility=visibility,
            ocr_meta={
                "method": ocr.get("method"),
                "note": ocr.get("note"),
                "filename": filename,
                "upload": upload_record,
            },
        )
        result["ocr"] = ocr
        result["upload"] = upload_record
        result["pipeline_ran"] = True
        return result

    async def _run_cams_for_fact(
        self,
        case_id: str,
        fact_key: str,
        trigger_document_id: Optional[str] = None,
        trigger_observation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        stored = await self.repo.get_observations(case_id, fact_key)
        observations = [_obs_from_dict(o) for o in stored]
        timeline = [
            _parse_dt(o.get("event_time")) for o in await self.repo.get_observations(case_id)
        ]
        previous = await self.repo.get_fact_value(case_id, fact_key)

        clog.banner(f"CAMS — fact `{fact_key}`", case_id)
        clog.kv("observations_for_fact", len(stored))
        clog.kv("previous_twin_value", previous)
        clog.kv("weights", WEIGHTS)
        clog.kv("tau", TAU)
        clog.kv("delta", DELTA)
        clog.step("Scoring each candidate with C = wA·A + wT·T + wX·X + wE·E")

        decision = synchronize(
            case_id=case_id,
            fact_key=fact_key,
            observations=observations,
            timeline=timeline,
            previous_value=previous,
            tau=TAU,
            delta=DELTA,
            weights=WEIGHTS,
        )

        supporting: List[str] = []
        top_factors = None
        if decision.candidates:
            supporting = list(decision.candidates[0].supporting_observation_ids)
            top_factors = decision.candidates[0].factors.model_dump()
            clog.step("Candidates (highest C first):")
            for c in decision.candidates:
                clog.detail(clog.cams_candidate_line(c.value, c.confidence, c.factors.model_dump()))

        explanation = _plain_english(decision, top_factors)
        clog.kv("C1", decision.C1)
        clog.kv("C2", decision.C2)
        clog.kv("margin", decision.margin)
        clog.kv("decision", "ACCEPTED" if decision.decided else "ABSTAINED")
        clog.detail(explanation)

        # History is appended first so provenance rows can reference it.
        history_entry = {
            "history_id": str(uuid4()),
            "case_id": case_id,
            "fact_key": fact_key,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decision": "ACCEPTED" if decision.decided else "ABSTAINED",
            "decided": decision.decided,
            "selected_value": decision.accepted_value if decision.decided else None,
            "previous_value": previous,
            "unresolved": not decision.decided,
            "C1": decision.C1,
            "C2": decision.C2,
            "margin": decision.margin,
            "tau": decision.tau,
            "delta": decision.delta,
            "weights": dict(WEIGHTS),
            "candidates": [c.model_dump() for c in decision.candidates],
            "supporting_observation_ids": supporting,
            "reason": decision.message,
            "explanation": explanation,
            "trigger_document_id": trigger_document_id,
            "trigger_observation_id": trigger_observation_id,
        }
        await self.repo.append_history(case_id, history_entry)

        if decision.decided:
            provenance = []
            by_id = {o["observation_id"]: o for o in stored}
            for oid in supporting:
                if oid in by_id:
                    o = by_id[oid]
                    provenance.append(
                        {
                            "observation_id": oid,
                            "source": o.get("source") or o.get("source_id"),
                            "source_type": o.get("source_type"),
                            "value": o.get("value"),
                            "evidence": o.get("evidence"),
                            "document_id": o.get("document_id"),
                        }
                    )
            await self.repo.set_fact(
                case_id,
                fact_key,
                {
                    "fact_key": fact_key,
                    "value": decision.accepted_value,
                    "status": "resolved",
                    "confidence": decision.C1,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "supporting_observation_ids": supporting,
                    "provenance": provenance,
                },
            )
            await self.repo.append_provenance(
                case_id, fact_key, history_entry["history_id"], provenance
            )
            await self.repo.clear_conflict(case_id, fact_key)
            clog.step("Digital Twin updated in PostgreSQL")
        else:
            competing = []
            for c in decision.candidates:
                competing.append(
                    {
                        "value": c.value,
                        "confidence": c.confidence,
                        "factors": c.factors.model_dump(),
                        "supporting_observation_ids": c.supporting_observation_ids,
                        "supporting_source_ids": c.supporting_source_ids,
                    }
                )
            await self.repo.set_conflict(
                case_id,
                fact_key,
                {
                    "fact_key": fact_key,
                    "status": "unresolved",
                    "reason": decision.message,
                    "explanation": explanation,
                    "previous_value": previous,
                    "C1": decision.C1,
                    "C2": decision.C2,
                    "margin": decision.margin,
                    "candidates": competing,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            facts = await self.repo.get_facts(case_id)
            if fact_key not in facts:
                await self.repo.set_fact(
                    case_id,
                    fact_key,
                    {
                        "fact_key": fact_key,
                        "value": previous,
                        "status": "unresolved",
                        "confidence": decision.C1,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "supporting_observation_ids": supporting,
                        "provenance": [],
                    },
                )
            clog.step("ABSTAIN: twin value NOT overwritten; conflict stored in PostgreSQL")

        clog.step("Appended decision to sync_history")
        return history_entry

    async def resync(self, case_id: str) -> Dict[str, Any]:
        await self.repo.ensure_case(case_id)
        keys = sorted({o["fact_key"] for o in await self.repo.get_observations(case_id)})
        clog.banner("RESYNC ALL FACTS FROM STORED OBSERVATIONS", case_id)
        clog.kv("fact_keys", keys)
        decisions = [await self._run_cams_for_fact(case_id, fk) for fk in keys]
        return {
            "case_id": case_id,
            "decisions": decisions,
            "facts": await self.repo.get_facts(case_id),
            "conflicts": await self.repo.get_conflicts(case_id),
            "case_view": await self.full_case_view(case_id),
        }

    async def case_snapshot(self, case_id: str) -> Dict[str, Any]:
        meta = await self.repo.get_case(case_id)
        return {
            **meta,
            "facts": await self.repo.get_facts(case_id),
            "conflicts": await self.repo.get_conflicts(case_id),
            "observation_count": len(await self.repo.get_observations(case_id)),
            "document_count": len(await self.repo.get_documents(case_id)),
            "history_count": len(await self.repo.get_history(case_id)),
            "stakeholders": await self.repo.list_stakeholders(case_id),
        }

    async def full_case_view(self, case_id: str) -> Dict[str, Any]:
        """
        Continuous case board: everything for this case_id, chronological.
        """
        await self.repo.ensure_case(case_id)
        docs = await self.repo.get_documents(case_id)
        obs = await self.repo.get_observations(case_id)
        history = await self.repo.get_history(case_id)
        facts = await self.repo.get_facts(case_id)
        conflicts = await self.repo.get_conflicts(case_id)
        stakeholders = await self.repo.list_stakeholders(case_id)

        timeline = []
        for d in docs:
            timeline.append(
                {
                    "kind": "document",
                    "at": d.get("ingestion_time"),
                    "source": d.get("source") or d.get("source_id"),
                    "source_type": d.get("source_type"),
                    "title": d.get("title"),
                    "document_id": d.get("document_id"),
                    "preview": (d.get("text") or "")[:280],
                    "ocr": d.get("ocr"),
                    "extractor": d.get("extractor"),
                }
            )
        for h in history:
            timeline.append(
                {
                    "kind": "cams_decision",
                    "at": h.get("timestamp"),
                    "fact_key": h.get("fact_key"),
                    "decision": h.get("decision"),
                    "selected_value": h.get("selected_value"),
                    "previous_value": h.get("previous_value"),
                    "C1": h.get("C1"),
                    "C2": h.get("C2"),
                    "margin": h.get("margin"),
                    "explanation": h.get("explanation"),
                }
            )
        timeline.sort(key=lambda x: x.get("at") or "")

        return {
            "case": await self.repo.get_case(case_id),
            "summary": {
                "documents": len(docs),
                "observations": len(obs),
                "history_events": len(history),
                "twin_facts": len(facts),
                "conflicts": len(conflicts),
                "stakeholders": len(stakeholders),
            },
            "twin": facts,
            "conflicts": conflicts,
            "documents": docs,
            "observations": obs,
            "history": history,
            "stakeholders": stakeholders,
            "timeline": timeline,
            "storage_hint": str(self.repo.root / case_id),
        }

    async def provenance(self, case_id: str) -> Dict[str, Any]:
        facts = await self.repo.get_facts(case_id)
        obs_by_id = {
            o["observation_id"]: o for o in await self.repo.get_observations(case_id)
        }
        docs_by_id = {
            d["document_id"]: d for d in await self.repo.get_documents(case_id)
        }
        history = await self.repo.get_history(case_id)

        out: Dict[str, Any] = {}
        for fact_key, fact in facts.items():
            chain = []
            for oid in fact.get("supporting_observation_ids") or []:
                o = obs_by_id.get(oid)
                if not o:
                    continue
                doc = docs_by_id.get(o.get("document_id") or "")
                chain.append(
                    {
                        "observation": o,
                        "evidence": o.get("evidence"),
                        "document_id": o.get("document_id"),
                        "original_text": (doc or {}).get("text"),
                        "source": o.get("source") or o.get("source_id"),
                        "source_type": o.get("source_type"),
                    }
                )
            related_hist = [h for h in history if h.get("fact_key") == fact_key]
            out[fact_key] = {
                "current_fact": fact,
                "latest_decision": related_hist[-1] if related_hist else None,
                "trace": chain,
            }
        return {"case_id": case_id, "provenance": out}


pipeline = Pipeline()
