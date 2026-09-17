# NyayaOS-lite

**Research prototype. CAMS confidence is NOT legal truth.**  
Evaluation numbers come from synthetic data in `evaluate.py` and are separate from demo case files.

## What this is (simple)

```
Your text
   → Gemini extracts facts + exact quotes (or a labelled rule-based fallback)
   → Each fact becomes an Observation
   → Observations are saved forever as JSON files
   → CAMS compares sources using A / T / X / E
   → Digital Twin shows only the current synchronized values
   → History, provenance, and unresolved conflicts are stored
```

| Piece | Responsibility |
| --- | --- |
| **Gemini** | Extract facts and evidence from text only. Never resolves conflicts. |
| **Observations (JSON)** | System memory. Never deleted — including duplicates and rejected claims. |
| **CAMS** | Scores and synchronizes competing claims (authority, time, corroboration, reliability). |
| **Digital Twin** | Current synchronized state only (`facts.json`). |
| **History / conflicts** | Every decision and every abstention, with C1/C2/margin and explanations. |

## File storage (no database)

```
data/cases/CASE-001/
  case.json
  documents.json      # original user texts
  observations.json   # append-only memory
  facts.json          # Digital Twin (current state)
  history.json        # every CAMS decision
  conflicts.json      # unresolved / abstained facts
  uploads/            # every raw uploaded file
  stakeholders/
    police__police-ps12/
      meta.json
      documents/      # copies + extracted .txt
      uploads_index.json
```

Data **survives FastAPI restarts**. Observations are never removed when CAMS rejects or abstains.

## CAMS (unchanged research core)

\[
C = w_A A + w_T T + w_X X + w_E E
\]

Update the twin only if \(C_1 \ge \tau\) and \((C_1 - C_2) \ge \delta\). Otherwise **abstain** and keep the previous twin value.

Core code preserved: `cams.py`, `config.py`, `evaluate.py`, `baselines.py`, `testcases.py`, `metrics.py`.

## OCR uploads

```bash
# PDF text layer works with pypdf alone.
# Image OCR needs Tesseract:
brew install tesseract   # macOS
```

Upload via the UI or `POST /cases/{id}/upload`. Files land in:

```
data/cases/{CASE_ID}/
  uploads/
  stakeholders/{source_type}__{source_id}/documents/
  documents.json / observations.json / facts.json / ...
```

Watch the **terminal running uvicorn** for step-by-step CAMS calculations.

## Configure Gemini

1. Copy `.env.example` to `.env`
2. Set `GEMINI_API_KEY=your_key`
3. Optional: `GEMINI_MODEL=gemini-2.5-flash`

If the key is missing or the API fails, the backend uses a **clearly labelled deterministic fallback** so the demo still works. The UI checkbox “Use rule-based fallback” forces that path.

## Run

```bash
cd nyayaos-lite
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn main:app --host 127.0.0.1 --port 8000
# Case dashboard: http://127.0.0.1:8000/
# API docs:       http://127.0.0.1:8000/docs
```

```bash
pytest -q
python cli.py               # interactive — same data/cases/ as the web UI
python cli.py --smoke ID    # create case + one text observation
python evaluate.py          # synthetic research table → results.md
python simulate.py          # qualitative demo → data/demo_cases/ only
```

## Main API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/cases` | Create case |
| `GET` | `/cases` | List cases |
| `GET` | `/cases/{id}` | Case snapshot |
| `POST` | `/cases/{id}/text` | **Full pipeline** text→extract→store→CAMS→twin |
| `GET` | `/cases/{id}/observations` | Full observation log |
| `GET` | `/cases/{id}/facts` | Digital Twin |
| `GET` | `/cases/{id}/history` | CAMS decisions |
| `GET` | `/cases/{id}/conflicts` | Unresolved facts |
| `GET` | `/cases/{id}/provenance` | Fact → decision → obs → evidence → text |
| `POST` | `/cases/{id}/resync` | Re-run CAMS from stored observations |
| `POST` | `/demo/case-001` | Built-in multi-source demo |

## Case dashboard (web + CLI)

Both UIs read/write the same folders under `data/cases/<case_id>/`:

- **Web** — `frontend/index.html` at `/`: select/create case → twin status (facts + UNRESOLVED conflicts) → upload PDF/image/text.
- **CLI** — `python cli.py`: same actions with live `console_log` CAMS reasoning in the terminal.

Deep-link a case: `http://127.0.0.1:8000/?case=YOUR_CASE_ID`

Demo/synthetic scenarios write only to `data/demo_cases/` (`POST /demo/*`, `simulate.py`).

## Why observations are never deleted

The twin is a *view*. The files are the *memory*. Keeping rejected and conflicting claims lets you prove how a value was chosen (or why the system abstained).

## Limitations

- File JSON storage, not a production database
- Gemini extraction quality depends on the model/key; fallback is pattern-based
- Roles/demo sources are illustrative
- Synthetic evaluation ≠ real case accuracy
- **Not for operational justice decisions**

## License / use

Student research prototype only.
