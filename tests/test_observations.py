"""OWNER: Person C — observation ingest, CAMS integration, twin/ODFS, API tests."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.observation import Observation, SyncDecision, TwinState, TwinStateVersion
from app.models.user import User
from tests.conftest import auth_header


async def _case_and_entity(client: AsyncClient, user: User) -> tuple[str, str]:
    case = (
        await client.post(
            "/cases",
            json={"case_number": f"C-{user.role}-{uuid.uuid4().hex[:10]}", "title": "Person C Case"},
            headers=auth_header(user),
        )
    ).json()
    entity = (
        await client.post(
            f"/cases/{case['id']}/entities",
            json={"entity_type": "person", "label": "Accused", "attributes": {}},
            headers=auth_header(user),
        )
    ).json()
    return case["id"], entity["id"]


def _obs(
    case_id: str,
    entity_id: str,
    *,
    fact_name: str = "bail_status",
    source_role: str = "court",
    value: dict | None = None,
    extraction_reliability: float | None = None,
    event_time: str | None = None,
) -> dict:
    payload: dict = {
        "case_id": case_id,
        "entity_id": entity_id,
        "fact_name": fact_name,
        "source_role": source_role,
        "candidate_value": value or {"status": "granted"},
    }
    if extraction_reliability is not None:
        payload["extraction_reliability"] = extraction_reliability
    if event_time is not None:
        payload["event_time"] = event_time
    return payload


@pytest.mark.asyncio
async def test_citizen_cannot_ingest(client: AsyncClient, citizen_user: User, police_user: User):
    case_id, entity_id = await _case_and_entity(client, police_user)
    resp = await client.post(
        "/observations",
        json=_obs(case_id, entity_id),
        headers=auth_header(citizen_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_normal_observation_updates_twin(
    client: AsyncClient, court_user: User, db_session: AsyncSession
):
    case_id, entity_id = await _case_and_entity(client, court_user)
    resp = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="court", value={"status": "granted"}),
        headers=auth_header(court_user),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["sync"]["decision"] == "updated"
    assert body["twin_updated"] is True
    assert body["observation"]["status"] == "accepted"

    listed = await client.get(
        f"/observations?case_id={case_id}",
        headers=auth_header(court_user),
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    one = await client.get(
        f"/observations/{body['observation']['id']}",
        headers=auth_header(court_user),
    )
    assert one.status_code == 200

    twin = await client.get(f"/twin/{case_id}", headers=auth_header(court_user))
    assert twin.status_code == 200
    facts = twin.json()["facts"]
    assert len(facts) == 1
    assert facts[0]["current_value"] == {"status": "granted"}
    assert facts[0]["version"] == 1
    assert facts[0]["confidence"] is not None and facts[0]["confidence"] >= 0.6

    versions = await client.get(
        f"/twin/{case_id}/facts/{body['fact_key_id']}/versions",
        headers=auth_header(court_user),
    )
    assert versions.status_code == 200
    assert len(versions.json()) == 1

    decisions = (
        await db_session.execute(select(SyncDecision).where(SyncDecision.fact_key_id == body["fact_key_id"]))
    ).scalars().all()
    assert len(decisions) == 1
    assert decisions[0].decision == "updated"


@pytest.mark.asyncio
async def test_conflicting_observations_court_beats_police(
    client: AsyncClient, court_user: User, police_user: User
):
    case_id, entity_id = await _case_and_entity(client, police_user)
    first = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="court", value={"status": "granted"}),
        headers=auth_header(court_user),
    )
    assert first.json()["twin_updated"] is True

    second = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="police", value={"status": "denied"}),
        headers=auth_header(police_user),
    )
    assert second.status_code == 201
    body = second.json()
    assert body["sync"]["c1"] > body["sync"]["c2"]
    winner = body["sync"]["winner_observation_id"]
    assert winner == first.json()["observation"]["id"]
    twin = await client.get(f"/twin/{case_id}", headers=auth_header(court_user))
    assert twin.json()["facts"][0]["current_value"] == {"status": "granted"}


@pytest.mark.asyncio
async def test_delayed_observation_loses_on_temporal(
    client: AsyncClient, court_user: User, police_user: User
):
    case_id, entity_id = await _case_and_entity(client, police_user)
    now = datetime.now(UTC).replace(tzinfo=None)
    await client.post(
        "/observations",
        json=_obs(
            case_id,
            entity_id,
            source_role="court",
            value={"status": "granted"},
            event_time=now.isoformat(),
        ),
        headers=auth_header(court_user),
    )
    delayed = now - timedelta(days=25)
    resp = await client.post(
        "/observations",
        json=_obs(
            case_id,
            entity_id,
            source_role="police",
            value={"status": "denied"},
            event_time=delayed.isoformat(),
        ),
        headers=auth_header(police_user),
    )
    body = resp.json()
    snapshot = body["sync"]["scores"]
    court_id = next(k for k, v in snapshot.items() if k != body["observation"]["id"])
    assert snapshot[court_id] > snapshot[body["observation"]["id"]]
    twin = (await client.get(f"/twin/{case_id}", headers=auth_header(court_user))).json()
    assert twin["facts"][0]["current_value"] == {"status": "granted"}


@pytest.mark.asyncio
async def test_duplicate_observation_retained(
    client: AsyncClient, court_user: User
):
    case_id, entity_id = await _case_and_entity(client, court_user)
    payload = _obs(case_id, entity_id, source_role="court", value={"status": "granted"})
    first = await client.post("/observations", json=payload, headers=auth_header(court_user))
    assert first.json()["sync"]["decision"] == "updated"
    second = await client.post("/observations", json=payload, headers=auth_header(court_user))
    assert second.status_code == 201
    assert second.json()["is_duplicate"] is True
    assert second.json()["sync"]["decision"] == "retained"
    assert second.json()["twin_updated"] is False


@pytest.mark.asyncio
async def test_corroborated_observations_raise_x(
    client: AsyncClient, court_user: User, police_user: User, lawyer_user: User
):
    case_id, entity_id = await _case_and_entity(client, police_user)
    value = {"status": "granted"}
    r1 = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="court", value=value),
        headers=auth_header(court_user),
    )
    r2 = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="police", value=value),
        headers=auth_header(police_user),
    )
    r3 = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="lawyer", value=value),
        headers=auth_header(lawyer_user),
    )
    assert r3.status_code == 201
    snap = r3.json()["sync"]
    assert snap["decision"] == "updated"
    # three independent sources agreeing → X = 2/3 for each candidate
    court_score = snap["scores"][r1.json()["observation"]["id"]]
    assert court_score > r1.json()["sync"]["c1"]
    assert r2.json()["twin_updated"] is True


@pytest.mark.asyncio
async def test_noisy_low_extraction_loses(
    client: AsyncClient, forensic_user: User, police_user: User
):
    case_id, entity_id = await _case_and_entity(client, police_user)
    clean = await client.post(
        "/observations",
        json=_obs(
            case_id,
            entity_id,
            fact_name="forensic_result",
            source_role="forensic",
            value={"result": "match"},
            extraction_reliability=1.0,
        ),
        headers=auth_header(forensic_user),
    )
    assert clean.json()["sync"]["decision"] == "updated"
    noisy = await client.post(
        "/observations",
        json=_obs(
            case_id,
            entity_id,
            fact_name="forensic_result",
            source_role="forensic",
            value={"result": "no_match"},
            extraction_reliability=0.15,
        ),
        headers=auth_header(forensic_user),
    )
    body = noisy.json()
    clean_id = clean.json()["observation"]["id"]
    noisy_id = body["observation"]["id"]
    assert body["sync"]["scores"][clean_id] > body["sync"]["scores"][noisy_id]
    twin = (await client.get(f"/twin/{case_id}", headers=auth_header(forensic_user))).json()
    fact = next(f for f in twin["facts"] if f["fact_name"] == "forensic_result")
    assert fact["current_value"] == {"result": "match"}


@pytest.mark.asyncio
async def test_low_confidence_unresolved(
    client: AsyncClient, lawyer_user: User, police_user: User, db_session: AsyncSession
):
    case_id, entity_id = await _case_and_entity(client, police_user)
    resp = await client.post(
        "/observations",
        json=_obs(
            case_id,
            entity_id,
            fact_name="identity",
            source_role="lawyer",
            value={"name": "unknown"},
            extraction_reliability=0.2,
        ),
        headers=auth_header(lawyer_user),
    )
    body = resp.json()
    assert body["sync"]["decision"] == "unresolved"
    assert body["twin_updated"] is False
    assert body["observation"]["status"] == "unresolved"

    twins = (
        await db_session.execute(select(TwinState).where(TwinState.case_id == case_id))
    ).scalars().all()
    assert twins == []
    versions = (
        await db_session.execute(select(TwinStateVersion).where(TwinStateVersion.case_id == case_id))
    ).scalars().all()
    assert versions == []


@pytest.mark.asyncio
async def test_odfs_versions_append_only(
    client: AsyncClient, court_user: User, police_user: User, db_session: AsyncSession
):
    case_id, entity_id = await _case_and_entity(client, police_user)
    await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="police", value={"status": "pending"}),
        headers=auth_header(police_user),
    )
    court = await client.post(
        "/observations",
        json=_obs(case_id, entity_id, source_role="court", value={"status": "granted"}),
        headers=auth_header(court_user),
    )
    fact_key_id = court.json()["fact_key_id"]
    versions = (
        await db_session.execute(
            select(TwinStateVersion)
            .where(TwinStateVersion.fact_key_id == fact_key_id)
            .order_by(TwinStateVersion.version.asc())
        )
    ).scalars().all()
    # police first observation is below tau (0.515 < 0.6) so only court creates v1
    assert all(v.version == i + 1 for i, v in enumerate(versions))
    obs_count = (
        await db_session.execute(select(Observation).where(Observation.case_id == case_id))
    ).scalars().all()
    assert len(obs_count) == 2


@pytest.mark.asyncio
async def test_missing_case_404(client: AsyncClient, court_user: User):
    resp = await client.post(
        "/observations",
        json=_obs("missing-case", "missing-entity"),
        headers=auth_header(court_user),
    )
    assert resp.status_code == 404
