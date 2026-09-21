# NyayaOS Tasks 1–4 — Complete Execution & Manual Testing Guide

Branch: `khushi-test` · Platform: Windows + PowerShell · Stack: Docker Compose (isolated)

This guide lets you execute and verify **everything** implemented in Tasks 1–4 from a fresh
PowerShell with nothing running. Every command, port, payload, credential, and expected
result is given explicitly — you never need to open source code.

> **Numbers in Part A11 are real captured outputs** from a live run of this exact stack
> (2026-09-21), recomputed against the implementation formula. Nothing is fabricated.

---

## 0. Environment facts (memorize this table)

| Item | Value |
|---|---|
| Compose project | `nyayaos-task14` |
| Containers | `nyayaos-task14-api-1`, `nyayaos-task14-db-1` |
| API base URL | `http://127.0.0.1:8002` |
| Web UI | `http://127.0.0.1:8002/` |
| Postgres (from host) | `localhost:5433` |
| Postgres (inside compose network) | `db:5432` |
| Database name | `nyayaos_rbac` |
| DB user / password | `nyayaos` / `nyayaos` |
| DB volume | `nyayaos-task14_task14_pgdata` |
| Migration head | `t3rbac0003` |
| CAMS constants | wA=0.3, wT=0.3, wX=0.2, wE=0.2, τ=0.55, δ=0.10 |
| Extraction mode | deterministic fallback (E=0.75) — `GEMINI_API_KEY` is intentionally blank |

**Seed accounts** (created automatically on API startup; dev-only password):

| Email | System role | Password |
|---|---|---|
| `admin@nyayaos.dev` | ADMIN | `NyayaOS-dev-2026!` |
| `court@nyayaos.dev` | COURT | `NyayaOS-dev-2026!` |
| `police@nyayaos.dev` | POLICE | `NyayaOS-dev-2026!` |
| `lawyer@nyayaos.dev` | LAWYER | `NyayaOS-dev-2026!` |
| `forensic@nyayaos.dev` | FORENSIC | `NyayaOS-dev-2026!` |
| `citizen@nyayaos.dev` | CITIZEN | `NyayaOS-dev-2026!` |

### 0.1 Safety rules (non-negotiable)

1. **The legacy `nyayaos` database belongs to another branch.** This stack never references
   it. `cleanup.py` hard-refuses any database whose name does not end in `_rbac`. Never run
   `DROP DATABASE nyayaos` or point `DATABASE_URL` at it.
2. `docker compose down -v` **destroys the Postgres volume** (all cases/users). Use plain
   `docker compose stop` to pause; `down` (no `-v`) to remove containers but keep data.
3. Do not commit `.env` (it is gitignored). Do not paste your real `JWT_SECRET_KEY` into
   any document, issue, or chat.
4. All manual test cases in this guide use case IDs starting with **`T14-`** so
   `cleanup.py` can remove them afterwards.

### 0.2 PowerShell conventions used below

- HTTP calls use **`curl.exe`** (the `.exe` suffix is required — plain `curl` in PowerShell
  is an alias for `Invoke-WebRequest` with different flags).
- JSON bodies are single-quoted PowerShell strings: `'{"email":"..."}'`.
- `| ConvertFrom-Json` parses responses; `| ConvertTo-Json -Depth 10` pretty-prints.
- Docker commands are identical in PowerShell and Git Bash. `docker compose exec -T`
  (capital T) disables TTY allocation so output pipes cleanly.

---

# PART A — HOW TO EXECUTE THE COMPLETE NYAYAOS SYSTEM

## A1. Initial setup (fresh PowerShell, nothing running)

### A1.1 Open PowerShell at the repo root

```powershell
cd C:\Users\HP\Projects\MajorProject
```

### A1.2 Verify the branch and working tree

```powershell
git branch --show-current
git status --short
```

Expected: `khushi-test`. Untracked files are fine (`Dockerfile`, `docker-compose.yml`,
`.dockerignore`, `cleanup.py`, this guide). If you see unexpected **modified** tracked
files, stop and investigate before continuing.

### A1.3 Verify Docker Desktop is running

```powershell
docker version --format '{{.Server.Version}}'
docker compose version
```

Expected: a server version string (e.g. `27.x`) and `Docker Compose version v2.x`.
If `docker version` errors with "engine not running", start Docker Desktop and wait for
the whale icon to go steady.

### A1.4 Verify/prepare `.env`

```powershell
Test-Path .env
```

If `False`, create it:

```powershell
Copy-Item .env.example .env
```

`.env` must contain (values shown are safe to use verbatim **except** the JWT secret):

```
DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac
JWT_SECRET_KEY=<generate below — at least 32 bytes>
JWT_EXPIRE_MINUTES=60
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
DEV_SEED_PASSWORD=NyayaOS-dev-2026!
```

Generate a cryptographically secure 32-byte hex secret (works in PowerShell 5.1 and 7):

```powershell
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$b = New-Object byte[] 32
$rng.GetBytes($b)
$secret = -join ($b | ForEach-Object { '{0:x2}' -f $_ })
$secret   # copy this value into .env as JWT_SECRET_KEY=...
```

Rules: the secret must be ≥ 32 bytes (64 hex chars), unique per environment, and never
committed or printed in shared documents. `GEMINI_API_KEY` stays **blank** — that forces
the deterministic rule-based extractor (reliability E = 0.75), which is what makes the
CAMS numbers in A11 reproducible.

> Note: `docker-compose.yml` **pins** `DATABASE_URL` in the api service's `environment:`
> block, which overrides both `env_file` and `load_dotenv()`. Even a stale `.env` cannot
> point the containers at the wrong database. The compose file never mentions `nyayaos`.

### A1.5 Check that ports 8002 and 5433 are free

```powershell
Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 5433 -State Listen -ErrorAction SilentlyContinue
```

Expected: **no output** for both. If something is listening, stop it (or `docker compose
down` a stale nyayaos-task14 stack) before continuing.

## A2. Database initialization

### A2.1 Build and start the stack (first time: several minutes)

```powershell
docker compose up -d --build
```

Expected tail of output: `Container nyayaos-task14-db-1 Healthy`,
`Container nyayaos-task14-api-1 Started`.

The api container's command is `alembic upgrade head && uvicorn ...` — **migrations run
automatically before the server starts** (the API seeds users at startup and needs tables).

### A2.2 Watch the startup logs

```powershell
docker compose logs api --tail 40
```

Expected, in order:
- three `Running upgrade ... -> t1pg0001 / t2auth0002 / t3rbac0003` lines (first boot only)
- `INFO:     Uvicorn running on http://0.0.0.0:8000`
- `INFO:     Application startup complete.`

### A2.3 Verify container health

```powershell
docker compose ps
```

Expected: both containers `Up ... (healthy)`. Health can take ~30 s after first boot;
re-run until both say healthy.

### A2.4 Verify the database, migrations, and tables

```powershell
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT current_database();"
docker compose exec -T api alembic current
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "\dt"
```

Expected: `nyayaos_rbac`; `t3rbac0003 (head)`; tables including `users`, `cases`,
`case_access`, `documents`, `observations`, `facts`, `history`, `conflicts`,
`submissions`, `stakeholders`, `alembic_version`.

Migration history:

```powershell
docker compose exec -T api alembic history
```

### A2.5 Verify seed users

```powershell
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT email, system_role, is_active FROM users ORDER BY email;"
```

Expected: exactly the six `@nyayaos.dev` accounts, all `is_active = true`. Seeding is
idempotent — restarting the API never duplicates them.

## A3. Clean demo environment (SAFE cleanup)

`cleanup.py` (run **inside the api container**) removes disposable data and nothing else.

**What it deletes** (three buckets):
1. **Demo scope** — every `is_demo = true` case row and everything under `data/demo_cases/`.
2. **Disposable real cases** — real cases whose ID starts with `T2-`, `T3-`, `T14-`,
   `CLI-`, `VERIFY-`, `A11-`, `MANUAL-` (extend with `--prefix`), their DB rows **and**
   their `data/cases/<ID>/` directories, plus same-prefix orphan directories with no DB row.
3. **Non-seed users** — every user except the six seed accounts (skip with `--keep-users`).

**What it never touches:** schema, tables, `alembic_version`, the six seed users, real
cases outside the disposable prefixes, and any database not named `*_rbac` (hard guard:
it runs `SELECT current_database()` and aborts otherwise — the legacy `nyayaos` database
can never be targeted).

### A3.1 Dry run (always do this first — deletes nothing)

```powershell
docker compose exec -T api python cleanup.py
```

Expected output shape (real capture):

```
[DRY RUN] database: nyayaos_rbac
[DRY RUN] disposable case prefixes: T2-, T3-, T14-, CLI-, VERIFY-, A11-, MANUAL-
[DRY RUN] demo scope: 0 demo case(s)
[DRY RUN] disposable real cases: 1 -> T14-CAMS-1
[DRY RUN] same-prefix orphan dirs without a DB row: 1 -> T2-9E5964BFFE
[DRY RUN] non-seed users: 0
[DRY RUN] always preserved: schema, alembic_version, seed users [...]
Nothing was deleted. Re-run with --apply to execute.
```

**Read the plan carefully.** It lists every exact case ID, directory, and email it would
delete. If anything listed is not disposable, stop.

### A3.2 Apply

```powershell
docker compose exec -T api python cleanup.py --apply
```

Then verify:

```powershell
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT case_number FROM cases;"
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT email FROM users ORDER BY email;"
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT version_num FROM alembic_version;"
```

Expected: only the disposable cases gone; six seed users still present; `t3rbac0003`.

Useful variants: `--demo-only` (wipe demo scope only), `--keep-users` (keep non-seed
users), `--prefix MYTEST` (extra prefix, repeatable; auto-uppercased, `-` appended).

## A4. Start, verify, stop the application

### A4.1 Start (after first build)

```powershell
docker compose up -d
docker compose ps        # wait for both (healthy)
```

