"""Tests for file persistence, Gemini parsing, CAMS pipeline, API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_repository import FileRepository
from gemini_extractor import fallback_extract, parse_gemini_response
from pipeline import Pipeline
import main as main_mod


@pytest.fixture
def tmp_repo(tmp_path: Path):
    return FileRepository(root=tmp_path / "cases")


@pytest.fixture
def tmp_demo_repo(tmp_path: Path):
    return FileRepository(root=tmp_path / "demo_cases")


@pytest.fixture
def pipe(tmp_repo):
    return Pipeline(repository=tmp_repo)


@pytest.fixture
def client(tmp_repo, tmp_demo_repo, monkeypatch):
    monkeypatch.setattr(main_mod, "repo", tmp_repo)
    monkeypatch.setattr(main_mod, "pipeline", Pipeline(repository=tmp_repo))
    monkeypatch.setattr(main_mod, "demo_repo", tmp_demo_repo)
    monkeypatch.setattr(main_mod, "demo_pipeline", Pipeline(repository=tmp_demo_repo))
    import pipeline as pipe_mod

    monkeypatch.setattr(pipe_mod, "pipeline", main_mod.pipeline)
    return TestClient(main_mod.app)


# ---- Gemini parsing / fallback ----


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


# ---- File persistence ----


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
    # New instance, same disk path
    r2 = FileRepository(root=root)
    assert r2.exists("P1")
    assert len(r2.get_observations("P1")) == 1
    assert (root / "P1" / "observations.json").exists()


def test_observations_never_deleted_on_conflict(pipe):
    pipe.create_case("C1")
    pipe.ingest_text(
        "C1",
        "Charge: IPC 302\n",
        source="court-1",
        source_type="court",
        force_fallback=True,
    )
    pipe.ingest_text(
        "C1",
        "Charge: IPC 304\n",
        source="media-1",
        source_type="media",
        force_fallback=True,
    )
    obs = pipe.repo.get_observations("C1", "charge")
    assert len(obs) >= 2
    values = {str(o["value"]) for o in obs}
    assert "IPC 302" in values
    assert "IPC 304" in values


def test_duplicate_observations_kept(pipe):
    pipe.create_case("DUP")
    pipe.ingest_text("DUP", "Weapon: knife\n", source="police-1", source_type="police", force_fallback=True)
    pipe.ingest_text("DUP", "Weapon: knife\n", source="police-1", source_type="police", force_fallback=True)
    assert len(pipe.repo.get_observations("DUP", "weapon_type")) == 2


def test_cams_accepts_and_updates_twin(pipe):
    pipe.create_case("TWIN")
    result = pipe.ingest_text(
        "TWIN",
        "Charge: IPC 302\nLocation: Mumbai\n",
        source="court-1",
        source_type="court",
        force_fallback=True,
    )
    facts = pipe.repo.get_facts("TWIN")
    assert "charge" in facts
    assert facts["charge"]["status"] == "resolved"
    assert facts["charge"]["value"] == "IPC 302"
    assert result["decisions"]
    assert any(d["decided"] for d in result["decisions"])


def test_abstention_does_not_overwrite(pipe):
    pipe.create_case("ABS")
    pipe.ingest_text(
        "ABS",
        "Charge: IPC 302\n",
        source="court-1",
        source_type="court",
        force_fallback=True,
    )
    before = pipe.repo.get_facts("ABS")["charge"]["value"]
    # Two weak media claims — often abstain on second conflicting equal pair;
    # inject via second court-level then conflicting equal media won't overwrite court.
    pipe.ingest_text(
        "ABS",
        "Charge: IPC 304\n",
        source="media-a",
        source_type="media",
        force_fallback=True,
    )
    after = pipe.repo.get_facts("ABS")["charge"]["value"]
    # Court value should remain (media loses or abstain keeps previous)
    assert after == before
    hist = pipe.repo.get_history("ABS")
    assert len(hist) >= 2


def test_history_and_provenance(pipe):
    pipe.create_case("PROV")
    pipe.ingest_text(
        "PROV",
        "Charge: IPC 302\nWeapon: knife\n",
        source="court-1",
        source_type="court",
        force_fallback=True,
    )
    hist = pipe.repo.get_history("PROV")
    assert hist
    assert "explanation" in hist[0]
    assert "C1" in hist[0]
    prov = pipe.provenance("PROV")
    assert "charge" in prov["provenance"]
    chain = prov["provenance"]["charge"]["trace"]
    assert chain
    assert chain[0].get("original_text")


def test_resync(pipe):
    pipe.create_case("RS")
    pipe.ingest_text("RS", "Location: Mumbai\n", source="police-1", source_type="police", force_fallback=True)
    out = pipe.resync("RS")
    assert out["facts"]


# ---- API ----


def test_api_text_pipeline(client, tmp_repo):
    r = client.post("/cases", json={"case_id": "API1", "title": "t"})
    assert r.status_code == 200
    r = client.post(
        "/cases/API1/text",
        json={
            "text": "Charge: IPC 302\nInjury: fracture\nLocation: Mumbai\n",
            "source": "forensic-1",
            "source_type": "forensic",
            "force_fallback": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["extraction"]["extractor"] == "fallback"
    assert body["observations_created"]
    assert (tmp_repo.root / "API1" / "observations.json").exists()
    assert (tmp_repo.root / "API1" / "facts.json").exists()
    assert (tmp_repo.root / "API1" / "history.json").exists()

    assert client.get("/cases/API1/observations").status_code == 200
    assert client.get("/cases/API1/facts").status_code == 200
    assert client.get("/cases/API1/history").status_code == 200
    assert client.get("/cases/API1/conflicts").status_code == 200
    assert client.get("/cases/API1/provenance").status_code == 200
    assert client.post("/cases/API1/resync").status_code == 200


def test_api_root_and_demo_isolated(client, tmp_repo, tmp_demo_repo):
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
    # Demo data must land in demo_cases root, not real cases root
    assert (tmp_demo_repo.root / "CASE-001" / "observations.json").exists()
    assert not (tmp_repo.root / "CASE-001").exists()
    obs = tmp_demo_repo.get_observations("CASE-001")
    assert len(obs) >= 5


def test_api_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "not legal truth" in r.json()["disclaimer"].lower()


def test_stakeholder_folders_and_ocr_txt_upload(client, tmp_repo, tmp_path):
    client.post("/cases", json={"case_id": "OCR1", "title": "ocr"})
    # plain text "PDF-like" upload via .txt
    content = b"Charge: IPC 302\nWeapon: knife\nLocation: Mumbai\n"
    r = client.post(
        "/cases/OCR1/upload",
        data={
            "source": "police-9",
            "source_type": "police",
            "force_fallback": "true",
            "title": "fir.txt",
        },
        files={"file": ("fir.txt", content, "text/plain")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("pipeline_ran") is True
    assert body["ocr"]["ok"] is True
    # stakeholder folder on disk
    sh = list((tmp_repo.root / "OCR1" / "stakeholders").iterdir())
    assert sh, "expected stakeholder folder"
    assert (tmp_repo.root / "OCR1" / "uploads").exists()
    full = client.get("/cases/OCR1/full").json()
    assert full["summary"]["documents"] >= 1
    assert full["summary"]["observations"] >= 1
    assert full["timeline"]


def test_continuous_case_keeps_prior_data(pipe):
    pipe.create_case("FLOW")
    pipe.ingest_text("FLOW", "Charge: IPC 302\n", source="court-1", source_type="court", force_fallback=True)
    pipe.ingest_text("FLOW", "Weapon: knife\n", source="police-1", source_type="police", force_fallback=True)
    view = pipe.full_case_view("FLOW")
    assert view["summary"]["documents"] == 2
    assert view["summary"]["observations"] >= 2
    assert len(view["timeline"]) >= 2
