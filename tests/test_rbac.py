"""Task 3 RBAC tests: per-role authorization, access management, submissions.

Coverage: all 6 roles, cross-case denial, revoked access, ADMIN override,
grant/revoke + duplicate prevention, COURT auto-assignment, source-role
spoofing denial, FORENSIC/CITIZEN filtering, citizen PENDING → APPROVE → CAMS
and REJECT → no CAMS, and the immutability of observations/Twin/CAMS state.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

import pytest

import rbac

pytestmark = pytest.mark.usefixtures("require_postgres")

CITIZEN_KEYS = rbac.CITIZEN_FACT_KEYS
FORENSIC_KEYS = rbac.FORENSIC_FACT_KEYS

MIXED_TEXT = "Weapon: knife\nInjury: fracture\nCharge: IPC 302\nLocation: Mumbai\n"


# ---- helpers ----


def _create_case(client, auth, case_id: str, **extra: Any) -> Dict[str, Any]:
    r = client.post(
        "/cases", json={"case_id": case_id, "title": "rbac case", **extra}, headers=auth("COURT")
    )
    assert r.status_code == 200, r.text
    return r.json()


def _grant(client, auth, case_id: str, email: str, role: str):
    return client.post(
        f"/cases/{case_id}/access",
        json={"email": email, "case_role": role},
        headers=auth("COURT"),
    )


def _make_user(loop_runner, role: str) -> str:
    """Insert a fresh ACTIVE user with the dev password; returns the email."""
    from db import AsyncSessionLocal
    from db_models import SystemRole, User
    from security import hash_password

    email = f"{role.lower()}-{uuid.uuid4().hex[:8]}@nyayaos.dev"

    async def _do():
        async with AsyncSessionLocal() as session:
            session.add(
                User(
                    email=email,
                    password_hash=hash_password("NyayaOS-dev-2026!"),
                    system_role=SystemRole[role.upper()],
                    is_active=True,
                )
            )
            await session.commit()

    loop_runner.run(_do())
    return email


def _access_rows(client, headers, case_id: str) -> List[Dict[str, Any]]:
    r = client.get(f"/cases/{case_id}/access", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["access"]


def _review(client, headers, case_id: str, sid: str, decision: str, **extra: Any):
    return client.post(
        f"/cases/{case_id}/submissions/{sid}/review",
        json={"decision": decision, **extra},
        headers=headers,
    )


def _submit(client, headers, case_id: str, text: str, title: str = "citizen statement"):
    return client.post(
        f"/cases/{case_id}/submissions", json={"title": title, "text": text}, headers=headers
    )


# ---- authentication ----


def test_missing_or_invalid_token_is_401(client, case_id):
    assert client.get("/cases").status_code == 401
    assert client.post("/cases", json={"case_id": case_id}).status_code == 401
    assert client.get(f"/cases/{case_id}").status_code == 401
    assert client.post(f"/cases/{case_id}/text", json={"text": "Charge: IPC 302"}).status_code == 401
    for bad in ("not-a-jwt", "a.b.c", ""):
        headers = {"Authorization": f"Bearer {bad}"}
        assert client.get("/cases", headers=headers).status_code == 401
    assert client.get("/auth/me").status_code == 401


def test_missing_case_is_404_for_authorized_roles(client, auth, case_id):
    assert client.get(f"/cases/{case_id}", headers=auth("COURT")).status_code == 404
    assert client.get(f"/cases/{case_id}", headers=auth("ADMIN")).status_code == 404
    assert (
        client.post(f"/cases/{case_id}/text", json={"text": "x"}, headers=auth("COURT")).status_code
        == 404
    )


# ---- case creation + COURT auto-assignment ----


def test_court_creator_auto_assigned_and_creation_roles(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)

    rows = _access_rows(client, auth("COURT"), case_id)
    assert len(rows) == 1
    row = rows[0]
    assert row["email"] == seed_users["COURT"]
    assert row["case_role"] == "COURT"
    assert row["status"] == "ACTIVE"
    assert row["granted_by"] is not None

    # duplicate case_id → 409 (no silent takeover / re-grant)
    assert (
        client.post("/cases", json={"case_id": case_id}, headers=auth("COURT")).status_code == 409
    )

    # only ADMIN + COURT may create cases
    for role in ("POLICE", "LAWYER", "FORENSIC", "CITIZEN"):
        r = client.post(
            "/cases", json={"case_id": f"{role}-{uuid.uuid4().hex[:6]}"}, headers=auth(role)
        )
        assert r.status_code == 403, f"{role} should not create cases: {r.text}"

    # ADMIN-created case has no case_access rows — access is system-wide
    admin_case = f"T3-ADM-{uuid.uuid4().hex[:8].upper()}"
    r = client.post("/cases", json={"case_id": admin_case, "title": "admin case"}, headers=auth("ADMIN"))
    assert r.status_code == 200, r.text
    assert _access_rows(client, auth("ADMIN"), admin_case) == []
    assert client.get(f"/cases/{admin_case}", headers=auth("ADMIN")).status_code == 200


# ---- all six roles ----


def test_all_six_roles_view_assigned_case(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    for role in ("POLICE", "LAWYER", "FORENSIC", "CITIZEN"):
        assert _grant(client, auth, case_id, seed_users[role], role).status_code == 200, role

    for role in ("ADMIN", "COURT", "POLICE", "LAWYER", "FORENSIC", "CITIZEN"):
        headers = auth(role)
        r = client.get(f"/cases/{case_id}", headers=headers)
        assert r.status_code == 200, f"{role}: {r.text}"
        assert r.json()["case_id"] == case_id

        r = client.get("/cases", headers=headers)
        assert r.status_code == 200, role
        assert case_id in {c["case_id"] for c in r.json()}


def test_unassigned_role_denied_even_with_same_system_role(client, auth, case_id, loop_runner):
    """A COURT user who is NOT assigned to the case gets 403 — access is per case."""
    _create_case(client, auth, case_id)
    other_court = _make_user(loop_runner, "COURT")

    r = client.post("/auth/login", json={"email": other_court, "password": "NyayaOS-dev-2026!"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    assert client.get(f"/cases/{case_id}", headers=headers).status_code == 403
    assert client.get("/cases", headers=headers).json() == []


def test_cross_case_denial(client, auth, seed_users, case_id):
    case_a = case_id
    case_b = f"T3-B-{uuid.uuid4().hex[:8].upper()}"
    _create_case(client, auth, case_a)
    r = client.post("/cases", json={"case_id": case_b, "title": "other"}, headers=auth("ADMIN"))
    assert r.status_code == 200, r.text
    assert _grant(client, auth, case_a, seed_users["POLICE"], "POLICE").status_code == 200

    police = auth("POLICE")
    assert client.get(f"/cases/{case_a}", headers=police).status_code == 200
    for path in ("", "/full", "/observations", "/facts", "/documents"):
        assert client.get(f"/cases/{case_b}{path}", headers=police).status_code == 403, path
    assert (
        client.post(f"/cases/{case_b}/text", json={"text": "Charge: IPC 302"}, headers=police).status_code
        == 403
    )
    listed = {c["case_id"] for c in client.get("/cases", headers=police).json()}
    assert case_a in listed and case_b not in listed

    # the COURT creator of case A has no access to case B either
    assert client.get(f"/cases/{case_b}", headers=auth("COURT")).status_code == 403

    # ADMIN sees both without any case_access row
    admin_list = {c["case_id"] for c in client.get("/cases", headers=auth("ADMIN")).json()}
    assert {case_a, case_b} <= admin_list


# ---- access management ----


def test_grant_revoke_reactivate(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    assert _grant(client, auth, case_id, seed_users["LAWYER"], "LAWYER").status_code == 200
    lawyer = auth("LAWYER")
    assert client.get(f"/cases/{case_id}", headers=lawyer).status_code == 200

    rows = _access_rows(client, auth("COURT"), case_id)
    entry = next(r for r in rows if r["email"] == seed_users["LAWYER"])
    user_id = entry["user_id"]
    assert entry["case_role"] == "LAWYER" and entry["status"] == "ACTIVE"

    r = client.delete(f"/cases/{case_id}/access/{user_id}", headers=auth("COURT"))
    assert r.status_code == 200, r.text
    assert r.json()["access"]["status"] == "REVOKED"

    assert client.get(f"/cases/{case_id}", headers=lawyer).status_code == 403
    listed = {c["case_id"] for c in client.get("/cases", headers=lawyer).json()}
    assert case_id not in listed  # revoked case disappears from the listing
    # revoking again → 404 (no ACTIVE row)
    assert client.delete(f"/cases/{case_id}/access/{user_id}", headers=auth("COURT")).status_code == 404

    # re-grant reactivates the same single row
    assert _grant(client, auth, case_id, seed_users["LAWYER"], "LAWYER").status_code == 200
    assert client.get(f"/cases/{case_id}", headers=lawyer).status_code == 200
    rows = _access_rows(client, auth("COURT"), case_id)
    assert len([r for r in rows if r["email"] == seed_users["LAWYER"]]) == 1


def test_grant_validation_and_duplicates(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)

    assert _grant(client, auth, case_id, seed_users["POLICE"], "POLICE").status_code == 200
    # idempotent repeat → 200, still exactly one row
    assert _grant(client, auth, case_id, seed_users["POLICE"], "POLICE").status_code == 200
    rows = _access_rows(client, auth("COURT"), case_id)
    assert len([r for r in rows if r["email"] == seed_users["POLICE"]]) == 1

    # different ACTIVE role → 409 (revoke first)
    r = _grant(client, auth, case_id, seed_users["POLICE"], "LAWYER")
    assert r.status_code == 409, r.text

    # unknown user → 404; invalid case_role → 422; ADMIN is not assignable
    assert _grant(client, auth, case_id, "nobody@example.com", "POLICE").status_code == 404
    assert _grant(client, auth, case_id, seed_users["LAWYER"], "SUPERUSER").status_code == 422
    assert _grant(client, auth, case_id, seed_users["LAWYER"], "ADMIN").status_code == 422

    # ADMIN can also manage assignments (system-wide bypass)
    r = client.post(
        f"/cases/{case_id}/access",
        json={"email": seed_users["LAWYER"], "case_role": "LAWYER"},
        headers=auth("ADMIN"),
    )
    assert r.status_code == 200, r.text


def test_only_admin_and_assigned_court_manage_access_or_edit_metadata(
    client, auth, seed_users, case_id
):
    _create_case(client, auth, case_id)
    for role in ("POLICE", "LAWYER", "FORENSIC", "CITIZEN"):
        assert _grant(client, auth, case_id, seed_users[role], role).status_code == 200
        headers = auth(role)
        assert client.get(f"/cases/{case_id}/access", headers=headers).status_code == 403, role
        assert (
            client.post(
                f"/cases/{case_id}/access",
                json={"email": seed_users["POLICE"], "case_role": "POLICE"},
                headers=headers,
            ).status_code
            == 403
        ), role
        assert (
            client.patch(f"/cases/{case_id}", json={"title": "hacked"}, headers=headers).status_code
            == 403
        ), role

    # COURT (assigned) and ADMIN may edit metadata
    r = client.patch(f"/cases/{case_id}", json={"title": "renamed"}, headers=auth("COURT"))
    assert r.status_code == 200 and r.json()["title"] == "renamed"
    r = client.patch(f"/cases/{case_id}", json={"court_name": "High Court"}, headers=auth("ADMIN"))
    assert r.status_code == 200 and r.json()["court_name"] == "High Court"
    # empty patch → 422
    assert client.patch(f"/cases/{case_id}", json={}, headers=auth("COURT")).status_code == 422
    # malformed target user id on revoke → 404
    assert (
        client.delete(f"/cases/{case_id}/access/not-a-uuid", headers=auth("COURT")).status_code == 404
    )


# ---- ADMIN override ----


def test_admin_override_but_no_direct_cams_modification(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200
    admin = auth("ADMIN")

    # full read access without any case_access row
    for path in (
        "",
        "/full",
        "/stakeholders",
        "/observations",
        "/facts",
        "/history",
        "/conflicts",
        "/provenance",
        "/documents",
        "/access",
        "/submissions",
    ):
        assert client.get(f"/cases/{case_id}{path}", headers=admin).status_code == 200, path

    # but ADMIN cannot mutate Twin/observations/CAMS through public APIs
    assert (
        client.post(f"/cases/{case_id}/text", json={"text": "Charge: IPC 302"}, headers=admin).status_code
        == 403
    )
    assert (
        client.post(
            f"/cases/{case_id}/upload",
            data={"force_fallback": "true"},
            files={"file": ("x.txt", b"Charge: IPC 302", "text/plain")},
            headers=admin,
        ).status_code
        == 403
    )
    assert client.post(f"/cases/{case_id}/resync", headers=admin).status_code == 403
    assert _submit(client, admin, case_id, "Charge: IPC 302").status_code == 403

    sid = _submit(client, auth("CITIZEN"), case_id, "Charge: IPC 302").json()["submission"][
        "submission_id"
    ]
    assert _review(client, admin, case_id, sid, "APPROVE").status_code == 403


# ---- ingestion identity / spoofing ----


def test_source_identity_is_server_derived_not_client_supplied(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    for role in ("POLICE", "LAWYER", "FORENSIC"):
        assert _grant(client, auth, case_id, seed_users[role], role).status_code == 200
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200

    # POLICE claims to be court — the claim must be ignored
    r = client.post(
        f"/cases/{case_id}/text",
        json={
            "text": "Charge: IPC 302\n",
            "source": "court:chief-justice",
            "source_type": "court",
            "force_fallback": True,
        },
        headers=auth("POLICE"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["source_type"] == "police"
    assert body["document"]["source"] == f"police:{seed_users['POLICE']}"
    assert all(o["source_type"] == "police" for o in body["observations_created"])

    # FORENSIC uploads with a forged court source_type form field
    r = client.post(
        f"/cases/{case_id}/upload",
        data={"source": "court:chief", "source_type": "court", "force_fallback": "true"},
        files={"file": ("report.txt", b"Weapon: knife\n", "text/plain")},
        headers=auth("FORENSIC"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["document"]["source_type"] == "forensic"

    docs = client.get(f"/cases/{case_id}/documents", headers=auth("COURT")).json()["documents"]
    by_type = {d["source_type"] for d in docs}
    assert by_type == {"police", "forensic"}
    assert all(d["source"] != "court:chief" for d in docs)

    # CITIZEN cannot ingest at all, even with a court-looking body
    r = client.post(
        f"/cases/{case_id}/text",
        json={"text": "Charge: IPC 999\n", "source_type": "court"},
        headers=auth("CITIZEN"),
    )
    assert r.status_code == 403


def test_court_controls_citizen_visibility_flag(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    for role in ("POLICE", "CITIZEN"):
        assert _grant(client, auth, case_id, seed_users[role], role).status_code == 200

    # COURT sets CITIZEN_VISIBLE; POLICE asks for it but is overridden to INTERNAL
    r = client.post(
        f"/cases/{case_id}/text",
        json={"text": "Charge: IPC 302\n", "force_fallback": True, "visibility": "CITIZEN_VISIBLE"},
        headers=auth("COURT"),
    )
    assert r.status_code == 200 and r.json()["document"]["visibility"] == "CITIZEN_VISIBLE"
    r = client.post(
        f"/cases/{case_id}/text",
        json={"text": "Weapon: knife\n", "force_fallback": True, "visibility": "CITIZEN_VISIBLE"},
        headers=auth("POLICE"),
    )
    assert r.status_code == 200 and r.json()["document"]["visibility"] == "INTERNAL"

    court_docs = client.get(f"/cases/{case_id}/documents", headers=auth("COURT")).json()["documents"]
    assert len(court_docs) == 2

    citizen_docs = client.get(f"/cases/{case_id}/documents", headers=auth("CITIZEN")).json()[
        "documents"
    ]
    assert len(citizen_docs) == 1
    assert citizen_docs[0]["visibility"] == "CITIZEN_VISIBLE"


# ---- FORENSIC filtering ----


def test_forensic_scoped_facts_observations_and_documents(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    assert (
        client.post(
            f"/cases/{case_id}/text",
            json={"text": MIXED_TEXT, "force_fallback": True},
            headers=auth("COURT"),
        ).status_code
        == 200
    )
    assert _grant(client, auth, case_id, seed_users["FORENSIC"], "FORENSIC").status_code == 200
    forensic = auth("FORENSIC")

    facts = client.get(f"/cases/{case_id}/facts", headers=forensic).json()["facts"]
    assert {"weapon_type", "victim_injury"} <= set(facts)
    assert "charge" not in facts and "incident_location" not in facts
    assert set(facts) <= FORENSIC_KEYS

    # forensic uploads its own finding; the mutation response is filtered too
    r = client.post(
        f"/cases/{case_id}/text",
        json={"text": "Weapon: bat\n", "force_fallback": True},
        headers=forensic,
    )
    assert r.status_code == 200, r.text
    assert "charge" not in r.json()["facts"]
    assert set(r.json()["facts"]) <= FORENSIC_KEYS

    obs = client.get(f"/cases/{case_id}/observations", headers=forensic).json()["observations"]
    assert obs and all(o["source_type"] == "forensic" for o in obs)

    docs = client.get(f"/cases/{case_id}/documents", headers=forensic).json()["documents"]
    assert docs and all(d["source_type"] == "forensic" for d in docs)

    history = client.get(f"/cases/{case_id}/history", headers=forensic).json()["history"]
    assert history and all(h["fact_key"] in FORENSIC_KEYS for h in history)

    conflicts = client.get(f"/cases/{case_id}/conflicts", headers=forensic).json()["conflicts"]
    assert set(conflicts) <= FORENSIC_KEYS

    prov = client.get(f"/cases/{case_id}/provenance", headers=forensic).json()
    assert set(prov["provenance"]) <= FORENSIC_KEYS

    # FORENSIC may ingest but not resync; ADMIN/police-style roles keep resync
    assert client.post(f"/cases/{case_id}/resync", headers=forensic).status_code == 403

    # the court still sees everything, including the forensic observation
    all_obs = client.get(f"/cases/{case_id}/observations", headers=auth("COURT")).json()[
        "observations"
    ]
    assert any(o["source_type"] == "forensic" for o in all_obs)
    court_facts = client.get(f"/cases/{case_id}/facts", headers=auth("COURT")).json()["facts"]
    assert "charge" in court_facts


# ---- CITIZEN filtering ----


def test_citizen_scoped_view_and_denials(client, auth, seed_users, case_id, pg_repo, loop_runner):
    _create_case(client, auth, case_id, description="internal notes", court_name="High Court")
    assert (
        client.post(
            f"/cases/{case_id}/text",
            json={"text": "Charge: IPC 302\n", "force_fallback": True},
            headers=auth("COURT"),
        ).status_code
        == 200
    )

    async def plant_status():
        await pg_repo.set_fact(
            case_id, "case_status", {"value": "Trial", "status": "resolved", "confidence": 0.9}
        )

    loop_runner.run(plant_status())
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200
    citizen = auth("CITIZEN")

    r = client.get(f"/cases/{case_id}", headers=citizen)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "description" not in body and body["case_id"] == case_id
    assert body["observation_count"] == 0  # hidden even though observations exist
    assert "charge" not in body["facts"]

    facts = client.get(f"/cases/{case_id}/facts", headers=citizen).json()["facts"]
    assert "case_status" in facts
    assert "charge" not in facts
    assert set(facts) <= CITIZEN_KEYS

    # citizen is denied observations, CAMS history/conflicts/provenance, stakeholders
    for path in ("/observations", "/history", "/conflicts", "/provenance", "/stakeholders"):
        assert client.get(f"/cases/{case_id}{path}", headers=citizen).status_code == 403, path
    for path in ("/text", "/upload", "/resync"):
        assert client.post(f"/cases/{case_id}{path}", headers=citizen).status_code == 403, path

    full = client.get(f"/cases/{case_id}/full", headers=citizen)
    assert full.status_code == 200, full.text
    view = full.json()
    assert view["summary"]["observations"] == 0
    assert view["summary"]["history_events"] == 0
    assert view["twin"] and "charge" not in view["twin"]


# ---- citizen submissions ----


def test_submission_pending_then_approve_runs_extraction_and_cams(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200
    assert _grant(client, auth, case_id, seed_users["POLICE"], "POLICE").status_code == 200
    citizen = auth("CITIZEN")
    court = auth("COURT")

    r = _submit(client, citizen, case_id, "Charge: IPC 302\nWeapon: knife\n")
    assert r.status_code == 200, r.text
    sub = r.json()["submission"]
    assert sub["status"] == "PENDING"
    assert sub["reviewed_by"] is None and sub["document_id"] is None
    sid = sub["submission_id"]

    # PENDING is inert: no document, no observations, no Twin/history changes
    assert client.get(f"/cases/{case_id}/documents", headers=court).json()["documents"] == []
    assert client.get(f"/cases/{case_id}/observations", headers=court).json()["observations"] == []
    assert client.get(f"/cases/{case_id}/facts", headers=court).json()["facts"] == {}
    assert client.get(f"/cases/{case_id}/history", headers=court).json()["history"] == []

    own = client.get(f"/cases/{case_id}/submissions", headers=citizen).json()["submissions"]
    assert [s["submission_id"] for s in own] == [sid]

    # only assigned COURT may review (ADMIN explicitly may not)
    for role in ("POLICE", "CITIZEN", "ADMIN"):
        assert _review(client, auth(role), case_id, sid, "APPROVE").status_code == 403, role
    assert _review(client, auth("ADMIN"), case_id, sid, "REJECT").status_code == 403

    r = _review(client, court, case_id, sid, "APPROVE", note="verified", force_fallback=True)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["submission"]["status"] == "APPROVED"
    assert out["submission"]["reviewed_by_email"] == seed_users["COURT"]
    assert out["submission"]["reviewed_at"]
    assert out["submission"]["review_note"] == "verified"
    assert out["submission"]["document_id"]
    assert out["ingestion"]["decisions"]
    assert out["ingestion"]["facts"]["charge"]["status"] == "resolved"
    assert out["ingestion"]["facts"]["charge"]["value"] == "IPC 302"

    # approved submission became an official document + observations as CITIZEN source
    obs = client.get(f"/cases/{case_id}/observations", headers=court).json()["observations"]
    assert obs and all(o["source_type"] == "citizen" for o in obs)
    assert all(o["source"].startswith("citizen:") for o in obs)
    docs = client.get(f"/cases/{case_id}/documents", headers=court).json()["documents"]
    assert len(docs) == 1 and docs[0]["visibility"] == "INTERNAL"

    # the approved row cannot be reviewed twice
    assert _review(client, court, case_id, sid, "REJECT").status_code == 409


def test_submission_reject_changes_no_cams_state(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200
    citizen, court = auth("CITIZEN"), auth("COURT")

    sid = _submit(client, citizen, case_id, "Charge: IPC 999\n").json()["submission"][
        "submission_id"
    ]
    r = _review(client, court, case_id, sid, "REJECT", note="not verifiable")
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["submission"]["status"] == "REJECTED"
    assert out["submission"]["reviewed_by_email"] == seed_users["COURT"]
    assert out["submission"]["review_note"] == "not verifiable"
    assert out["submission"]["document_id"] is None
    assert out["ingestion"] is None

    assert client.get(f"/cases/{case_id}/documents", headers=court).json()["documents"] == []
    assert client.get(f"/cases/{case_id}/observations", headers=court).json()["observations"] == []
    assert client.get(f"/cases/{case_id}/facts", headers=court).json()["facts"] == {}
    assert client.get(f"/cases/{case_id}/history", headers=court).json()["history"] == []
    assert _review(client, court, case_id, sid, "APPROVE").status_code == 409


def test_citizen_sees_only_own_submissions(client, auth, seed_users, case_id, loop_runner):
    _create_case(client, auth, case_id)
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200
    other = _make_user(loop_runner, "CITIZEN")
    assert _grant(client, auth, case_id, other, "CITIZEN").status_code == 200
    r = client.post("/auth/login", json={"email": other, "password": "NyayaOS-dev-2026!"})
    other_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    mine = _submit(client, auth("CITIZEN"), case_id, "Charge: IPC 302\n").json()["submission"]
    theirs = _submit(client, other_headers, case_id, "Charge: IPC 304\n").json()["submission"]

    visible = client.get(f"/cases/{case_id}/submissions", headers=auth("CITIZEN")).json()[
        "submissions"
    ]
    assert [s["submission_id"] for s in visible] == [mine["submission_id"]]

    all_rows = client.get(f"/cases/{case_id}/submissions", headers=auth("COURT")).json()[
        "submissions"
    ]
    assert {s["submission_id"] for s in all_rows} == {
        mine["submission_id"],
        theirs["submission_id"],
    }


def test_submission_validation_and_missing_targets(client, auth, seed_users, case_id):
    _create_case(client, auth, case_id)
    assert _grant(client, auth, case_id, seed_users["CITIZEN"], "CITIZEN").status_code == 200
    citizen, court = auth("CITIZEN"), auth("COURT")

    assert _submit(client, citizen, case_id, "   ").status_code == 422
    assert _submit(client, citizen, case_id, "ok\n").status_code == 200

    assert _review(client, court, case_id, str(uuid.uuid4()), "APPROVE").status_code == 404
    assert _review(client, court, case_id, "not-a-uuid", "APPROVE").status_code == 404
    assert (
        client.post(
            "/cases",
            json={"case_id": f"T3-MISS-{uuid.uuid4().hex[:6]}"},
            headers=court,
        ).status_code
        == 200
    )
    missing = f"T3-MISS-{uuid.uuid4().hex[:6]}"
    assert _submit(client, citizen, missing, "Charge: IPC 302").status_code == 404


# ---- immutability of Twin/observation/CAMS state ----


def test_mutation_routes_are_exactly_the_reviewed_surface(client):
    """No public route may edit/delete observations, Twin facts, or CAMS history."""
    from starlette.routing import Route

    import main as main_mod

    actual = set()
    for route in main_mod.app.routes:
        if not isinstance(route, Route):
            continue
        for method in (route.methods or set()) & {"POST", "PUT", "PATCH", "DELETE"}:
            actual.add((method, route.path))

    expected = {
        ("POST", "/auth/login"),
        ("POST", "/cases"),
        ("PATCH", "/cases/{case_id}"),
        ("POST", "/cases/{case_id}/text"),
        ("POST", "/cases/{case_id}/upload"),
        ("POST", "/cases/{case_id}/resync"),
        ("POST", "/cases/{case_id}/access"),
        ("DELETE", "/cases/{case_id}/access/{user_id}"),
        ("POST", "/cases/{case_id}/submissions"),
        ("POST", "/cases/{case_id}/submissions/{submission_id}/review"),
        ("POST", "/demo/case-001"),
        ("POST", "/demo/scenario/{name}"),
        ("POST", "/api/reset-demo"),
        ("POST", "/users"),
        ("PATCH", "/users/{user_id}"),
    }
    assert actual == expected