### A4.2 Health endpoint (no auth, no DB query)

```powershell
curl.exe -s http://127.0.0.1:8002/api/health | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

Expected (real capture):

```json
{
  "service": "nyayaos-lite",
  "pipeline": "text → Gemini/fallback → PostgreSQL → CAMS → Digital Twin",
  "storage": "postgresql",
  "weights": { "wA": 0.3, "wT": 0.3, "wX": 0.2, "wE": 0.2 },
  "tau": 0.55,
  "delta": 0.1,
  "real_cases_root": "/app/data/cases",
  "demo_cases_root": "/app/data/demo_cases",
  "disclaimer": "CAMS confidence is not legal truth. Evaluation data is synthetic."
}
```

If `weights/tau/delta` differ from 0.3/0.3/0.2/0.2/0.55/0.1, **stop** — someone edited
`config.py`; the A11 expectations assume these constants.

### A4.3 Prove the backend is connected to the intended database

```powershell
docker compose exec -T api python -c "import asyncio, db; from sqlalchemy import text;`nasync def m():`n    async with db.AsyncSessionLocal() as s: print((await s.execute(text('SELECT current_database()'))).scalar_one())`nasyncio.run(m())"
```

Expected: `nyayaos_rbac`. (If the backtick-n multiline form is awkward, this also works:)

```powershell
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT count(*) FROM users;"
```

### A4.4 Web UI

Open `http://127.0.0.1:8002/` in a browser. Expected: the NyayaOS sign-in overlay
("NyayaOS — sign in") with email/password fields and a hint naming the dev accounts.

### A4.5 Stop / restart

```powershell
docker compose stop          # pause, keep everything
docker compose start         # resume
docker compose down          # remove containers, KEEP the data volume
docker compose down -v       # DESTRUCTIVE: also deletes the nyayaos_rbac volume
```

Data persistence proof: create a case (A5), `docker compose stop && docker compose start`,
then confirm the case still exists — Postgres data lives in the named volume, not the
container.

---

## A5. Task 1 features — PostgreSQL persistence + JWT authentication

### A5.1 Login (POST /auth/login)

```powershell
$login = curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"court@nyayaos.dev","password":"NyayaOS-dev-2026!"}' | ConvertFrom-Json
$COURT = $login.access_token
$COURT.Length    # expect ~255 (HS256 JWT)
```

Response fields: `access_token` (JWT), `token_type` = `bearer`. **The response never
contains a password or password hash** — verify visually.

### A5.2 Who am I (GET /auth/me)

```powershell
curl.exe -s http://127.0.0.1:8002/auth/me -H "Authorization: Bearer $COURT" | ConvertFrom-Json
```

Expected: `email = court@nyayaos.dev`, `system_role = COURT`, `is_active = true`,
an `id` UUID. No password fields.

### A5.3 Failure modes

```powershell
# wrong password -> 401
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"court@nyayaos.dev","password":"wrong"}'
# missing token -> 401 on a protected route
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases
# garbage token -> 401
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases -H "Authorization: Bearer not.a.jwt"
```

Expected: `401`, `401`, `401`.

### A5.4 Persistence proof

Create a case, restart the stack, confirm it survives:

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"case_id":"T14-PERSIST","title":"persistence check"}' | ConvertFrom-Json
docker compose stop; docker compose start
# re-login (tokens survive restarts too — same JWT_SECRET_KEY), then:
curl.exe -s http://127.0.0.1:8002/cases -H "Authorization: Bearer $COURT" | ConvertFrom-Json
```

Expected: `T14-PERSIST` still listed. Also confirm on disk:

```powershell
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT case_number FROM cases;"
```

### A5.5 Token expiry

`JWT_EXPIRE_MINUTES=60`. Live-observed: tokens minted at 04:22 were rejected at 05:40
with `401 {"detail":"Not authenticated"}` — expiry is enforced without leaking whether
the token was expired vs. malformed. To see it on demand, temporarily set
`JWT_EXPIRE_MINUTES=1` in `.env`, run `docker compose up -d` (recreates api), login, wait
61 s, call `/auth/me` → expect 401. Re-login mints a fresh token. Restore `60` afterwards
and recreate the api container.

## A6. Task 2 features — complete API surface

**Auth**: every call below needs `-H "Authorization: Bearer $TOKEN"` unless marked public.
Get tokens like A5.1 (substitute the email):

```powershell
$ADMIN    = (curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"admin@nyayaos.dev","password":"NyayaOS-dev-2026!"}'    | ConvertFrom-Json).access_token
$COURT    = (curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"court@nyayaos.dev","password":"NyayaOS-dev-2026!"}'    | ConvertFrom-Json).access_token
$POLICE   = (curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"police@nyayaos.dev","password":"NyayaOS-dev-2026!"}'   | ConvertFrom-Json).access_token
$LAWYER   = (curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"lawyer@nyayaos.dev","password":"NyayaOS-dev-2026!"}'   | ConvertFrom-Json).access_token
$FORENSIC = (curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"forensic@nyayaos.dev","password":"NyayaOS-dev-2026!"}' | ConvertFrom-Json).access_token
$CITIZEN  = (curl.exe -s -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"citizen@nyayaos.dev","password":"NyayaOS-dev-2026!"}'  | ConvertFrom-Json).access_token
```

### Endpoint reference (Task 2 + Task 3 surface)

| # | Method & path | Min. case role | Payload | Success | Key response fields |
|---|---|---|---|---|---|
| 1 | `POST /auth/login` | public | `{"email","password"}` | 200 | `access_token`, `token_type` |
| 2 | `GET /auth/me` | any logged-in | — | 200 | `id`, `email`, `system_role`, `is_active`, `created_at` |
| 3 | `POST /cases` | COURT or ADMIN (system) | `{"case_id"?,"title"?,"description"?}` | 200 | full case object; creator auto-assigned COURT |
| 4 | `GET /cases` | any logged-in | — | 200 | only cases you have ACTIVE access to |
| 5 | `GET /cases/{id}` | any case member | — | 200 | case metadata |
| 6 | `PATCH /cases/{id}` | COURT / ADMIN | `{"title"?,"description"?,"case_type"?,"case_status"?,"filing_date"?,"court_name"?,"next_hearing_date"?}` | 200 | updated case |
| 7 | `POST /cases/{id}/text` | COURT/POLICE/LAWYER/FORENSIC | `{"text","title"?,"force_fallback"?,"visibility"?}` | 200 | `document`, `extraction`, `observations_created`, `decisions`, `facts`, `conflicts`, `case_view` |
| 8 | `POST /cases/{id}/upload` | same as 7 | multipart: `file` + optional `force_fallback`,`visibility` | 200 | same as 7 (+ `ocr`) |
| 9 | `GET /cases/{id}/full` | any case member | — | 200 | whole twin: facts/conflicts/documents/observations/history/stakeholders/timeline |
| 10 | `GET /cases/{id}/facts` | any case member | — | 200 | twin facts (role-whitelisted) |
| 11 | `GET /cases/{id}/history` | any case member | — | 200 | CAMS decision log |
| 12 | `GET /cases/{id}/conflicts` | any case member | — | 200 | unresolved facts |
| 13 | `GET /cases/{id}/provenance` | any case member | — | 200 | per-fact evidence chains |
| 14 | `GET /cases/{id}/observations` | COURT/POLICE/LAWYER/FORENSIC (not CITIZEN) | — | 200 | raw observations |
| 15 | `GET /cases/{id}/documents` | any case member | — | 200 | documents (INTERNAL hidden from CITIZEN) |
| 16 | `GET /cases/{id}/stakeholders` | any case member | — | 200 | source registry |
| 17 | `POST /cases/{id}/resync` | COURT | `{}` | 200 | fresh decisions for all facts |
| 18 | `POST /cases/{id}/access` | COURT (case) / ADMIN | `{"email","case_role"}` | 200 | granted access row |
| 19 | `GET /cases/{id}/access` | COURT / ADMIN | — | 200 | access list |
| 20 | `DELETE /cases/{id}/access/{user_id}` | COURT / ADMIN | — | 200 | revoked row (status REVOKED) |
| 21 | `POST /cases/{id}/submissions` | CITIZEN (case member) | `{"text","title"?}` | 200 | `submission_id`, `status=PENDING`, `reviewed_by/reviewed_at/review_note/document_id` null |
| 22 | `GET /cases/{id}/submissions` | COURT/ADMIN: all; CITIZEN: own | — | 200 | submission list |
| 23 | `POST /cases/{id}/submissions/{sid}/review` | COURT | `{"decision":"APPROVE"\|"REJECT","note"?}` | 200 | review result; APPROVE runs the CAMS pipeline |
| 24 | `GET /users` | ADMIN (system) | — | 200 | all users (no password fields) |
| 25 | `POST /users` | ADMIN (system) | `{"email","password","system_role"}` | 201 | `{"user": {id, email, system_role, is_active, created_at}}` |
| 26 | `PATCH /users/{user_id}` | ADMIN (system) | `{"is_active"?,"password"?}` | 200 | updated user |
| 27 | `GET /api/health` | public | — | 200 | see A4.2 |
| 28 | `GET /api/config` | public | — | 200 | weights/tau/delta |
| 29 | `GET /api/evaluation` | public | — | 200 | paper results markdown |
| 30 | `POST /api/reset-demo` | public | — | 200 | demo scope wiped |
| 31 | `POST /demo/case-001` | public | — | 200 | seeds demo case |
| 32 | `POST /demo/scenario/{name}` | public | — | 200 | runs a named demo scenario |

`{id}` is the case_number (e.g. `T14-PERSIST`). Roles in the table are **case roles**
(per-case assignment) unless marked "system".

### A6.1 Walkthrough — create, ingest, inspect

```powershell
# 1) create case (COURT)
curl.exe -s -X POST http://127.0.0.1:8002/cases -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"case_id":"T14-API-1","title":"API walkthrough"}' | ConvertFrom-Json

