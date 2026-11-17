# Prism audit response

This response reconciles the November 17, 2026 resume-readiness audit with the repository state. “Completed earlier” means the capability existed and was verified in this workspace before the audit was received. “Implemented now” means it was added in this change set. “Deferred” is a valid improvement, but needs an explicit product or deployment decision rather than a cosmetic code change.

## Implemented now

| Audit item | Resolution |
| --- | --- |
| Recruiters rank pasted JDs while jobs and applications are separate | `POST /jobs/{job_id}/rank-applicants` ranks only active applicants for that recruiter-owned job, uses the saved description and required skills, and records the job ID in run metadata. The hiring workspace now has a **Rank applicants** action and result summary. |
| Candidates only see coverage, not guidance | Job coverage now returns concrete missing/partial-skill guidance and the candidate workspace displays it. |
| Behavioral score is a weak and potentially unfair proxy | The default weight is now `0`. Activity can only affect a rank through an explicit Availability preset; it is not a hidden default hiring signal. |
| Candidate data portability and deletion are absent | Candidates can download their stored data and permanently delete their account after entering their email. Deletion removes their profile, applications, session records, candidate-specific score/feedback data, and their derived vector when available. |
| Resume uploads do not accept DOCX | Text-based DOCX resumes are now accepted with ZIP/XML, expanded-content and extracted-text limits. |
| Broken favicon | The page now references the committed `logo.jpg`. |
| Inaccurate integrations copy | The UI now identifies FastEmbed/ONNX rather than sentence-transformers and no longer calls predominantly synchronous endpoints “async”. |

## Already completed before this audit

| Audit item | Evidence |
| --- | --- |
| Real authentication, sessions, CSRF and throttling | `backend/auth.py`; security tests cover registration, expired/revoked sessions, CSRF and login throttling. |
| Tenant isolation | `candidate_scope`, `run_scope`, job ownership checks, and security/hiring tests enforce candidate and workspace boundaries. |
| Honest AI failures | `AIUnavailable` maps to an explicit 503 rather than a fabricated result. |
| Evidence-aware skill matching | Skill aliases, token boundaries, evidence discounting and gap reporting are in `backend/scorer/skill_scorer.py`. |
| Additive migrations, atomic saved runs, CI and evaluation utility | `database.init_db`, `ranker.py`, `.github/workflows/checks.yml`, and `backend/evaluate.py`. The evaluation set is deliberately marked synthetic/unreviewed. |
| Hiring pipeline, private notes, interviews, invitations and withdrawal | `backend/hiring.py` and `HiringWorkspace.jsx`. |
| Feedback preserves explanations | `feedback_reranker.py` adds a feedback tag without replacing the original explanation. |
| Accessibility foundation | Dialog focus handling, Escape support, visible focus styles and reduced-motion CSS were added previously. |
| Resume analyzer is real, not a placeholder | It uploads a PDF and only saves a validated parsed profile; unavailable AI reports an error. |

## Deferred with a clear next decision

| Audit item | Why it is deferred |
| --- | --- |
| Human-labeled evaluation, BM25 baseline and ablation study | The code can calculate NDCG/precision/recall, but meaningful labels need consented profiles and independent recruiter relevance judgments. Fabricating those labels would make the portfolio claim less credible. Next: collect about 30 roles by 200 pseudonymous profiles and run the benchmark. |
| Hybrid retrieval / cross-encoder | Valuable after the labeled benchmark establishes a baseline. Adding it first would create complexity without proving better quality. |
| Skills ontology and partial credit | The interface already supports partial status. A taxonomy should be selected and licensed deliberately (for example ESCO) rather than silently inventing skill equivalences. |
| Domain classifier | The current logic uses explicit profile domain first, with career/context fallback. Replacing it should follow evaluation data because a classifier can introduce new errors. |
| Very large candidate-pool scalability | Job-specific ranking now queries an explicit applicant ID set rather than the entire workspace. General discovery still needs a production search architecture once scale requirements and a database choice are agreed. |
| Background ranking, progress and cancellation | This needs a durable worker/queue choice (Redis/Celery, RQ or a managed job platform) and an operating deployment; it is not safely solved with an in-memory background task. |
| Transactional email, password reset and calendar invitations | These require a provider account, verified sending domain and email-retention policy. The code must not pretend email was sent without those credentials. |
| GitHub enrichment | Requires user OAuth, consent, rate-limit policy and a decision on whether public repository activity is an allowable hiring signal. |
| OCR for scanned resumes | DOCX extraction is implemented. OCR still requires a quality/privacy decision and image/PDF processing infrastructure, so scanned PDFs remain explicitly unsupported. |
| Thousands of synthetic demo candidates | Useful only for a scale demonstration. It should live in a separate demo generator and never be mixed with candidate data or presented as production evidence. |
| React Router, TanStack Query, TypeScript, ESLint/Prettier and component tests | These are sound maintainability upgrades, but are a frontend migration rather than a one-line bug fix. They should be a focused follow-up to avoid destabilizing the working app. |
| Screenshots, architecture diagram, live demo and Docker | Documentation/screenshots and a runbook already exist. A live demo and Docker image require deployment/secrets decisions and should be added together in a release-focused change. |
| Deleting legacy/hackathon modules and columns | Keep compatibility code until import/migration users are accounted for. Removal should be a separately reviewed breaking-change cleanup, not an untracked deletion. |

## Intentionally not adopted as stated

* Moving immediately from SQLite to Postgres plus SQLAlchemy/Alembic is not required for a local/demo deployment. It is the correct next architecture at multi-user production scale, but an unnecessary rewrite before the product and hosting requirements are fixed.
* Passing the authenticated actor through every database call instead of `ContextVar` is a readability trade-off, not a demonstrated authorization defect. Existing isolation tests cover the current boundary.
* “Sub-100ms across the entire pool” should not be claimed without a measured hardware/dataset benchmark. The integration copy now avoids that unsupported promise.
* A one-click seeded demo login should not be added to a deployment that can contain real data. It belongs only in a separately isolated demo environment.

## Recommended next sequence

1. Create a consented, pseudonymous relevance-labeling set and add BM25/NDCG/ablation reporting.
2. Make the API work asynchronous using a durable job queue and expose honest progress/cancel states.
3. Choose a production deployment boundary: PostgreSQL, object storage, email provider, container image and a distinct demo environment.
4. Migrate the frontend feature by feature to routes, server-state caching, formatting/linting and component tests.
