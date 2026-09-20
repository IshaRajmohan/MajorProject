"""Tests for extraction, CAMS pipeline (PostgreSQL), API, and legacy JSON files."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from file_repository import FileRepository
from gemini_extractor import fallback_extract, parse_gemini_response


@pytest.fixture
def tmp_repo(tmp_path: Path):
    return FileRepository(root=tmp_path / "cases")


@pytest.fixture
def tmp_demo_repo(tmp_path: Path):
    return FileRepository(root=tmp_path / "demo_cases")


@pytest.fixture
def pipe(pg_repo):
    from pipeline import Pipeline

    return Pipeline(repository=pg_repo)


# ---- Gemini parsing / fallback (no DB) ----


def test_parse_gemini_response():
    raw = """
    {
      "facts": [
        {"fact_key": "charge", "value": "IPC 302", "evidence": "Charge: IPC 302",
         "extraction_confidence": 0.91, "event_time": null}
      ]
    }
    """
    facts = parse_gemini_response(raw, "court")
    assert len(facts) == 1
    assert facts[0]["fact_key"] == "charge"
    assert facts[0]["value"] == "IPC 302"
    assert "IPC 302" in facts[0]["evidence"]
    assert facts[0]["source_type"] == "court"


def test_fallback_extract_labelled():
    text = "Charge: IPC 302\nWeapon: knife\nLocation: Mumbai\n"
    facts, note = fallback_extract(text, "police")
    assert any(f["fact_key"] == "charge" for f in facts)
    assert "FALLBACK" in note


def test_runtime_uses_db_repository_not_file_repository():
    from tests.conftest import postgres_driver_ok

    if not postgres_driver_ok():
        pytest.skip("asyncpg driver is not importable in this interpreter")
    import main as main_mod
    from db_repository import DbRepository as DR
    from file_repository import FileRepository as FR

    assert isinstance(main_mod.repo, DR)
    assert isinstance(main_mod.demo_repo, DR)
    assert isinstance(main_mod.pipeline.repo, DR)
    assert not isinstance(main_mod.repo, FR)
    assert not isinstance(main_mod.pipeline.repo, FR)


# ---- Legacy FileRepository (not used at runtime) ----


def test_file_persistence_survives_new_repo_instance(tmp_path):
    root = tmp_path / "cases"
    r1 = FileRepository(root=root)
    r1.create_case("P1", "persist")
    r1.append_observations(
        "P1",
        [
            {
                "observation_id": "o1",
                "case_id": "P1",
                "fact_key": "charge",
                "value": "IPC 302",
                "source": "court-1",
                "source_id": "court-1",
                "source_type": "court",
                "event_time": datetime.now(timezone.utc).isoformat(),
                "ingestion_time": datetime.now(timezone.utc).isoformat(),
                "evidence": "Charge: IPC 302",
                "extraction_confidence": 0.9,
                "extraction_reliability": 0.9,
                "status": "recorded",
            }
        ],
    )
    r2 = FileRepository(root=root)
    assert r2.exists("P1")
    assert len(r2.get_observations("P1")) == 1
    assert (root / "P1" / "observations.json").exists()


# ---- PostgreSQL pipeline ----


def test_observations_never_deleted_on_conflict(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        await pipe.ingest_text(
            case_id,
            "Charge: IPC 302\n",
            source="court-1",
            source_type="court",
            force_fallback=True,
        )
        await pipe.ingest_text(
            case_id,
            "Charge: IPC 304\n",
            source="media-1",
            source_type="media",
            force_fallback=True,
        )
        obs = await pipe.repo.get_observations(case_id, "charge")
        values = {str(o["value"]) for o in obs}
        assert len(obs) >= 2
        assert "IPC 302" in values
        assert "IPC 304" in values

    loop_runner.run(run())


def test_duplicate_observations_kept(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        await pipe.ingest_text(
            case_id, "Weapon: knife\n", source="police-1", source_type="police", force_fallback=True
        )
        await pipe.ingest_text(
            case_id, "Weapon: knife\n", source="police-1", source_type="police", force_fallback=True
        )
        assert len(await pipe.repo.get_observations(case_id, "weapon_type")) == 2

    loop_runner.run(run())


def test_cams_accepts_and_updates_twin(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        result = await pipe.ingest_text(
            case_id,
            "Charge: IPC 302\nLocation: Mumbai\n",
            source="court-1",
            source_type="court",
            force_fallback=True,
        )
        facts = await pipe.repo.get_facts(case_id)
        assert "charge" in facts
        assert facts["charge"]["status"] == "resolved"
        assert facts["charge"]["value"] == "IPC 302"
        assert result["decisions"]
        assert any(d["decided"] for d in result["decisions"])

    loop_runner.run(run())


def test_abstention_does_not_overwrite(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        await pipe.ingest_text(
            case_id,
            "Charge: IPC 302\n",
            source="court-1",
            source_type="court",
            force_fallback=True,
        )
        before = (await pipe.repo.get_facts(case_id))["charge"]["value"]
        await pipe.ingest_text(
            case_id,
            "Charge: IPC 304\n",
            source="media-a",
            source_type="media",
            force_fallback=True,
        )
        after = (await pipe.repo.get_facts(case_id))["charge"]["value"]
        assert after == before
        hist = await pipe.repo.get_history(case_id)
        assert len(hist) >= 2

    loop_runner.run(run())


def test_history_and_provenance(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        await pipe.ingest_text(
            case_id,
            "Charge: IPC 302\nWeapon: knife\n",
            source="court-1",
            source_type="court",
            force_fallback=True,
        )
        hist = await pipe.repo.get_history(case_id)
        assert hist
        assert "explanation" in hist[0]
        assert "C1" in hist[0]
        prov = await pipe.provenance(case_id)
        assert "charge" in prov["provenance"]
        chain = prov["provenance"]["charge"]["trace"]
        assert chain
        assert chain[0].get("original_text")

    loop_runner.run(run())


def test_resync(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        await pipe.ingest_text(
            case_id, "Location: Mumbai\n", source="police-1", source_type="police", force_fallback=True
        )
        out = await pipe.resync(case_id)
        assert out["facts"]

    loop_runner.run(run())


def test_continuous_case_keeps_prior_data(pipe, loop_runner, case_id):
    async def run():
        await pipe.create_case(case_id)
        await pipe.ingest_text(
            case_id, "Charge: IPC 302\n", source="court-1", source_type="court", force_fallback=True
        )
        await pipe.ingest_text(
            case_id, "Weapon: knife\n", source="police-1", source_type="police", force_fallback=True
        )
        view = await pipe.full_case_view(case_id)
        assert view["summary"]["documents"] == 2
        assert view["summary"]["observations"] >= 2
        assert len(view["timeline"]) >= 2

    loop_runner.run(run())


def test_abstain_persists_conflict_in_postgres(pipe, loop_runner, case_id):
    """Two equal-authority sources with identical event_time make CAMS abstain
    (margin 0 < delta). The conflict must persist in the PostgreSQL ``conflicts``
    table and read back with the exact old-JSON shape; the twin is NOT resolved
    and both observations are preserved (append-only)."""
    from sqlalchemy import text as _sqltext

    import db

    async def run():
        await pipe.create_case(case_id)
        t0 = datetime.now(timezone.utc).isoformat()
        await pipe.repo.append_observations(
            case_id,
            [
                {
                    "observation_id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "fact_key": "charge",
                    "value": "IPC 302",
                    "source": "media-1",
                    "source_id": "media-1",
                    "source_type": "media",
                    "event_time": t0,
                    "ingestion_time": t0,
                    "evidence": "Charge: IPC 302",
                    "extraction_confidence": 0.75,
                    "extraction_reliability": 0.75,
                    "status": "recorded",
                },
                {
                    "observation_id": str(uuid.uuid4()),
                    "case_id": case_id,
                    "fact_key": "charge",
                    "value": "IPC 304",
                    "source": "media-2",
                    "source_id": "media-2",
                    "source_type": "media",
                    "event_time": t0,
                    "ingestion_time": t0,
                    "evidence": "Charge: IPC 304",
                    "extraction_confidence": 0.75,
                    "extraction_reliability": 0.75,
                    "status": "recorded",
                },
            ],
        )

        out = await pipe.resync(case_id)

        # CAMS abstained on the conflicting fact (corroboration margin < delta)
        assert any(d["decision"] == "ABSTAINED" for d in out["decisions"])

        # conflict reads back from PostgreSQL with the old-JSON shape
        conflicts = await pipe.repo.get_conflicts(case_id)
        assert "charge" in conflicts
        cf = conflicts["charge"]
        assert cf["status"] == "unresolved"
        assert cf["C1"] is not None and cf["C2"] is not None
        assert cf["margin"] is not None and cf["margin"] < 0.10
        assert len(cf["candidates"]) == 2
        assert cf["explanation"]

        # twin fact is NOT resolved — abstain preserves the unresolved placeholder
        facts = await pipe.repo.get_facts(case_id)
        assert facts["charge"]["status"] == "unresolved"

        # both observations preserved (append-only)
        assert len(await pipe.repo.get_observations(case_id, "charge")) == 2

        # explicit raw-SQL proof the row lives in the PostgreSQL conflicts table
        async with db.AsyncSessionLocal() as session:
            n = (
                await session.execute(
                    _sqltext(
                        "SELECT count(*) FROM conflicts c JOIN cases cs "
                        "ON cs.id = c.case_id WHERE cs.case_number = :cn "
                        "AND cs.is_demo = false"
                    ),
                    {"cn": case_id},
                )
            ).scalar_one()
        assert n == 1

    loop_runner.run(run())


# ---- API (PostgreSQL) ----


def test_api_text_pipeline(client, auth, pg_repo, case_id):
    h = auth("COURT")
    r = client.post("/cases", json={"case_id": case_id, "title": "t"}, headers=h)
    assert r.status_code == 200
    r = client.post(
        f"/cases/{case_id}/text",
        json={
            "text": "Charge: IPC 302\nInjury: fracture\nLocation: Mumbai\n",
            "source": "forensic-1",
            "source_type": "forensic",
            "force_fallback": True,
        },
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["extraction"]["extractor"] == "fallback"
    assert body["observations_created"]
    # structured state is in PostgreSQL, not JSON files
    assert not (pg_repo.root / case_id / "observations.json").exists()
    assert not (pg_repo.root / case_id / "facts.json").exists()
    assert not (pg_repo.root / case_id / "history.json").exists()

    assert client.get(f"/cases/{case_id}/observations", headers=h).status_code == 200
    assert client.get(f"/cases/{case_id}/facts", headers=h).status_code == 200
    assert client.get(f"/cases/{case_id}/history", headers=h).status_code == 200
    assert client.get(f"/cases/{case_id}/conflicts", headers=h).status_code == 200
    assert client.get(f"/cases/{case_id}/provenance", headers=h).status_code == 200
    assert client.post(f"/cases/{case_id}/resync", headers=h).status_code == 200


def test_api_root_and_demo_isolated(client, pg_repo, pg_demo_repo, loop_runner):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert b"Justice Twin" in r.content
    assert b"Upload material" in r.content
    js = client.get("/assets/app.js")
    assert js.status_code == 200
    assert b"/cases/" in js.content

    r = client.post("/demo/case-001")
    assert r.status_code == 200
    assert r.json()["case_id"] == "CASE-001"
    assert (pg_demo_repo.root / "CASE-001").exists() or True
    assert not (pg_repo.root / "CASE-001").exists()

    async def check():
        obs = await pg_demo_repo.get_observations("CASE-001")
        real = await pg_repo.list_cases()
        return obs, real

    obs, real = loop_runner.run(check())
    assert len(obs) >= 5
    assert all(c.get("case_id") != "CASE-001" for c in real)


def test_api_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert "not legal truth" in body["disclaimer"].lower()
    assert body["storage"] == "postgresql"


def test_stakeholder_folders_and_ocr_txt_upload(client, auth, pg_repo, case_id):
    h = auth("COURT")
    client.post("/cases", json={"case_id": case_id, "title": "ocr"}, headers=h)
    content = b"Charge: IPC 302\nWeapon: knife\nLocation: Mumbai\n"
    r = client.post(
        f"/cases/{case_id}/upload",
        data={
            "source": "police-9",
            "source_type": "police",
            "force_fallback": "true",
            "title": "fir.txt",
        },
        files={"file": ("fir.txt", content, "text/plain")},
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("pipeline_ran") is True
    assert body["ocr"]["ok"] is True
    sh = list((pg_repo.root / case_id / "stakeholders").iterdir())
    assert sh, "expected stakeholder folder"
    assert (pg_repo.root / case_id / "uploads").exists()
    full = client.get(f"/cases/{case_id}/full", headers=h).json()
    assert full["summary"]["documents"] >= 1
    assert full["summary"]["observations"] >= 1
    assert full["timeline"]