# 2) ingest text as COURT (identity is derived server-side — you cannot spoof source)
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-API-1/text -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 302","force_fallback":true,"title":"charge sheet"}' | ConvertFrom-Json -Depth 10

# 3) inspect
curl.exe -s http://127.0.0.1:8002/cases/T14-API-1/facts      -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 10
curl.exe -s http://127.0.0.1:8002/cases/T14-API-1/history    -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 10
curl.exe -s http://127.0.0.1:8002/cases/T14-API-1/conflicts  -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 10
curl.exe -s http://127.0.0.1:8002/cases/T14-API-1/provenance -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 10
curl.exe -s http://127.0.0.1:8002/cases/T14-API-1/full       -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 10
```

In the ingest response verify:
- `document.source_id` = `court:court@nyayaos.dev`, `source_type` = `court` (derived from
  YOUR identity, not the request body — sending `"source":"media"` in the payload is ignored)
- `document.extractor` = `fallback`, note mentions `GEMINI_API_KEY not configured`
- `extraction.facts[0]`: `fact_key=charge`, `value=IPC 302`, `extraction_confidence=0.75`
- `decisions[0]`: `decision=ACCEPTED`, `C1=0.944`, `selected_value=IPC 302`
- `facts.charge.status = resolved`

### A6.2 File upload (multipart)

Create a test file, then upload as POLICE (after granting police access — A7.2):

```powershell
Set-Content -Path $env:TEMP\t14-upload.txt -Value "Weapon: knife`nLocation: Mumbai"
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-API-1/upload -H "Authorization: Bearer $POLICE" -F "file=@$env:TEMP\t14-upload.txt" -F "force_fallback=true" | ConvertFrom-Json -Depth 10
```

Expected: same structure as text ingest; `document.ocr` populated for text extraction;
`source_type=police`. PDFs and images also work (images go through Tesseract OCR inside
the container).

### A6.3 Resync (COURT only)

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-API-1/resync -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{}' | ConvertFrom-Json -Depth 10
```

Expected: 200 with fresh `decisions` for every fact (same values if no new observations).
As POLICE: expect **403**.

## A7. Task 3 — case-specific RBAC, all six roles

### A7.1 Permission matrix (case roles)

| Capability | COURT | POLICE | LAWYER | FORENSIC | CITIZEN | ADMIN (system) |
|---|---|---|---|---|---|---|
| Create case | yes | no | no | no | no | yes |
| List cases (`GET /cases`) | assigned only | assigned only | assigned only | assigned only | assigned only | **ALL cases, no access row needed** |
| View case metadata | yes | yes | yes | yes | yes (if assigned) | **yes, any case** |
| Edit case metadata (PATCH) | yes | no | no | no | no | **yes, any case** |
| Ingest text/upload | yes | yes | yes | yes | no | **no (403)** |
| View facts (whitelisted) | all | all | all | **whitelist** | **whitelist** | **all, any case** |
| View raw observations | yes | yes | yes | yes | **no (403)** | **yes, any case** |
| View INTERNAL documents | yes | yes | yes | yes | **no** | **yes, any case** |
| View history/conflicts/provenance | yes | yes | yes | whitelist | whitelist | **yes, any case** |
| Resync | yes | no | no | no | no | **no (403)** |
| Manage case access | yes (assigned cases) | no | no | no | no | **yes, any case** |
| Submit citizen statement | no | no | no | no | yes | **no (403)** |
| Review submissions | yes | no | no | no | no | **no (403)** |

ADMIN is a **system-wide bypass for reads and administration only** — it never needs a
`case_access` row, but it can never perform legal/CAMS mutations (ingest, upload, resync,
submit, review all return 403). Live-verified: with zero access rows on a case, ADMIN got
200 on `GET /cases/{id}`, `/full`, `/observations`, `/facts`, `/history`, `/documents`,
`/access`, `/submissions`, and on `GET /cases` the case appeared in ADMIN's list;
`POST /text` and `POST /resync` returned 403; `PATCH` metadata and `POST /access` (grant)
returned 200. Proven by `tests/test_rbac.py::test_admin_override_but_no_direct_cams_modification`.

Fact whitelists:
- **FORENSIC** sees only: `weapon_type`, `victim_injury`, `cause_of_injury`,
  `evidence_finding`, `finding_limitation`, `forensic_result`, `sample_type`, `sample_result`
- **CITIZEN** sees only: `case_status`, `hearing_date`, `next_hearing_date`, `court_name`,
  `case_stage`, `public_order_status`, `filing_date`
- COURT/POLICE/LAWYER/ADMIN see all facts.

**System role vs case role**: your *system role* (ADMIN/COURT/…) decides global abilities
(create case, user management). Your *case role* (row in `case_access`) decides what you
can do **in that case**. A system-COURT user with no access row for a case gets 403 on it.
**ADMIN is the exception**: it bypasses `case_access` completely — no grant is ever needed
for ADMIN to read any case or manage its assignments, and ADMIN is deliberately not an
assignable case_role (granting `case_role: ADMIN` → 422). An ADMIN-created case has zero
`case_access` rows yet ADMIN can still read and administer it.

### A7.2 Full six-role scenario

```powershell
# 1) COURT creates the case (auto-assigned COURT on it)
curl.exe -s -X POST http://127.0.0.1:8002/cases -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"case_id":"T14-RBAC-1","title":"RBAC scenario"}' | ConvertFrom-Json

# 2) COURT grants the other five roles
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"police@nyayaos.dev","case_role":"POLICE"}'     | ConvertFrom-Json
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"lawyer@nyayaos.dev","case_role":"LAWYER"}'     | ConvertFrom-Json
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"forensic@nyayaos.dev","case_role":"FORENSIC"}' | ConvertFrom-Json
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"citizen@nyayaos.dev","case_role":"CITIZEN"}'   | ConvertFrom-Json

# 3) list access
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6
```

Expected: five ACTIVE rows (court auto + 4 grants), each with `user_id`, `email`,
`system_role`, `case_role`, `status=ACTIVE`, `granted_by` = court's user_id.

**Ingest one fact per role** (charge + a forensic-whitelist fact):

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/text -H "Authorization: Bearer $COURT"    -H "Content-Type: application/json" -d '{"text":"Charge: IPC 302","force_fallback":true}'  | Out-Null
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/text -H "Authorization: Bearer $POLICE"   -H "Content-Type: application/json" -d '{"text":"Weapon: knife","force_fallback":true}'   | Out-Null
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/text -H "Authorization: Bearer $FORENSIC" -H "Content-Type: application/json" -d '{"text":"Victim injury: stab wound","force_fallback":true}' | Out-Null
```

**Role-by-role verification** (each line prints an HTTP status; expected value in comment):

```powershell
# POLICE: sees all facts, cannot PATCH metadata, cannot manage access
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts -H "Authorization: Bearer $POLICE" | ConvertFrom-Json -Depth 6   # 200: charge + weapon_type + victim_injury
curl.exe -s -o /dev/null -w "%{http_code}`n" -X PATCH http://127.0.0.1:8002/cases/T14-RBAC-1 -H "Authorization: Bearer $POLICE" -H "Content-Type: application/json" -d '{"title":"hijack"}'   # 403
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $POLICE" -H "Content-Type: application/json" -d '{"email":"admin@nyayaos.dev","case_role":"COURT"}'   # 403

# LAWYER: sees all facts AND raw observations (live-verified 200 on both; only CITIZEN is denied observations)
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts -H "Authorization: Bearer $LAWYER" | ConvertFrom-Json -Depth 6          # 200: all facts
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases/T14-RBAC-1/observations -H "Authorization: Bearer $LAWYER"   # 200

# FORENSIC: whitelist filtering — 'charge' must be ABSENT, forensic facts present
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts -H "Authorization: Bearer $FORENSIC" | ConvertFrom-Json -Depth 6
#   expect: weapon_type + victim_injury present; NO charge

# CITIZEN: no observations, no INTERNAL documents, whitelist-only facts, can submit
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases/T14-RBAC-1/observations -H "Authorization: Bearer $CITIZEN"   # 403
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases/T14-RBAC-1/text -H "Authorization: Bearer $CITIZEN" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 999"}'   # 403
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts -H "Authorization: Bearer $CITIZEN" | ConvertFrom-Json -Depth 6   # 200: only citizen-whitelist keys (charge NOT visible)

# ADMIN override (NO case_access row exists for admin on this case — live-verified):
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases/T14-RBAC-1              -H "Authorization: Bearer $ADMIN"   # 200 (bypass)
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases/T14-RBAC-1/observations -H "Authorization: Bearer $ADMIN"   # 200
curl.exe -s http://127.0.0.1:8002/cases -H "Authorization: Bearer $ADMIN" | ConvertFrom-Json   # lists ALL cases incl. T14-RBAC-1
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/text -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 999"}'   # 403 — no CAMS mutation
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/resync -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{}'   # 403
curl.exe -s -o /dev/null -w "%{http_code}`n" -X PATCH http://127.0.0.1:8002/cases/T14-RBAC-1 -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"court_name":"High Court"}'   # 200 — administration allowed
```

> ADMIN note (live-verified): ADMIN **bypasses `case_access`** for every read
> (`GET /cases`, `/cases/{id}`, `/full`, `/observations`, `/facts`, `/history`,
> `/conflicts`, `/provenance`, `/documents`, `/access`, `/submissions` → 200 with zero
> access rows) and for administration (`PATCH` metadata, grant/revoke access → 200).
> ADMIN can **never** mutate legal/CAMS state: `/text`, `/upload`, `/resync`, submission
> create and submission review all return 403. Granting `case_role: "ADMIN"` is rejected
> with 422 — ADMIN is system-wide only, not an assignable case role.

**Revoke access** (COURT revokes LAWYER, then lawyer is locked out):

```powershell
$access = curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/access -H "Authorization: Bearer $COURT" | ConvertFrom-Json
$lawyerRow = $access.access | Where-Object { $_.email -eq 'lawyer@nyayaos.dev' }
curl.exe -s -X DELETE "http://127.0.0.1:8002/cases/T14-RBAC-1/access/$($lawyerRow.user_id)" -H "Authorization: Bearer $COURT" | ConvertFrom-Json
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/cases/T14-RBAC-1/facts -H "Authorization: Bearer $LAWYER"   # 403 now
```

Re-grant afterwards if you continue using lawyer.

### A7.3 Complete citizen submission workflow

```powershell
# 0) prerequisite: citizen has CITIZEN case role on T14-RBAC-1 (A7.2 step 2)

