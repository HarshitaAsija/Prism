"""Authenticated Prism API. Run: uvicorn main:app --reload --port 8000."""

import csv
import io
import os
import tempfile
import uuid
from typing import Optional
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import database as db
from auth import router as auth_router, current_user, recruiter, admin, limit_requests
from config import CORS_ORIGINS, DEFAULT_WEIGHTS
from models import RankRequest, FeedbackRequest

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app):
    startup()
    yield


app = FastAPI(title="Prism Hiring API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Content-Type", "X-Prism-Client"],
)
app.include_router(auth_router)
from hiring import router as hiring_router

app.include_router(hiring_router)


def startup():
    # Never seed or download models during startup.
    db.init_db()


@app.exception_handler(ValueError)
async def invalid_input(request, error):
    return JSONResponse(status_code=422, content={"detail": str(error)})


from llm_client import AIUnavailable


@app.exception_handler(AIUnavailable)
async def ai_unavailable(request, error):
    return JSONResponse(status_code=503, content={"detail": str(error), "status": "unavailable"})


@app.get("/health")
def health():
    return {"status": "ok", "model": "NVIDIA NIM", "embedding_model": "all-MiniLM-L6-v2"}


def own_run(run_id):
    run = db.get_jd_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found.")
    return run


def candidate_or_404(candidate_id, user, edit=False):
    candidate = db.get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found.")
    if (
        edit
        and user["role"] != "admin"
        and candidate.get("owner_id")
        != (user["username"] if user["role"] == "candidate" else user["workspace_id"])
    ):
        raise HTTPException(403, "You can only edit profiles you own.")
    return candidate


class CandidateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    title: Optional[str] = Field(None, max_length=200)
    experienceYears: Optional[float] = Field(None, ge=0, le=80)
    skills: Optional[list[str]] = Field(None, max_length=100)
    github: Optional[str] = Field(None, max_length=500)
    linkedin: Optional[str] = Field(None, max_length=500)
    certifications: Optional[list[str]] = Field(None, max_length=50)
    visibility: Optional[str] = Field(None, pattern="^(private|public)$")


@app.get("/me/profile")
def my_profile(user=Depends(current_user)):
    if user["role"] != "candidate":
        raise HTTPException(403, "Candidate account required.")
    return candidate_or_404(user["candidate_id"], user)


# Static routes precede the dynamic candidate ID route.
@app.get("/candidates/search")
def search_candidates(
    q: str = Query(min_length=2, max_length=1000),
    limit: int = Query(50, ge=1, le=100),
    user=Depends(recruiter),
):
    from embedder import embed_text
    from vector_store import search

    ids = [c["id"] for c in db.get_all_candidates(limit=100000)]
    return [
        dict(db.get_candidate(r["candidate_id"]), similarity_score=r["similarity"])
        for r in search(embed_text(q), top_n=limit, candidate_ids=ids)
    ]


@app.get("/candidates")
def candidates(
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), user=Depends(recruiter)
):
    return {
        "total": db.count_candidates(),
        "limit": limit,
        "offset": offset,
        "candidates": db.get_all_candidates(limit, offset),
    }


@app.get("/candidates/{candidate_id}")
def candidate(candidate_id: str, user=Depends(current_user)):
    return candidate_or_404(candidate_id, user)


@app.put("/candidates/{candidate_id}")
def update_candidate(candidate_id: str, body: CandidateUpdate, user=Depends(current_user)):
    from utils import estimate_completeness

    candidate = candidate_or_404(candidate_id, user, edit=True)
    fields = body.model_dump(exclude_none=True)
    for field in ("github", "linkedin"):
        if fields.get(field) and not fields[field].startswith("https://"):
            raise HTTPException(422, "Profile links must use HTTPS.")
    fields = {
        {"title": "current_title", "experienceYears": "years_experience"}.get(k, k): v
        for k, v in fields.items()
    }
    candidate.update(fields)
    candidate["profile_completeness"] = estimate_completeness(candidate)
    db.upsert_candidate(candidate)
    with db.get_conn() as conn:
        conn.execute("UPDATE candidates SET index_status='pending' WHERE id=?", (candidate_id,))
    return {"status": "success", "candidate": candidate}


