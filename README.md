# Prism

A two-sided hiring platform with recruiter workspaces, candidate profiles, job applications, and evidence-aware candidate matching.

## What works

- Server-backed signup/login/logout, hashed passwords, expiring HttpOnly sessions, role checks and workspace isolation.
- Candidate-owned profiles, persistent profile links, resume parsing, private-by-default discovery, job-specific skill guidance, self-service export and account deletion.
- Recruiter job posting, job-specific applicant ranking, applications, hiring stages, internal notes, interview scheduling and candidate withdrawal.
- Email-bound team invitation codes and member removal. Invitations are shared manually, not emailed automatically.
- Semantic retrieval with local embeddings, five configurable scoring signals, explanations/outreach for top results, feedback reranking previews, history, analytics and authenticated CSV exports.
- Recoverable vector indexing, bounded uploads, pagination validation, request throttling, admin metrics, tests and CI.

Scores describe matching heuristics, not hiring probabilities. Activity is excluded from the default composite score and is available only through an explicit availability preset. Career progression may be incomplete or self-reported. Supporting resume mentions are not credential verification. Humans make hiring decisions. External ATS integrations remain planned.

## Local setup

Use Python 3.11 and Node 22.12+ (Node 24 works). From the repository root on Windows PowerShell:

```powershell
git clone https://github.com/HarshitaAsija/Prism.git
cd Prism
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt
Copy-Item backend/.env.example backend/.env
.venv/Scripts/python.exe -m uvicorn main:app --app-dir backend --reload --port 8000
```

Set `NVIDIA_API_KEY` in `backend/.env` for job analysis, resume parsing, bias scans and generated explanations. `NVIDIA_MODEL` is configurable; use a model your provider account supports. Profile editing, jobs, applications, skill coverage, authentication and history work without an AI key. AI analysis failures return an explicit error and do not invent successful scores.

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. API documentation: http://localhost:8000/docs. Use the same hostname for both servers; do not mix localhost and 127.0.0.1. Register separate recruiter and candidate accounts. The old demo credentials are removed.

On macOS/Linux use `python3 -m venv .venv`, `source .venv/bin/activate`, then the same pip and uvicorn commands with `python`. `backend/setup.sh` is an optional helper. `backend/requirements.txt` pins portable direct dependencies; `requirements-windows.lock.txt` records the resolved Windows/Python 3.11 runtime snapshot.

## First hiring flow

1. Register a recruiter. Open **Hiring workspace**, post a job, and set its required skills.
2. Register a candidate. Edit their profile or upload a resume, then open **Jobs and applications**.
3. Check skill coverage and apply. Applying shares the profile with that job's workspace even when discovery is private.
4. Refresh the recruiter pipeline, use **Rank applicants** on the job, then screen the applicant, add an internal note and schedule an interview.
5. The candidate can refresh to see the stage and interview link or withdraw an active application. They can download or delete their data from **My data**.

Recruiters can also import candidates and run AI matching from the dashboard. Editing weights or submitting feedback produces a preview; run ranking again to save a new result. CSV exports always represent the saved run, not an unsaved preview.

## Data and administration

SQLite is the source of truth. A fresh installation starts empty. No startup or public endpoint deletes data to seed demonstrations. To load demonstrations explicitly into an **empty** installation:

```powershell
.venv/Scripts/python.exe backend/seed.py
```

Seeded legacy records are initially unowned. Register the recruiter that should own them, then preview and explicitly assign them:

```powershell
.venv/Scripts/python.exe backend/migrate_legacy.py --owner recruiter@example.com
.venv/Scripts/python.exe backend/migrate_legacy.py --owner recruiter@example.com --apply
```

Assignment creates a database backup before changes. The same procedure works for existing unowned records. Create an admin through the terminal; passwords are prompted, not command-line arguments:

```powershell
.venv/Scripts/python.exe backend/create_admin.py admin@example.com
```

The admin's System metrics page shows measured process-local request/token usage and can rebuild the index without replacing source data. The first semantic search downloads the configured embedding model into `backend/data/embedding_cache`. Rankings repair missing or outdated authorized profile vectors. API uploads are limited to 5 MB; PDFs to 30 pages and 100,000 extracted characters; DOCX files to 10 MB expanded content and 100,000 extracted characters; CSV imports to 500 rows. Scanned PDFs without text require OCR outside the current implementation.

## Checks

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/ruff.exe check backend
cd frontend
npm test
npm run build
npx playwright install chromium
$env:PRISM_PYTHON=(Resolve-Path ../.venv/Scripts/python.exe).Path
npm run test:e2e
```

Browser tests launch temporary API/frontend servers and use synthetic data under `work/`. Set `PRISM_PYTHON` to the Python executable containing backend dependencies if it is not the default `python`. `PLAYWRIGHT_CHROME` can point to an existing Chrome binary. The tests do not send messages or call live NVIDIA services.

See `backend/evaluation/README.md` for ranking metrics and a synthetic example. Independent recruiter-reviewed labels and live model/provider validation are still required. See `SECURITY.md` for deployment settings and remaining Chroma dependency advisories.