# 1) baseline twin state (COURT) — record charge value + history length
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts   -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/history -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6

# 2) CITIZEN submits a statement (NO extraction happens yet)
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/submissions -H "Authorization: Bearer $CITIZEN" -H "Content-Type: application/json" -d '{"title":"Eyewitness account","text":"Charge: IPC 302. I saw the incident near the station."}' | ConvertFrom-Json -Depth 6
#   expect: status PENDING, a `submission_id` UUID, reviewed_by/reviewed_at/review_note/document_id all null

# 3) PROVE no CAMS mutation happened: facts + history unchanged vs step 1
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/history -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6

# 4) CITIZEN sees only their own submissions
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/submissions -H "Authorization: Bearer $CITIZEN" | ConvertFrom-Json -Depth 6

# 5) COURT reviews: APPROVE (use the submission id from step 2)
curl.exe -s -X POST "http://127.0.0.1:8002/cases/T14-RBAC-1/submissions/<SUBMISSION_ID>/review" -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"decision":"APPROVE","note":"verified with FIR"}' | ConvertFrom-Json -Depth 10
```

On APPROVE expect (live-verified): `submission.status=APPROVED`, `reviewed_by_email` =
`court@nyayaos.dev`, `review_note` stored, `document_id` populated; the text becomes an
**official document** with `source = citizen:<submitter email>`, `source_type = citizen`,
`visibility = INTERNAL`; new `observations_created`, a new CAMS `decision` appended to
history, and the twin updated only if CAMS accepts. For a first-ever `charge` fact from a
citizen the live run returned **ACCEPTED, C1 = 0.8**: citizen is not in the charge
authority table → A defaults to 0.5; single observation → T = 1.0, X = 1.0; fallback
E = 0.75 → C = 0.3(0.5) + 0.3(1) + 0.2(1) + 0.2(0.75) = 0.15+0.30+0.20+0.15 = **0.800**.
Then verify all downstream state:

```powershell
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts      -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/history    -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/provenance -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 8
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/documents  -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6
```

```powershell
# 6) second submission -> REJECT
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-RBAC-1/submissions -H "Authorization: Bearer $CITIZEN" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 999","title":"bogus claim"}' | ConvertFrom-Json
curl.exe -s -X POST "http://127.0.0.1:8002/cases/T14-RBAC-1/submissions/<SUBMISSION_ID_2>/review" -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"decision":"REJECT","note":"unverified"}' | ConvertFrom-Json -Depth 6
# 7) PROVE no mutation: facts/history identical to post-APPROVE state; no new documents
curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/history -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 6
```

Non-COURT review attempt must fail:

```powershell
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST "http://127.0.0.1:8002/cases/T14-RBAC-1/submissions/<SUBMISSION_ID>/review" -H "Authorization: Bearer $POLICE" -H "Content-Type: application/json" -d '{"decision":"APPROVE"}'   # 403
```

## A8. Task 4 — frontend (browser) walkthrough

Open `http://127.0.0.1:8002/`. The UI stores the JWT in `localStorage` under
`nyayaos_token`; every API call sends it as a Bearer header.

### A8.1 Login / session mechanics (any role)

1. Sign in as `court@nyayaos.dev` / `NyayaOS-dev-2026!`. Expected: overlay disappears;
   header shows the email and a `COURT` badge; case panel appears.
2. **Refresh the page (F5)** — you must remain signed in (token re-read from localStorage;
   `/auth/me` re-validates it). No re-login prompt.
3. Wrong password → overlay stays, status line shows the 401 error.
4. Click **Sign out** → overlay returns; localStorage token cleared (verify: DevTools →
   Application → Local Storage → key `nyayaos_token` gone).
5. Stale/invalid token: DevTools → Application → Local Storage → edit `nyayaos_token` to
   `garbage` → refresh → UI must show "Session expired or account deactivated — sign in
   again." and return to the login overlay (401 handling clears the session).
6. Deactivated user: as ADMIN deactivate an account (A9), then try to sign in as that
   account → rejected; an existing token for that account → 401 on next call → UI kicks
   back to login.

### A8.2 COURT view

Sign in as court, create case `T14-UI-1` (New case ID + Title → **Create case**), open it.
Expected visible sections: Case, Justice Twin status, **Upload material** (with the
"Share with citizen (CITIZEN_VISIBLE)" checkbox — COURT-only), Documents, Citizen
submissions (**with review note field + APPROVE/REJECT buttons on PENDING rows**), Case
access (grant form + list with Revoke buttons). User management section: **hidden**
(COURT is not ADMIN).

Do: paste `Charge: IPC 302` in the text box → **Ingest text** → twin panel shows
`charge = IPC 302`, resolved, confidence 0.944; history shows one ACCEPTED row.

### A8.3 POLICE / LAWYER view

Sign in as police (after court grants POLICE on `T14-UI-1` and you refresh the case list).
Expected: Upload section **present**; CITIZEN_VISIBLE checkbox **absent**; submissions
review controls **absent**; Case access grant form **absent**. Same for lawyer.
Open the case via the dropdown — if the case is not listed, your user has no ACTIVE
access row (RBAC filtering of `GET /cases`).

### A8.4 FORENSIC view (whitelist filtering in the UI)

Grant forensic FORENSIC on `T14-UI-1`, ingest `Charge: IPC 302` (as court) and
`Weapon: knife` (as forensic), then sign in as forensic and open the case.
Expected: twin panel shows **weapon_type only — `charge` must NOT appear anywhere**.
Upload section present, no review/access controls.

### A8.5 CITIZEN view

Grant citizen CITIZEN on `T14-UI-1`. Sign in as citizen, open the case.
Expected: **no Upload section**; submissions section shows a statement text box +
**Submit statement** button; own submissions listed with status badges (PENDING /
APPROVED / REJECTED); no APPROVE/REJECT buttons; no raw observations, no INTERNAL
documents, no confidence/provenance columns (citizen whitelist facts only).
Deep link test: sign in as citizen and navigate to
`http://127.0.0.1:8002/?case=T14-RBAC-1` **without** access → UI must show
"Case T14-RBAC-1 is not visible for this account." (403 handling), not a broken page.

### A8.6 ADMIN view

Sign in as admin. Expected: **User management (ADMIN)** section visible (create user
form, user table with Deactivate/Activate + Reset password buttons — the button for your
own account is disabled); case list shows only cases where admin has access; no Upload
section for cases (ADMIN is not an ingest role).

## A9. ADMIN user management

```powershell
# create
curl.exe -s -X POST http://127.0.0.1:8002/users -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"email":"t14.temp@nyayaos.dev","password":"TempPass-123!","system_role":"POLICE"}' | ConvertFrom-Json
#   -> 201, {"user": {id, email, system_role, is_active=true, created_at}} — NO password fields
#   (the id field is named "id"; use it as <USER_ID> below)

# duplicate -> 409  {"detail":"email already registered"}
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/users -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"email":"t14.temp@nyayaos.dev","password":"TempPass-123!","system_role":"POLICE"}'

# short password -> 422
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/users -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"email":"t14.x@nyayaos.dev","password":"short","system_role":"POLICE"}'

# list
curl.exe -s http://127.0.0.1:8002/users -H "Authorization: Bearer $ADMIN" | ConvertFrom-Json -Depth 6

# non-admin -> 403  {"detail":"ADMIN role required"}
curl.exe -s -o /dev/null -w "%{http_code}`n" http://127.0.0.1:8002/users -H "Authorization: Bearer $COURT"

# deactivate (use the "id" value from create/list as <USER_ID>) -> 200, is_active=false
curl.exe -s -X PATCH "http://127.0.0.1:8002/users/<USER_ID>" -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"is_active":false}' | ConvertFrom-Json

# deactivated user cannot login -> 401  {"detail":"Invalid credentials"}  (live-verified)
curl.exe -s -o /dev/null -w "%{http_code}`n" -X POST http://127.0.0.1:8002/auth/login -H "Content-Type: application/json" -d '{"email":"t14.temp@nyayaos.dev","password":"TempPass-123!"}'

# reactivate (200), reset password (200, login with NEW password 200), empty patch -> 422
#   422 detail: {"detail":"no fields supplied (is_active and/or password required)"}
curl.exe -s -X PATCH "http://127.0.0.1:8002/users/<USER_ID>" -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"is_active":true}' | ConvertFrom-Json
curl.exe -s -X PATCH "http://127.0.0.1:8002/users/<USER_ID>" -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{"password":"NewPass-456!"}' | ConvertFrom-Json
curl.exe -s -o /dev/null -w "%{http_code}`n" -X PATCH "http://127.0.0.1:8002/users/<USER_ID>" -H "Authorization: Bearer $ADMIN" -H "Content-Type: application/json" -d '{}'