@app.post("/rank")
async def rank(body: RankRequest, user=Depends(recruiter)):
    from ranker import rank_candidates

    if body.previous_run_id:
        own_run(body.previous_run_id)
    limit_requests("rank:" + user["username"], 10)
    return await rank_candidates(
        body.jd_text,
        body.weights.model_dump() if body.weights else DEFAULT_WEIGHTS,
        str(uuid.uuid4()),
        body.previous_run_id,
        top_n=body.top_n,
    )


@app.get("/runs")
def runs(limit: int = Query(50, ge=1, le=200), user=Depends(recruiter)):
    rows = db.list_jd_runs(limit)
    return {"total": len(rows), "runs": rows}


@app.get("/runs/{run_id}")
def run(run_id: str, user=Depends(recruiter)):
    return own_run(run_id)


@app.get("/runs/{run_id}/results")
def results(run_id: str, user=Depends(recruiter)):
    own_run(run_id)
    return {"run_id": run_id, "results": db.get_ranked_results(run_id)}


@app.delete("/runs")
def clear_runs(user=Depends(recruiter)):
    db.clear_all_runs()
    return {"status": "success"}


@app.post("/feedback")
def feedback(body: FeedbackRequest, user=Depends(recruiter)):
    own_run(body.run_id)
    db.save_feedback(body.run_id, body.candidate_id, body.feedback_type, body.notes or "")
    return {"status": "saved", "feedback_type": body.feedback_type}


@app.post("/runs/{run_id}/rerank")
async def rerank(run_id: str, user=Depends(recruiter)):
    from feedback_reranker import apply_feedback_boost

    own_run(run_id)
    adjusted = await run_in_threadpool(
        apply_feedback_boost, db.get_ranked_results(run_id), run_id, db.get_feedback_map(run_id)
    )
    return {"run_id": run_id, "results": adjusted, "preview": True}


@app.get("/export/{run_id}")
def export(run_id: str, user=Depends(recruiter)):
    own_run(run_id)
    fields = [
        "rank",
        "candidate_id",
        "name",
        "current_title",
        "current_company",
        "composite_score",
        "semantic_score",
        "skill_score",
        "trajectory_score",
        "behavioral_score",
        "domain_score",
        "explanation",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in db.get_ranked_results(run_id):
        writer.writerow(
            {
                k: (
                    "'" + str(row[k])
                    if isinstance(row.get(k), str)
                    and row[k].lstrip().startswith(("=", "+", "-", "@"))
                    else row.get(k, "")
                )
                for k in fields
            }
        )
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="prism_{run_id[:8]}.csv"'},
    )


@app.get("/stats")
def stats(user=Depends(recruiter)):
    candidates = db.get_all_candidates(limit=100000)
    return {
        "total_candidates": len(candidates),
        "vectors_indexed": sum(c.get("index_status") == "ready" for c in candidates),
    }


@app.get("/analytics")
def analytics(user=Depends(recruiter)):
    return db.get_analytics()


MAX_UPLOAD = 5 * 1024 * 1024


async def read_upload(file):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Upload must be 5 MB or smaller.")
    return data


def pdf_text(data):
    import pypdf

    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "File is not a valid PDF.")
    try:
        reader = pypdf.PdfReader(io.BytesIO(data))
        if len(reader.pages) > 30:
            raise HTTPException(422, "PDF must have at most 30 pages.")
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Unable to read this PDF.")
    if not text.strip():
        raise HTTPException(422, "PDF contains no extractable text.")
    if len(text) > 100000:
        raise HTTPException(422, "PDF text exceeds 100,000 characters.")
    return text


