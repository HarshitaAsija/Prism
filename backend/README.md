# Backend

Run and test this service using the instructions in the repository root README.

The API uses FastAPI, SQLite, local FastEmbed embeddings and embedded Chroma storage. Accounts, jobs, applications and profile updates work without NVIDIA credentials. AI endpoints require a configured provider key and return explicit availability errors. Never run a separate publicly accessible Chroma server for this deployment.

- `auth.py`: server-side accounts, password hashing, sessions and role dependencies.
- `database.py`: additive migrations, source records and workspace scoping.
- `hiring.py`: job/application pipeline, interview scheduling, notes and team access.
- `ranker.py`: authorized retrieval, scoring, optional explanations and atomic persistence.
- `main.py`: API validation, upload bounds, metrics and endpoint wiring.
- `tests/`: isolated security, workflow, scorer, AI failure, evaluation and real vector-store tests.

`python test_backend.py` runs the isolated test suite; it no longer inserts fixtures into the live database or calls NVIDIA.