# cleanup: remove the temp user (non-seed users are removable via cleanup.py --apply too)
```

A deactivated user's **existing tokens stop working immediately** (activity check on every
request) — live-verified: `/auth/me` with a token minted before deactivation returns
**401** `{"detail":"Not authenticated"}`.

## A10. Demo & research routes

```powershell
curl.exe -s http://127.0.0.1:8002/api/health  | ConvertFrom-Json          # no DB access
curl.exe -s http://127.0.0.1:8002/api/config  | ConvertFrom-Json          # {"weights":{...},"tau":0.55,"delta":0.1}
curl.exe -s http://127.0.0.1:8002/api/evaluation | ConvertFrom-Json       # paper results.md as {"markdown": "..."}
```

> `/api/evaluation` reports the **paper's validation-selected** configuration
> (`tau=0.45`, weights with wE=0.4, TSA=0.9840 …). That is the research result table —
> the **runtime** system uses the `/api/config` constants (τ=0.55, 0.3/0.3/0.2/0.2).
> Do not confuse the two.

Demo scenarios (public, write to the **demo scope only**):

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/demo/case-001 | ConvertFrom-Json -Depth 6
curl.exe -s -X POST http://127.0.0.1:8002/demo/scenario/conflict | ConvertFrom-Json -Depth 6
# valid scenario names (live-verified): conflict, corroboration, delayed, duplicate, noisy
# aliases for the full demo: full, full-demo, case-001. Unknown name -> 400.
# optional query param: ?case_id=DEMO-XYZ (defaults to the demo case-001)
```

**Demo isolation proof**: demo cases carry `is_demo=true` and live under
`data/demo_cases/`. Real-scope queries (`GET /cases` with a login) never show them, and
`POST /api/reset-demo` wipes only the demo scope:

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/api/reset-demo | ConvertFrom-Json
docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "SELECT case_number, is_demo FROM cases ORDER BY is_demo;"
#   -> demo rows gone; your T14-* real cases untouched
```

## A11. CAMS / Digital Twin research scenario (real numbers)

### Constants (must match `/api/config` before you start)

wA = 0.3, wT = 0.3, wX = 0.2, wE = 0.2, τ = 0.55, δ = 0.10.
Confidence: **C = 0.3·A + 0.3·T + 0.2·X + 0.2·E**.
Decision: accept top candidate iff **C1 ≥ τ AND (no C2 OR C1 − C2 ≥ δ)**; otherwise abstain
and keep the previous twin value.

Factor semantics (as implemented in `cams.py`):
- **A** — `SOURCE_AUTHORITY[fact_key][source_type]`; for `charge`: court 0.98, police 0.70,
  lawyer 0.65, forensic 0.40.
- **T** — median-absolute-deviation fit of the observation's event time to the fact's
  timeline: `T = 1 / (1 + gap/MAD)`; if MAD = 0, scale = 86400 s. With 2 observations the
  earlier one always gets **T = 0.5** and the later **T = 1.0** (MAD equals their gap).
- **X** — agreeing distinct sources ÷ all distinct sources for that fact.
- **E** — extraction reliability; the fallback extractor always yields **0.75**.
- A candidate's displayed factors come from its **highest-confidence member observation**.

### Scenario setup (fresh case, four roles)

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"case_id":"T14-CAMS-2","title":"CAMS scenario"}' | Out-Null
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"lawyer@nyayaos.dev","case_role":"LAWYER"}'     | Out-Null
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"police@nyayaos.dev","case_role":"POLICE"}'   | Out-Null
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/access -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"email":"forensic@nyayaos.dev","case_role":"FORENSIC"}' | Out-Null
```

### Step 1 — COURT ingests `Charge: IPC 302` → deterministic ACCEPT

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/text -H "Authorization: Bearer $COURT" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 302","force_fallback":true,"title":"Court charge sheet excerpt"}' | ConvertFrom-Json -Depth 10
```

Single observation → timeline median = itself, MAD = 0 → T = 1.0; X = 1/1 = 1.0.

| Candidate | A | T | X | E | C |
|---|---|---|---|---|---|
| IPC 302 (court) | 0.98 | 1.0 | 1.0 | 0.75 | **0.944** |

C = 0.3(0.98) + 0.3(1.0) + 0.2(1.0) + 0.2(0.75) = 0.294 + 0.300 + 0.200 + 0.150 = **0.944**
(live-observed: `0.9440000000000001`). No C2 → C1 ≥ τ → **ACCEPTED**.
Twin: `charge = IPC 302`, resolved, confidence 0.944.

### Step 2 — LAWYER ingests `Charge: IPC 304` → deterministic ABSTAIN (margin rule)

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/text -H "Authorization: Bearer $LAWYER" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 304","force_fallback":true,"title":"Defence counsel note"}' | ConvertFrom-Json -Depth 10
```

Two observations [t_court, t_lawyer]: median = t_lawyer, MAD = the gap → court (earlier)
gets T = 0.5 **exactly**, lawyer (later) T = 1.0. X = 1/2 = 0.5 for both values.

| Candidate | A | T | X | E | C |
|---|---|---|---|---|---|
| IPC 304 (lawyer) | 0.65 | 1.0 | 0.5 | 0.75 | **0.745** |
| IPC 302 (court) | 0.98 | 0.5 | 0.5 | 0.75 | **0.694** |

C1 = 0.195+0.300+0.100+0.150 = 0.745; C2 = 0.294+0.150+0.100+0.150 = 0.694.
**C1 = 0.745 ≥ τ = 0.55, but margin = 0.051 < δ = 0.10 → ABSTAINED.**
Twin **keeps IPC 302**; `GET /conflicts` now shows `charge` unresolved with
reason `abstain: margin=0.051 < delta=0.1`. These numbers are timing-independent —
the 2-observation MAD structure is exact.