@app.post("/candidates/upload")
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    limit_requests("upload:" + user["username"], 10)
    filename = (file.filename or "").lower()
    if not filename.endswith((".pdf", ".csv")):
        raise HTTPException(422, "Upload a PDF resume or CSV candidate file.")
    data = await read_upload(file)
    if filename.endswith(".csv"):
        if user["role"] not in {"recruiter", "admin"}:
            raise HTTPException(403, "Only recruiters can bulk import candidates.")
        from data_ingest import ingest

        try:
            rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        except (UnicodeError, csv.Error):
            raise HTTPException(422, "Invalid UTF-8 CSV.")
        if not rows or len(rows) > 500:
            raise HTTPException(422, "CSV must contain between 1 and 500 candidates.")
        for row in rows:
            for key in ("id", "ID", "candidate_id", "owner_id", "visibility"):
                row.pop(key, None)
            row["candidate_id"] = "cand_" + uuid.uuid4().hex
        handle, path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(handle, "w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=list(dict.fromkeys(k for row in rows for k in row))
                )
                writer.writeheader()
                writer.writerows(rows)
            before = db.count_candidates()
            await run_in_threadpool(ingest, path)
            return {
                "status": "success",
                "type": "csv",
                "added_count": db.count_candidates() - before,
                "total_count": db.count_candidates(),
            }
        finally:
            os.unlink(path)
    from resume_parser import parse_resume_text

    text = await run_in_threadpool(pdf_text, data)
    parsed = await run_in_threadpool(parse_resume_text, text)
    if user["role"] == "candidate":
        existing = candidate_or_404(user["candidate_id"], user, edit=True)
        parsed = {
            **existing,
            **parsed,
            "id": existing["id"],
            "owner_id": user["username"],
            "visibility": existing["visibility"],
        }
    else:
        parsed["id"] = "cand_" + uuid.uuid4().hex
        parsed["owner_id"] = user["workspace_id"]
    from utils import estimate_completeness

    parsed["profile_completeness"] = estimate_completeness(parsed)
    db.upsert_candidate(parsed)
    with db.get_conn() as conn:
        conn.execute("UPDATE candidates SET index_status='pending' WHERE id=?", (parsed["id"],))
    return {"status": "success", "type": "pdf", "candidate": parsed}


class JDInput(BaseModel):
    jd_text: str = Field(min_length=50, max_length=30000)


@app.post("/jd/analyze")
def analyze(body: JDInput, user=Depends(recruiter)):
    from jd_parser import parse_jd

    limit_requests("ai:" + user["username"], 20)
    return parse_jd(body.jd_text)


@app.post("/jd/analyze/file")
async def analyze_file(file: UploadFile = File(...), user=Depends(recruiter)):
    from jd_parser import parse_jd

    limit_requests("ai:" + user["username"], 20)
    text = await run_in_threadpool(pdf_text, await read_upload(file))
    return {**await run_in_threadpool(parse_jd, text), "jd_text": text}


@app.post("/jd/bias-scan")
def bias_scan(body: JDInput, user=Depends(recruiter)):
    from jd_parser import scan_jd_bias

    limit_requests("ai:" + user["username"], 20)
    return scan_jd_bias(body.jd_text)


class InterviewInput(BaseModel):
    parsed_jd: dict


@app.post("/candidates/{candidate_id}/interview-questions")
async def interview(candidate_id: str, body: InterviewInput, user=Depends(recruiter)):
    from explainer import generate_interview_questions

    limit_requests("ai:" + user["username"], 20)
    return {
        "questions": await generate_interview_questions(
            candidate_or_404(candidate_id, user), body.parsed_jd
        )
    }


import time
from collections import deque
from threading import Lock

_timings = deque(maxlen=1000)
_metrics_lock = Lock()


@app.middleware("http")
async def observe_requests(request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        with _metrics_lock:
            _timings.append(
                {"duration_ms": round((time.perf_counter() - started) * 1000, 2), "status": status}
            )


@app.get("/admin/metrics")
def metrics(user=Depends(admin)):
    from llm_client import get_token_usage
    from config import NVIDIA_API_KEY

    with _metrics_lock:
        timings = list(_timings)
    return {
        "requests_observed": len(timings),
        "failed_requests": sum(t["status"] >= 500 for t in timings),
        "average_duration_ms": round(sum(t["duration_ms"] for t in timings) / len(timings), 2)
        if timings
        else None,
        "token_usage": get_token_usage(),
        "ai_configured": bool(NVIDIA_API_KEY),
        "candidates": db.count_candidates(),
        "scope": "This server process; latest 1,000 requests",
    }


@app.post("/admin/reindex")
def reindex(user=Depends(admin)):
    from data_ingest import rebuild_index

    return {"indexed": rebuild_index()}
