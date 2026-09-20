"""Public/demo route policy, JSON-free runtime persistence, frontend auth contract."""

from __future__ import annotations

PUBLIC_GET = ("/api/health", "/api/config", "/api/evaluation")
PROTECTED_GET = ("/cases", "/users", "/auth/me")


def test_public_endpoints_stay_public(client):
    assert client.get("/").status_code == 200
    for path in PUBLIC_GET:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"


def test_protected_endpoints_require_token(client):
    for path in PROTECTED_GET:
        r = client.get(path)
        assert r.status_code == 401, f"{path} -> {r.status_code}"


def test_demo_reset_cannot_touch_real_cases(client, auth, pg_repo, pg_demo_repo, case_id, loop_runner):
    h = auth("COURT")
    assert client.post("/cases", json={"case_id": case_id, "title": "real"}, headers=h).status_code == 200
    assert client.post("/demo/case-001").status_code == 200

    async def check():
        return await pg_demo_repo.exists("CASE-001"), await pg_repo.exists(case_id)

    demo_before, real_before = loop_runner.run(check())
    assert demo_before is True
    assert real_before is True

    assert client.post("/api/reset-demo").status_code == 200

    demo_after, real_after = loop_runner.run(check())
    assert demo_after is False, "reset-demo must clear the demo scope"
    assert real_after is True, "reset-demo must not touch real cases"

    assert client.get(f"/cases/{case_id}", headers=h).status_code == 200
    assert client.get("/cases/CASE-001", headers=h).status_code == 404


def test_demo_routes_never_write_to_real_scope(client, pg_repo, loop_runner):
    assert client.post("/demo/scenario/noisy").status_code == 200

    async def real_case_ids():
        return [c["case_id"] for c in await pg_repo.list_cases()]

    assert "CASE-001" not in loop_runner.run(real_case_ids())


def test_no_json_runtime_persistence(client, auth, pg_repo, case_id):
    h = auth("COURT")
    assert client.post("/cases", json={"case_id": case_id, "title": "json-free"}, headers=h).status_code == 200
    r = client.post(
        f"/cases/{case_id}/upload",
        data={"source": "police-7", "source_type": "police", "force_fallback": "true", "title": "fir.txt"},
        files={"file": ("fir.txt", b"Charge: IPC 302\nLocation: Pune\n", "text/plain")},
        headers=h,
    )
    assert r.status_code == 200, r.text

    assert client.post(f"/cases/{case_id}/text", headers=h, json={"text": "Weapon: knife"}).status_code == 200

    stray = [p for p in pg_repo.root.rglob("*.json")]
    assert stray == [], f"runtime persistence wrote JSON: {stray}"

    uploads = list((pg_repo.root / case_id / "uploads").iterdir())
    assert uploads, "uploaded physical file must be preserved on disk"
    assert any(p.suffix == ".txt" for p in uploads)


def test_runtime_modules_do_not_import_file_repository():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    runtime = [
        "main.py",
        "db_repository.py",
        "pipeline.py",
        "auth.py",
        "security.py",
        "users_api.py",
        "rbac.py",
        "paths.py",
        "ocr.py",
        "cams.py",
    ]
    offenders = []
    for name in runtime:
        path = root / name
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                offenders += [
                    f"{name}: import {a.name}"
                    for a in node.names
                    if a.name.split(".")[0] == "file_repository"
                ]
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod == "file_repository":
                    offenders.append(f"{name}: from {node.module} import ...")
    assert offenders == [], f"runtime modules still import file_repository: {offenders}"


def test_frontend_shell_has_authenticated_login_contract(client):
    html = client.get("/").text
    assert "loginOverlay" in html
    assert "loginForm" in html

    js = client.get("/assets/app.js").text
    for needle in ("/auth/login", "/auth/me", "Authorization", "Bearer", "localStorage"):
        assert needle in js, f"frontend missing {needle!r}"
    assert "logout" in js.lower()