### Step 3 — POLICE ingests `Charge: IPC 302` → ABSTAIN (outcome deterministic, exact numbers timing-dependent)

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/text -H "Authorization: Bearer $POLICE" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 302","force_fallback":true,"title":"Police FIR excerpt"}' | ConvertFrom-Json -Depth 10
```

Run steps 3 and 4 **back-to-back**. With three observations the MAD is the *smaller* of
the two gaps, so whichever observation sits far from the cluster gets a crushed T.
In the live captured run (lawyer→police ≈ 18 s apart, court ≈ 39 s before lawyer):

| Candidate | A | T | X | E | C |
|---|---|---|---|---|---|
| IPC 302 (best member: court) | 0.98 | 0.464414 | 2/3 | 0.75 | **0.716657** |
| IPC 304 (lawyer) | 0.65 | 1.0 | 1/3 | 0.75 | **0.711667** |

margin = 0.004991 < 0.10 → **ABSTAINED** (twin still IPC 302). If your steps 2→3 run
within a second of each other you may instead see IPC 304 briefly as C1 (≈0.712 vs
≈0.643, margin ≈0.068) — **still ABSTAINED**. The decision is invariant; the exact T
values depend on your wall-clock gaps. This is the MAD quirk: corroboration (X 1/2→2/3)
was cancelled by the court record becoming a temporal outlier.

### Step 4 — FORENSIC ingests `Charge: IPC 302` → deterministic ACCEPT (corroboration wins)

```powershell
curl.exe -s -X POST http://127.0.0.1:8002/cases/T14-CAMS-2/text -H "Authorization: Bearer $FORENSIC" -H "Content-Type: application/json" -d '{"text":"Charge: IPC 302","force_fallback":true,"title":"Forensic report excerpt"}' | ConvertFrom-Json -Depth 10
```

Four observations [court, lawyer, police, forensic]; median (index 2) = **police** → police
T = 1.0 exactly. IPC 302 now has 3 of 4 distinct sources (X = 0.75) vs IPC 304 (X = 0.25).
Best IPC-302 member is the police observation:

| Candidate | A | T | X | E | C |
|---|---|---|---|---|---|
| IPC 302 (police member) | 0.70 | 1.0 | 0.75 | 0.75 | **0.810** |
| IPC 304 (lawyer) | 0.65 | 0.5–1.0 | 0.25 | 0.75 | **0.545–0.695** |

C1 = 0.210+0.300+0.150+0.150 = **0.810**. margin ≥ 0.810 − 0.695 = **0.115 ≥ δ** in every
timing regime → **ACCEPTED** (live-observed: C2 = 0.599860, lawyer T = 0.682867,
margin = 0.210140). If you pause long between steps the displayed C1 can rise toward
~0.894 (the court observation becoming the best member) — the decision is unchanged.

**RBAC bonus visible in this very response**: the forensic caller's `facts` dict comes
back **without `charge`** (forensic whitelist excludes it) even though the decision block
is present — live proof of role-based fact filtering.

### Final state verification

```powershell
curl.exe -s http://127.0.0.1:8002/cases/T14-CAMS-2/facts      -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 8
curl.exe -s http://127.0.0.1:8002/cases/T14-CAMS-2/conflicts  -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 8
curl.exe -s http://127.0.0.1:8002/cases/T14-CAMS-2/history    -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 8
curl.exe -s http://127.0.0.1:8002/cases/T14-CAMS-2/provenance -H "Authorization: Bearer $COURT" | ConvertFrom-Json -Depth 8
```

Expected (live-captured values):
- `facts.charge`: value `IPC 302`, status `resolved`, confidence `0.81`, **3** supporting
  observations, provenance from court + police + forensic.
- `conflicts`: `{}` (cleared by the accept).
- `history`: four rows —
  `ACCEPTED C1=0.944` → `ABSTAINED margin=0.051` → `ABSTAINED margin≈0.005` →
  `ACCEPTED C1=0.810 margin≈0.210`.

### Ablation (research extra)

`POST /demo/scenario/{name}` and the evaluation tooling support single-factor ablation
(zero one of A/T/X/E and renormalize the remaining weights to sum 1). The runtime API
does not take an ablation parameter — ablations are exercised in the evaluation suite
(`/api/evaluation` reports the paper's results). Constants above must remain unchanged
for any demo or paper claim.

---

# PART B — MANUAL VERIFICATION (10 points per feature)

Legend for every feature: (1) what, (2) prerequisites, (3) exact action, (4) expected
HTTP status, (5) expected response/UI, (6) expected PostgreSQL state, (7) how to inspect
the DB, (8) expected filesystem state, (9) what must NOT happen, (10) what failure means.

DB inspection shorthand used below —
`PSQL "<sql>"` means:
`docker compose exec -T db psql -U nyayaos -d nyayaos_rbac -c "<sql>"`.

## B1 — Task 1: persistence & authentication

### B1.1 JWT login

1. **Feature**: `POST /auth/login` issues an HS256 JWT for valid credentials.
2. **Prereq**: stack healthy (A2.3); seed users present (A2.5).
3. **Action**: A5.1 login command.
4. **Status**: 200.
5. **Response**: `access_token` (~255 chars, two dots), `token_type: bearer`.
6. **DB state**: unchanged — login writes nothing.
7. **Inspect**: `PSQL "SELECT email FROM users WHERE email='court@nyayaos.dev';"` → 1 row.
8. **Filesystem**: unchanged.
9. **Must NOT**: response contain `password`/`password_hash`; DB gain rows; token appear in logs.
10. **Failure means**: 401 → wrong seed password or user missing (re-seed: restart api);
    500 → `JWT_SECRET_KEY` unset/invalid.

### B1.2 Identity endpoint

1. **Feature**: `GET /auth/me` returns the caller's profile from the token.
2. **Prereq**: `$COURT` token from B1.1.
3. **Action**: A5.2 command.
4. **Status**: 200.
5. **Response**: `email`, `system_role=COURT`, `is_active=true`, `id` UUID; no secrets.
6. **DB**: unchanged.
7. **Inspect**: `PSQL "SELECT id, email, system_role FROM users WHERE email='court@nyayaos.dev';"` — response `id` must equal the DB `id`.
8. **Filesystem**: unchanged.
9. **Must NOT**: return password hash or other users' data.
10. **Failure means**: 401 → token expired/invalid or user deactivated since minting.

### B1.3 Token rejection

1. **Feature**: missing/garbage/expired tokens are rejected on protected routes.
2. **Prereq**: running stack.
3. **Action**: the three A5.3 commands.
4. **Status**: 401, 401, 401.
5. **Response**: `{"detail": ...}` only.
6. **DB**: unchanged. 7. **Inspect**: n/a. 8. **Filesystem**: unchanged.
9. **Must NOT**: any 200; no data leaked in the 401 body.
10. **Failure means**: 200 → auth dependency broken (critical); 500 → JWT decode crash.

### B1.4 PostgreSQL persistence across restarts

1. **Feature**: cases survive `stop/start` (named volume).
2. **Prereq**: B1.1 token.
3. **Action**: A5.4 sequence.
4. **Status**: 200 on re-list.
5. **Response**: `T14-PERSIST` present after restart.
6. **DB**: row in `cases` before and after.
7. **Inspect**: `PSQL "SELECT case_number, created_at FROM cases WHERE case_number='T14-PERSIST';"`
8. **Filesystem**: `data/cases/T14-PERSIST/` exists inside the api container
   (`docker compose exec -T api python -c "from paths import DATA_ROOT; print(sorted(p.name for p in DATA_ROOT.iterdir()))"`).
9. **Must NOT**: data vanish after restart; `docker compose ps` show a recreated volume.
10. **Failure means**: data lost → volume misconfigured (check `docker volume ls` for
    `nyayaos-task14_task14_pgdata`).

### B1.5 Deactivation kills sessions

1. **Feature**: `is_active=false` blocks login **and** invalidates existing tokens.
2. **Prereq**: `$ADMIN` token; a temp user from A9.
3. **Action**: A9 deactivate, then login attempt + `/auth/me` with the old token.
4. **Status**: PATCH 200; login 401 (`Invalid credentials`); `/auth/me` with the old token 401.
5. **Response**: user object shows `is_active=false`; the blocked login returns the
   generic `Invalid credentials` (no deactivation detail leaked — correct: the API does
   not reveal why authentication failed).
6. **DB**: `users.is_active=false` for that email.
7. **Inspect**: `PSQL "SELECT email, is_active FROM users WHERE email='t14.temp@nyayaos.dev';"`
8. **Filesystem**: unchanged.
9. **Must NOT**: old token keep working; user row be deleted.
10. **Failure means**: old token still 200 → activity check missing from the auth
    dependency (security bug — stop and fix).

## B2 — Task 2: case + ingestion + twin API

### B2.1 Case creation & auto-assignment

1. **Feature**: `POST /cases` creates a case and auto-assigns the creator COURT access.
2. **Prereq**: `$COURT`.
3. **Action**: A6.1 step 1 with `T14-API-1`.
4. **Status**: 200.
5. **Response**: case object with your `case_id`, `case_status=OPEN`.
6. **DB**: 1 row in `cases`; 1 row in `case_access` (case_role=COURT, status=ACTIVE,
   granted_by = your user id or null-self).
7. **Inspect**: `PSQL "SELECT c.case_number, a.case_role, a.status FROM cases c JOIN case_access a ON a.case_id=c.id WHERE c.case_number='T14-API-1';"`
8. **Filesystem**: `data/cases/T14-API-1/` created lazily on first ingestion (may not exist yet).
9. **Must NOT**: POLICE/LAWYER/FORENSIC/CITIZEN be able to create (verify: same POST with
   `$POLICE` → 403); duplicate case_id succeed (→ 409).
10. **Failure means**: 403 for court → RBAC permission table broken; no access row →
    auto-assignment regression.

### B2.2 Text ingestion → extraction → observations → CAMS

1. **Feature**: `POST /cases/{id}/text` runs the full pipeline and returns decisions.
2. **Prereq**: B2.1 case; `$COURT`.
3. **Action**: A6.1 step 2 (`Charge: IPC 302`, `force_fallback:true`).
4. **Status**: 200.
5. **Response**: `document.source_id=court:court@nyayaos.dev`, `source_type=court`,
   `extractor=fallback`; `extraction.facts[0]` = charge/IPC 302/E 0.75;
   `decisions[0]` = ACCEPTED C1=0.944; `facts.charge.status=resolved`.
6. **DB**: rows in `documents` (1), `observations` (1), `history` (1), `facts` (1,
   value IPC 302), `stakeholders` (court registered).
7. **Inspect**: `PSQL "SELECT (SELECT count(*) FROM documents d JOIN cases c ON c.id=d.case_id WHERE c.case_number='T14-API-1') AS docs, (SELECT count(*) FROM observations o JOIN cases c ON c.id=o.case_id WHERE c.case_number='T14-API-1') AS obs;"`
8. **Filesystem**: `data/cases/T14-API-1/` exists with the stored document text.
9. **Must NOT**: a client-supplied `"source":"media"` in the body change `source_type`
   (spoof-proof); observations be editable via any route; Gemini be called
   (`extractor` must say `fallback` while `GEMINI_API_KEY` is blank).
10. **Failure means**: `source_type` reflects the body → identity derivation broken
    (security); no decision row → CAMS wiring regression.

### B2.3 File upload + OCR path

1. **Feature**: `POST /cases/{id}/upload` accepts PDF/image/text and stores OCR output.
2. **Prereq**: case + ingest-capable role token (A6.2).
3. **Action**: A6.2 commands.
4. **Status**: 200.
5. **Response**: same envelope as text ingest; `document.ocr` non-null for scanned/image
   input; facts extracted from the file content.
6. **DB**: `documents` row with `ocr` populated; observations per extracted fact.
7. **Inspect**: `PSQL "SELECT title, source_type, (ocr IS NOT NULL) AS has_ocr FROM documents ORDER BY ingestion_time DESC LIMIT 1;"`
8. **Filesystem**: uploaded file stored under the case directory.
9. **Must NOT**: executable/unknown mime types be silently accepted as documents with
   fabricated text; upload work for CITIZEN (→ 403).
10. **Failure means**: tesseract missing in image (check `docker compose exec -T api
    tesseract --version`); pypdf failure on scanned PDFs is expected (image path uses OCR).

### B2.4 Twin read endpoints

1. **Feature**: `/facts`, `/history`, `/conflicts`, `/provenance`, `/full`, `/documents`,
   `/observations`, `/stakeholders` reflect DB state.
2. **Prereq**: B2.2 ingested.
3. **Action**: A6.1 step 3 commands.
4. **Status**: 200 each (for a case member).
5. **Response**: facts → charge resolved 0.944; history → 1 ACCEPTED row with
   weights/tau/delta echoed; conflicts → `{}`; provenance → 1 entry quoting
   `Charge: IPC 302` with document_id; full → everything + timeline.
6. **DB**: matches exactly (compare counts).
7. **Inspect**: `PSQL "SELECT fact_key, value, status, confidence FROM facts f JOIN cases c ON c.id=f.case_id WHERE c.case_number='T14-API-1';"`
8. **Filesystem**: unchanged by reads.
9. **Must NOT**: reads mutate anything (run twice — identical output, `history` count
   unchanged); CITIZEN see `/observations` (403).
10. **Failure means**: divergence between API and SQL → serializer bug.

### B2.5 Conflict detection & abstention

1. **Feature**: competing values produce an unresolved conflict, twin keeps previous value.
2. **Prereq**: A11 steps 1–2 executed (court 302 + lawyer 304).
3. **Action**: `GET /cases/T14-CAMS-2/conflicts` with `$COURT`.
4. **Status**: 200.
5. **Response**: `charge` present, `status=unresolved`, `reason` = `abstain: margin=0.051
   < delta=0.1`, both candidates with factors, `previous_value=IPC 302`.
6. **DB**: `facts.charge` still `IPC 302`; `conflicts` table has the charge row;
   `history` has the ABSTAINED row.
7. **Inspect**: `PSQL "SELECT decision, \"C1\", \"C2\", margin FROM history h JOIN cases c ON c.id=h.case_id WHERE c.case_number='T14-CAMS-2' ORDER BY timestamp;"`
8. **Filesystem**: unchanged.
9. **Must NOT**: twin value flip to IPC 304; the lawyer observation be deleted or edited.
10. **Failure means**: value flipped → margin rule (δ) broken; conflict missing →
    conflict recorder regression.

### B2.6 Resync

1. **Feature**: `POST /cases/{id}/resync` recomputes decisions for all facts (COURT only).
2. **Prereq**: case with observations.
3. **Action**: A6.3.
4. **Status**: 200 (court) / 403 (police).
5. **Response**: fresh `decisions` array; values unchanged when no new observations.
6. **DB**: new `history` rows appended (audit trail grows); `facts` unchanged.
7. **Inspect**: history count before/after via B2.5 query.
8. **Filesystem**: unchanged.
9. **Must NOT**: observations be modified; non-COURT roles succeed.
10. **Failure means**: facts changed without new data → resync is mutating state (bug).

## B3 — Task 3: RBAC

### B3.1 Case access grant/revoke lifecycle

1. **Feature**: COURT/ADMIN grant, list, revoke case access.
2. **Prereq**: `$COURT`, case `T14-RBAC-1`, target user exists.
3. **Action**: A7.2 steps 2–3, then the revoke block.
4. **Status**: grant 200; list 200; revoke 200; revoked user's next call 403.
5. **Response**: grant echoes `user_id/email/system_role/case_role/status=ACTIVE/
   granted_by`; list shows all rows; revoke shows `status=REVOKED`.
6. **DB**: `case_access` row inserted, then `status` flips to REVOKED (row is kept —
   audit trail, not deleted).
7. **Inspect**: `PSQL "SELECT u.email, a.case_role, a.status FROM case_access a JOIN users u ON u.id=a.user_id JOIN cases c ON c.id=a.case_id WHERE c.case_number='T14-RBAC-1' ORDER BY u.email;"`
8. **Filesystem**: unchanged.
9. **Must NOT**: POLICE/LAWYER/FORENSIC/CITIZEN grant access (403); granting change the
   user's **system_role**; a revoked user retain any case access; granting a non-existent
   email succeed (→ 404).
10. **Failure means**: 403 for court → permission matrix broken; revoked user still 200 →
    access check not consulting `status`.

### B3.2 Role capability matrix (403 verification)

1. **Feature**: each case role can do exactly what A7.1's matrix says.
2. **Prereq**: all five roles granted on `T14-RBAC-1`; facts ingested (A7.2).
3. **Action**: the role-by-role block in A7.2.
4. **Status**: as annotated per line (200s and 403s).
5. **Response**: 403 bodies are `{"detail": ...}` only.
6. **DB**: denied actions leave **no** rows (e.g. police PATCH attempt doesn't change
   `cases.title`).
7. **Inspect**: `PSQL "SELECT title FROM cases WHERE case_number='T14-RBAC-1';"` → still
   `RBAC scenario`.
8. **Filesystem**: unchanged by denied calls.
9. **Must NOT**: any annotated 403 return 200; any 200 return 403; error bodies leak
   stack traces or other users' data.
10. **Failure means**: a specific cell failing pinpoints the broken permission in the
    matrix (compare against `rbac.py` permission sets).

### B3.3 FORENSIC fact whitelist

1. **Feature**: forensic sees only its 8 whitelist fact keys.
2. **Prereq**: case with `charge` + `weapon_type` + `victim_injury` facts; `$FORENSIC` granted.
3. **Action**: `curl.exe -s http://127.0.0.1:8002/cases/T14-RBAC-1/facts -H "Authorization: Bearer $FORENSIC" | ConvertFrom-Json -Depth 6`
4. **Status**: 200.
5. **Response**: `facts` contains `weapon_type`/`victim_injury` (if ingested); **no**
   `charge` key at all. With only `charge` present in the case, `facts` is `{}`
   (live-verified: `{"case_id":"T14-CAMS-1","facts":{}}`).
