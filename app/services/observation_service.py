"""
OWNER: Person C
Integration point: ingestion -> factors -> CAMS synchronize -> TwinState.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cams.engine import synchronize
from app.cams.factors import FactorCalculator
from app.cams.models import CAMSWeights, Candidate
from app.core import demo_log
from app.models.case import Case, Entity
from app.models.observation import FactKey, Observation, SyncDecision, TwinState
from app.models.source_authority import CAMSConfig, SourceAuthorityRule
from app.models.user import User
from app.schemas.observation import ObservationCreate


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ObservationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(self, payload: ObservationCreate, user: User) -> dict[str, Any]:
        demo_log.banner("JUSTICE DIGITAL TWIN — OBSERVATION INGEST PIPELINE")

        # --- Step 1: validate case/entity ---
        demo_log.step(1, "Validate case and entity exist", case_id=payload.case_id, entity_id=payload.entity_id)
        case = (
            await self.db.execute(select(Case).where(Case.id == payload.case_id))
        ).scalar_one_or_none()
        if case is None:
            raise ValueError("Case not found")
        entity = (
            await self.db.execute(
                select(Entity).where(
                    Entity.id == payload.entity_id,
                    Entity.case_id == payload.case_id,
                )
            )
        ).scalar_one_or_none()
        if entity is None:
            raise ValueError("Entity not found for this case")
        demo_log.success(f"Case '{case.case_number}' / Entity '{entity.label}' OK")

        # --- Step 2: resolve / create FactKey ---
        demo_log.step(2, "Resolve FactKey", fact_name=payload.fact_name)
        fact_key = await self._get_or_create_fact_key(
            payload.case_id, payload.entity_id, payload.fact_name
        )
        demo_log.success(f"FactKey id={fact_key.id}")

        # --- Step 3: append Observation (never overwrite) ---
        demo_log.step(
            3,
            "Append Observation (append-only)",
            source_role=payload.source_role,
            value=payload.candidate_value,
            extraction_reliability=payload.extraction_reliability,
        )
        observation = Observation(
            fact_key_id=fact_key.id,
            case_id=payload.case_id,
            source_id=user.id,
            source_role=payload.source_role,
            candidate_value=payload.candidate_value,
            event_time=payload.event_time,
            extraction_reliability=(
                1.0 if payload.extraction_reliability is None else payload.extraction_reliability
            ),
            raw_source_ref=payload.raw_source_ref,
            status="pending",
        )
        self.db.add(observation)
        await self.db.flush()
        demo_log.success(f"Stored observation id={observation.id}")

        # --- Step 4: load CAMS config + authority rules ---
        demo_log.step(4, "Load CAMS weights / tau / delta and authority rules")
        weights, tau, delta = await self._load_cams_config(payload.case_id)
        rules = await self._load_authority_rules()
        calc = FactorCalculator(authority_rules=rules)
        demo_log.info(
            "CAMS config",
            w_A=weights.w_A,
            w_T=weights.w_T,
            w_X=weights.w_X,
            w_E=weights.w_E,
            tau=tau,
            delta=delta,
        )

        # --- Step 5: build Candidates with A/T/X/E ---
        demo_log.step(5, "Compute A/T/X/E factors for all observations on this fact")
        obs_rows = (
            await self.db.execute(
                select(Observation).where(Observation.fact_key_id == fact_key.id)
            )
        ).scalars().all()

        twin = (
            await self.db.execute(
                select(TwinState).where(TwinState.fact_key_id == fact_key.id)
            )
        ).scalar_one_or_none()
        chron_anchor = twin.updated_at if twin and twin.updated_at else None

        candidates: list[Candidate] = []
        for row in obs_rows:
            agreeing = {
                o.source_id
                for o in obs_rows
                if o.source_id != row.source_id and o.candidate_value == row.candidate_value
            }
            cand = calc.build_candidate(
                observation_id=row.id,
                value=row.candidate_value,
                source_role=row.source_role,
                fact_type=payload.fact_name,
                event_time=row.event_time,
                known_chronology_anchor=chron_anchor,
                independent_source_count=len(agreeing),
                extraction_reliability=row.extraction_reliability,
            )
            candidates.append(cand)
            demo_log.info(
                f"Candidate {row.id[:8]}… role={row.source_role}",
                A=round(cand.A, 3),
                T=round(cand.T, 3),
                X=round(cand.X, 3),
                E=round(cand.E, 3),
                value=cand.value,
            )

        # --- Step 6: synchronize ---
        demo_log.step(6, "Run CAMS synchronize() — Algorithm 1")
        result = synchronize(candidates, weights, tau, delta)
        demo_log.info(
            "SyncResult",
            decision=result.decision,
            c1=round(result.c1, 4),
            c2=None if result.c2 is None else round(result.c2, 4),
            explanation=result.explanation,
            winner=None if result.winner is None else result.winner.observation_id,
            scores={k[:8] + "…": round(v, 4) for k, v in result.scores.items()},
        )

        # --- Step 7: persist SyncDecision ---
        demo_log.step(7, "Persist SyncDecision audit row")
        snapshot = {
            c.observation_id: {
                "value": c.value,
                "A": c.A,
                "T": c.T,
                "X": c.X,
                "E": c.E,
                "score": result.scores.get(c.observation_id),
            }
            for c in candidates
        }
        decision_row = SyncDecision(
            fact_key_id=fact_key.id,
            winning_observation_id=None if result.winner is None else result.winner.observation_id,
            candidates_snapshot=snapshot,
            c1=result.c1,
            c2=result.c2,
            tau=tau,
            delta=delta,
            decision=result.decision,
            explanation=result.explanation[:255],
        )
        self.db.add(decision_row)

        # --- Step 8: update TwinState only if "updated" ---
        twin_updated = False
        demo_log.step(8, "Update Justice Digital Twin state (only if decision=updated)")
        if result.decision == "updated" and result.winner is not None:
            if twin is None:
                twin = TwinState(
                    case_id=payload.case_id,
                    fact_key_id=fact_key.id,
                    current_value=result.winner.value,
                    confidence=result.c1,
                    source_observation_id=result.winner.observation_id,
                    updated_at=_utcnow(),
                )
                self.db.add(twin)
            else:
                twin.current_value = result.winner.value
                twin.confidence = result.c1
                twin.source_observation_id = result.winner.observation_id
                twin.updated_at = _utcnow()
            twin_updated = True
            observation.status = "accepted"
            demo_log.success(
                f"Twin UPDATED → value={result.winner.value} confidence={result.c1:.4f}"
            )
        else:
            observation.status = "retained" if result.decision == "retained" else "unresolved"
            demo_log.warn(
                f"Twin NOT changed (decision={result.decision}) — prior state kept"
            )

        await self.db.commit()
        await self.db.refresh(observation)
        demo_log.banner("PIPELINE COMPLETE")

        return {
            "observation": observation,
            "sync": result,
            "twin_updated": twin_updated,
            "fact_key_id": fact_key.id,
        }

    async def _get_or_create_fact_key(
        self, case_id: str, entity_id: str, fact_name: str
    ) -> FactKey:
        existing = (
            await self.db.execute(
                select(FactKey).where(
                    FactKey.case_id == case_id,
                    FactKey.entity_id == entity_id,
                    FactKey.fact_name == fact_name,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        fk = FactKey(case_id=case_id, entity_id=entity_id, fact_name=fact_name)
        self.db.add(fk)
        await self.db.flush()
        return fk

    async def _load_cams_config(self, case_id: str) -> tuple[CAMSWeights, float, float]:
        cfg = (
            await self.db.execute(
                select(CAMSConfig).where(
                    CAMSConfig.is_active.is_(True),
                    CAMSConfig.case_id == case_id,
                )
            )
        ).scalar_one_or_none()
        if cfg is None:
            cfg = (
                await self.db.execute(
                    select(CAMSConfig).where(
                        CAMSConfig.is_active.is_(True),
                        CAMSConfig.case_id.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if cfg is None:
            return CAMSWeights(0.3, 0.3, 0.2, 0.2), 0.6, 0.1
        return (
            CAMSWeights(
                cfg.weight_authority,
                cfg.weight_temporal,
                cfg.weight_corroboration,
                cfg.weight_extraction,
            ),
            cfg.tau,
            cfg.delta,
        )

    async def _load_authority_rules(self) -> dict[tuple[str, str], float]:
        rows = (await self.db.execute(select(SourceAuthorityRule))).scalars().all()
        if not rows:
            return dict(FactorCalculator.DEFAULT_AUTHORITY_RULES)
        return {(r.fact_type, r.source_role): r.authority_score for r in rows}