6. **DB**: `facts` table still holds `charge` (filtering is view-layer only).
7. **Inspect**: `PSQL "SELECT fact_key FROM facts f JOIN cases c ON c.id=f.case_id WHERE c.case_number='T14-RBAC-1';"` → includes charge.
8. **Filesystem**: unchanged.
9. **Must NOT**: `charge` appear in any forensic-visible payload (facts, full, ingest
   response, UI twin panel); the underlying row be deleted.
10. **Failure means**: charge visible → whitelist filter not applied on that serializer.

### B3.4 CITIZEN restrictions

1. **Feature**: citizen gets whitelist facts only; no observations, no INTERNAL docs, no ingest.
2. **Prereq**: `$CITIZEN` granted CITIZEN on the case.
3. **Action**: the CITIZEN block in A7.2.
4. **Status**: `/observations` 403; `/text` 403; `/facts` 200; `/documents` 200 (only
   CITIZEN_VISIBLE docs).
5. **Response**: citizen `/facts` contains only citizen-whitelist keys.
6. **DB**: unchanged by the denied calls.
7. **Inspect**: `PSQL "SELECT visibility, count(*) FROM documents d JOIN cases c ON c.id=d.case_id WHERE c.case_number='T14-RBAC-1' GROUP BY visibility;"`
8. **Filesystem**: unchanged.
9. **Must NOT**: citizen see INTERNAL documents, raw observations, confidence scores in
   UI, or other citizens' submissions.
10. **Failure means**: any 200 where 403 expected → citizen permission set broken.

### B3.5 Citizen submission → PENDING → no mutation

1. **Feature**: submitting creates a PENDING row and touches nothing else.
2. **Prereq**: A7.3 step 1 baseline recorded.
3. **Action**: A7.3 step 2, then step 3 comparison.
4. **Status**: 200 on submit.
5. **Response**: submission with `status=PENDING`; `reviewed_by`, `reviewed_at`,
   `review_note`, `document_id` all null.
6. **DB**: 1 row in `submissions`; `facts`/`history`/`observations`/`documents` counts
   **identical** to baseline.
7. **Inspect**: `PSQL "SELECT status, reviewed_by IS NULL AS unreviewed FROM submissions s JOIN cases c ON c.id=s.case_id WHERE c.case_number='T14-RBAC-1';"` plus history count query from B2.5.
8. **Filesystem**: no new document files.
9. **Must NOT**: any CAMS decision, observation, document, or twin change appear.
10. **Failure means**: mutation on submit → the "review-gated ingestion" invariant is
    broken (core Task 3 requirement).

### B3.6 COURT APPROVE → official ingestion

1. **Feature**: approving turns the statement into a document + observations + CAMS run.
2. **Prereq**: B3.5 PENDING submission; `$COURT`.
3. **Action**: A7.3 step 5, then the four verification GETs.
4. **Status**: 200 on review.
5. **Response**: submission `status=APPROVED`, `reviewed_by_email` = court's email,
   `review_note` stored, `document_id` populated; `ingestion` block with the new
   document + decisions.
6. **DB**: `submissions.status=APPROVED`; new rows in `documents`, `observations`,
   `history`; `facts` updated **iff** CAMS accepted (with court 302 + citizen 302, the
   citizen obs corroborates: expect a decision row either way).
7. **Inspect**: `PSQL "SELECT source_type, title FROM documents d JOIN cases c ON c.id=d.case_id WHERE c.case_number='T14-RBAC-1' ORDER BY ingestion_time DESC LIMIT 1;"` → source_type `citizen`.
8. **Filesystem**: case directory gains the submission document.
9. **Must NOT**: the citizen be able to self-approve (403 — verified in A7.3); police
   review succeed (403); the submission text be altered.
10. **Failure means**: no document created → approval pipeline unwired; wrong
    source_type → identity derivation bug.

### B3.7 COURT REJECT → zero mutation

1. **Feature**: rejecting records the decision and nothing else.
2. **Prereq**: second PENDING submission (A7.3 step 6).
3. **Action**: A7.3 steps 6–7.
4. **Status**: 200 on review.
5. **Response**: `status=REJECTED`, note stored.
6. **DB**: only `submissions` changed; `documents`/`observations`/`history`/`facts`
   counts identical to post-APPROVE state.
7. **Inspect**: counts before/after via B2.5 + `PSQL "SELECT count(*) FROM documents d JOIN cases c ON c.id=d.case_id WHERE c.case_number='T14-RBAC-1';"`
8. **Filesystem**: no new files.
9. **Must NOT**: rejected text ever reach extraction, the twin, or provenance; a second
   review of the same submission succeed (already-reviewed → 409
   `{"detail":"submission was already reviewed"}` — live-verified).
10. **Failure means**: mutation on reject → review gate bypassed (critical).

### B3.8 Case-scoped listing

1. **Feature**: `GET /cases` returns only cases with ACTIVE access.
2. **Prereq**: two users with different case sets (e.g. court on both T14 cases, citizen
   on one).
3. **Action**: `curl.exe -s http://127.0.0.1:8002/cases -H "Authorization: Bearer $CITIZEN" | ConvertFrom-Json`
4. **Status**: 200.
5. **Response**: only the granted case(s); revoked-access cases absent.
6. **DB**: `case_access` rows explain the list exactly.
7. **Inspect**: B3.1 query per case.
8. **Filesystem**: unchanged.
9. **Must NOT**: any case without an ACTIVE row appear; demo-scope cases appear.
10. **Failure means**: listing ignores `case_access` → data-exposure bug.

## B4 — Task 4: frontend

### B4.1 Login overlay & session persistence

1. **Feature**: JWT stored in localStorage; refresh keeps session; logout clears it.
2. **Prereq**: UI at `http://127.0.0.1:8002/`.
3. **Action**: A8.1 steps 1–4.
4. **Status**: login POST 200; `/auth/me` 200 on refresh.
5. **UI**: overlay → header badge; after F5 still signed in; after Sign out overlay returns.
6. **DB**: unchanged.
7. **Inspect**: n/a (client-side); DevTools → Application → Local Storage →
   `nyayaos_token` present/absent as annotated.
8. **Filesystem**: unchanged.
9. **Must NOT**: token be written to cookies/URLs; password persist anywhere; the app
   work after logout without re-login.
10. **Failure means**: session lost on refresh → token not re-read or `/auth/me` failing.

### B4.2 Invalid/expired token UX

1. **Feature**: 401 → "Session expired or account deactivated — sign in again." + forced logout.
2. **Prereq**: signed-in session.
3. **Action**: A8.1 step 5 (corrupt localStorage token, refresh).
4. **Status**: 401 from the first API call.
5. **UI**: exact message; login overlay shown; localStorage token removed.
6. **DB**: unchanged. 7. **Inspect**: n/a. 8. **Filesystem**: unchanged.
9. **Must NOT**: blank/broken page; infinite retry loop; token retained after 401.
10. **Failure means**: 401 handler not wired in `app.js`.

### B4.3 Role-aware UI surfaces

1. **Feature**: sections/buttons render per CASE_ROLE_UI (A8.2–A8.6).
2. **Prereq**: `T14-UI-1` with grants for all roles.
3. **Action**: sign in as each role, open the case, compare against A8.2–A8.6 lists.
4. **Status**: all underlying calls 200/403 exactly as the UI expects.
5. **UI**: COURT sees everything incl. CITIZEN_VISIBLE checkbox + review controls;
   POLICE/LAWYER/FORENSIC see upload only (no checkbox/review/access); CITIZEN sees
   submission box + own submissions only; ADMIN sees User management + access mgmt but
   **no** upload section.
6. **DB**: unchanged by viewing.
7. **Inspect**: n/a.
8. **Filesystem**: unchanged.
9. **Must NOT**: a hidden-for-role control be invocable via DevTools and succeed (the
   backend must 403 — UI hiding is cosmetic, RBAC is server-side; verify by trying).
10. **Failure means**: wrong section visible → CASE_ROLE_UI mismatch; backend 200 on a
    hidden action → **server-side RBAC hole (critical, report immediately)**.

### B4.4 FORENSIC whitelist in the twin panel

1. **Feature**: UI twin panel shows only whitelist facts for forensic.
2. **Prereq**: A8.4 case with charge + weapon facts.
3. **Action**: A8.4.
4. **Status**: facts call 200.
5. **UI**: weapon_type row present; **no charge row anywhere** (twin, documents, history).
6. **DB**: charge row still exists.
7. **Inspect**: B3.3 query.
8. **Filesystem**: unchanged.
9. **Must NOT**: charge leak via any panel, tooltip, or network response (check DevTools
   → Network → the facts response body).
10. **Failure means**: leak in response → backend filter; leak only in UI → renderer
    ignoring the filtered payload.

### B4.5 Deep-link 403 handling

1. **Feature**: `?case=<ID>` without access shows a clean denial.
2. **Prereq**: citizen signed in; `T14-RBAC-1` exists without citizen access.
3. **Action**: A8.5 deep link.
4. **Status**: 403 from the case fetch.
5. **UI**: "Case T14-RBAC-1 is not visible for this account." — no stack trace, no partial data.
6. **DB**: unchanged. 7. **Inspect**: n/a. 8. **Filesystem**: unchanged.
9. **Must NOT**: any case data render; the app crash or hang.
10. **Failure means**: 403 path unhandled in the deep-link loader.

---

# PART C — AUTOMATED TESTING (supplement, never a substitute for Parts A/B)

All commands run **inside the api container** with the test database URL explicit:

```powershell
# Full suite — expected: 67 passed
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest -q

# Per suite (counts from a live run):
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_auth.py -q          # 4 passed
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_db.py -q            # 9 passed
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_pipeline.py -q      # 16 passed
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_public_routes.py -q # 7 passed
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_rbac.py -q          # 19 passed
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_users_api.py -q     # 12 passed

# Single test by name
docker compose exec -T -e DATABASE_URL=postgresql+asyncpg://nyayaos:nyayaos@db:5432/nyayaos_rbac api python -m pytest tests/test_rbac.py::test_mutation_routes_are_exactly_the_reviewed_surface -q
```

Notes:
- **Pytest leaves residue in the runtime database.** A live full-suite run created 67
  disposable cases (`T2-*`, `T3-*`) and 21 test users (`t4user-*`, `citizen-*`, …) inside
  `nyayaos_rbac`. After testing — and always **before a demo** — run
  `docker compose exec -T api python cleanup.py --apply` (A3) to remove them. Seed users,
  schema, and migrations are preserved (live-verified: post-cleanup state = 0 cases,
  6 active seed users, empty `data/cases` and `data/demo_cases`, `/api/health` 200).
- The suite never touches the legacy `nyayaos` database.
- `StarletteDeprecationWarning: HTTP_422_UNPROCESSABLE_ENTITY` lines are upstream FastAPI
  deprecation noise (FastAPI 0.141 / Starlette 1.6 in the container) — not failures.
- The route-surface guard test recurses into FastAPI's lazy `_IncludedRouter` wrappers,
  so it passes on both old and new FastAPI.
- **A green pytest run does NOT prove the manual behaviors in Parts A/B** (UI rendering,
  browser session handling, Docker networking, real OCR, cross-container DB identity).
  Run Parts A and B by hand before any demo.

# PART D — FINAL PRE-DEMO CHECKLIST

Work top to bottom. Change `NOT TESTED` to `PASS` or `FAIL` **only after personally
executing** the referenced step. Never mark PASS because pytest passed.

**Infrastructure**
- [ ] Docker Desktop running; `docker compose ps` shows api + db healthy (A2.3) — NOT TESTED
- [ ] Correct database selected: `SELECT current_database()` = `nyayaos_rbac` (A4.3) — NOT TESTED
- [ ] Legacy `nyayaos` DB untouched: no compose file/env references it (0.1) — NOT TESTED
- [ ] Migrations at head: `alembic current` = `t3rbac0003 (head)` (A2.4) — NOT TESTED
- [ ] Secure JWT secret configured: ≥64 hex chars in `.env`, not committed (A1.4) — NOT TESTED
- [ ] Ports 8002/5433 bound by this stack only (A1.5) — NOT TESTED
- [ ] Seed users available: six rows in `users`, all active (A2.5) — NOT TESTED
- [ ] Backend running: `/api/health` returns exact constants (A4.2) — NOT TESTED
- [ ] Frontend loads: `http://127.0.0.1:8002/` shows sign-in overlay (A4.4) — NOT TESTED

**Task 1 — persistence & auth**
- [ ] B1.1 login returns JWT, no secrets in body — NOT TESTED
- [ ] B1.2 `/auth/me` matches DB user — NOT TESTED
- [ ] B1.3 missing/garbage token → 401 — NOT TESTED
- [ ] B1.4 case survives stop/start — NOT TESTED
- [ ] B1.5 deactivation blocks login AND kills existing tokens — NOT TESTED

**Task 2 — API surface**
- [ ] B2.1 case create + COURT auto-assignment; police create → 403 — NOT TESTED
- [ ] B2.2 text ingest: identity server-derived, fallback E=0.75, C1=0.944 ACCEPT — NOT TESTED
- [ ] B2.3 upload path stores document (+OCR for images) — NOT TESTED
- [ ] B2.4 all read endpoints match SQL state — NOT TESTED
- [ ] B2.5 conflict recorded, twin keeps previous value on abstain — NOT TESTED
- [ ] B2.6 resync: court 200 / police 403, no state mutation — NOT TESTED

**Task 3 — RBAC**
- [ ] B3.1 grant/list/revoke lifecycle; revoked user → 403 — NOT TESTED
- [ ] B3.2 matrix 403s: police PATCH, police grant-access, citizen ingest — NOT TESTED
- [ ] B3.3 forensic whitelist: `charge` absent from every forensic payload — NOT TESTED
- [ ] B3.4 citizen: no observations (403), no INTERNAL docs, whitelist facts — NOT TESTED
- [ ] B3.5 submission PENDING with zero CAMS mutation — NOT TESTED
- [ ] B3.6 APPROVE → document + observations + history + twin update — NOT TESTED
- [ ] B3.7 REJECT → zero mutation — NOT TESTED
- [ ] B3.8 `GET /cases` lists only ACTIVE-access cases — NOT TESTED
- [ ] A7.3 non-court review → 403 — NOT TESTED

**Task 4 — frontend**
- [ ] B4.1 login/refresh-persistence/logout — NOT TESTED
- [ ] B4.2 corrupted token → clean forced logout message — NOT TESTED
- [ ] B4.3 all six role surfaces match A8.2–A8.6 (incl. ADMIN user mgmt) — NOT TESTED
- [ ] B4.4 forensic UI shows no non-whitelist fact — NOT TESTED
- [ ] B4.5 deep link without access → clean 403 message — NOT TESTED
- [ ] A9 admin create/deactivate/reactivate/reset-password via UI or API — NOT TESTED

**CAMS research scenario (A11)**
- [ ] Step 1 ACCEPT C1=0.944 (exact) — NOT TESTED
- [ ] Step 2 ABSTAIN margin=0.051 (exact, timing-independent) — NOT TESTED
- [ ] Step 3 ABSTAIN (outcome; exact T timing-dependent) — NOT TESTED
- [ ] Step 4 ACCEPT C1=0.810, margin ≥ 0.115 — NOT TESTED
- [ ] Final twin: IPC 302 resolved @ 0.81, 3 provenance sources, conflicts `{}` — NOT TESTED
- [ ] History shows the full ACCEPT→ABSTAIN→ABSTAIN→ACCEPT chain — NOT TESTED

**Demo isolation & cleanup**
- [ ] A10 demo scenario runs; real cases unaffected — NOT TESTED
- [ ] A10 `/api/reset-demo` wipes demo scope only — NOT TESTED
- [ ] A3.1 cleanup dry-run plan reviewed — NOT TESTED
- [ ] A3.2 cleanup `--apply` removes T14-* cases, keeps seeds + schema — NOT TESTED

**Automated suite (supplement only)**
- [ ] Part C full suite: 67 passed — NOT TESTED

---

*Guide generated from a live end-to-end run of the `khushi-test` stack on 2026-09-21.
CAMS numbers in A11 are captured outputs, cross-checked against `cams.py` arithmetic.
CAMS confidence is not legal truth; evaluation data is synthetic.*
