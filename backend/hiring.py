"""Job posting, applications, recruiter stages, internal notes and interview scheduling."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from auth import current_user, recruiter
from database import get_conn, get_candidate

router = APIRouter(tags=["hiring"])
SCHEMA = """
CREATE TABLE IF NOT EXISTS team_invites(token_hash TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, email TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, title TEXT NOT NULL, company TEXT NOT NULL,
 description TEXT NOT NULL, location TEXT NOT NULL, required_skills TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'open', created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS applications(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL, candidate_id TEXT NOT NULL, applicant_id TEXT NOT NULL,
 stage TEXT NOT NULL DEFAULT 'applied', cover_note TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')),
 updated_at TEXT DEFAULT (datetime('now')), UNIQUE(job_id,candidate_id)
);
CREATE TABLE IF NOT EXISTS application_notes(
 id TEXT PRIMARY KEY, application_id TEXT NOT NULL, author_id TEXT NOT NULL, body TEXT NOT NULL,
 created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS interviews(
 id TEXT PRIMARY KEY, application_id TEXT NOT NULL, scheduled_at TEXT NOT NULL,
 meeting_url TEXT NOT NULL, created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS application_events(
 id INTEGER PRIMARY KEY, application_id TEXT NOT NULL, actor_id TEXT NOT NULL, stage TEXT NOT NULL,
 created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_owner ON jobs(owner_id);
CREATE INDEX IF NOT EXISTS idx_notes_application ON application_notes(application_id);
CREATE INDEX IF NOT EXISTS idx_interviews_application ON interviews(application_id);
CREATE INDEX IF NOT EXISTS idx_applications_applicant ON applications(applicant_id);
CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
"""


class JobInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    company: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=50, max_length=30000)
    location: str = Field(min_length=1, max_length=200)
    required_skills: list[str] = Field(min_length=1, max_length=30)


class ApplyInput(BaseModel):
    cover_note: str = Field(default="", max_length=2000)


class StageInput(BaseModel):
    stage: str = Field(pattern="^(screened|interview|offer|hired|rejected)$")


class NoteInput(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class InterviewInput(BaseModel):
    scheduled_at: datetime
    meeting_url: str = Field(pattern=r"^https://[^\s]+$", max_length=1000)


def job_record(row):
    job = dict(row)
    job["required_skills"] = json.loads(job["required_skills"])
    return job


def owned_job(job_id, user, conn):
    job = conn.execute(
        "SELECT * FROM jobs WHERE id=? AND owner_id=?", (job_id, user["workspace_id"])
    ).fetchone()
    if not job:
        raise HTTPException(404, "Job not found.")
    return dict(job)


def application_record(application_id, user, conn):
    row = conn.execute(
        "SELECT a.*,j.owner_id,j.title,j.company FROM applications a JOIN jobs j ON j.id=a.job_id WHERE a.id=?",
        (application_id,),
    ).fetchone()
    if not row or (
        user["workspace_id"] != row["owner_id"] and user["username"] != row["applicant_id"]
    ):
        raise HTTPException(404, "Application not found.")
    return dict(row)


def event(conn, application_id, user, stage):
    conn.execute(
        "INSERT INTO application_events(application_id,actor_id,stage) VALUES(?,?,?)",
        (application_id, user["username"], stage),
    )


@router.get("/jobs")
def jobs(
    mine: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
):
    with get_conn() as conn:
        if mine:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user["workspace_id"], limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status='open' ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return {"jobs": [job_record(row) for row in rows]}


@router.post("/jobs", status_code=201)
def create_job(body: JobInput, user=Depends(recruiter)):
    job_id = uuid.uuid4().hex
    skills = list(dict.fromkeys(s.strip() for s in body.required_skills if s.strip()))
    if not skills or not body.title.strip() or not body.company.strip():
        raise HTTPException(422, "Title, company and skills cannot be blank.")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs(id,owner_id,title,company,description,location,required_skills) VALUES(?,?,?,?,?,?,?)",
            (
                job_id,
                user["workspace_id"],
                body.title.strip(),
                body.company.strip(),
                body.description,
                body.location,
                json.dumps(skills),
            ),
        )
    return {"id": job_id}


@router.patch("/jobs/{job_id}")
def close_job(job_id: str, user=Depends(recruiter)):
    with get_conn() as conn:
        owned_job(job_id, user, conn)
        conn.execute("UPDATE jobs SET status='closed' WHERE id=?", (job_id,))
    return {"status": "closed"}


@router.post("/jobs/{job_id}/apply", status_code=201)
def apply(job_id: str, body: ApplyInput, user=Depends(current_user)):
    if user["role"] != "candidate":
        raise HTTPException(403, "Candidate account required.")
    with get_conn() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=? AND status='open'", (job_id,)).fetchone()
        if not job:
            raise HTTPException(404, "Open job not found.")
        profile = conn.execute(
            "SELECT * FROM candidates WHERE id=? AND owner_id=?",
            (user["candidate_id"], user["username"]),
        ).fetchone()
        if not profile or not profile["current_title"] or not json.loads(profile["skills"] or "[]"):
            raise HTTPException(
                422, "Add a professional title and skills to your profile before applying."
            )
        previous = conn.execute(
            "SELECT id FROM applications WHERE job_id=? AND candidate_id=?",
            (job_id, user["candidate_id"]),
        ).fetchone()
        if previous:
            raise HTTPException(409, "You have already applied to this job.")
        application_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO applications(id,job_id,candidate_id,applicant_id,cover_note) VALUES(?,?,?,?,?)",
            (application_id, job_id, user["candidate_id"], user["username"], body.cover_note),
        )
        event(conn, application_id, user, "applied")
    return {"id": application_id, "stage": "applied"}


@router.get("/applications")
def applications(
    job_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(current_user),
):
    with get_conn() as conn:
        field = "a.applicant_id" if user["role"] == "candidate" else "j.owner_id"
        where = field + "=?"
        params = [user["username"] if user["role"] == "candidate" else user["workspace_id"]]
        if job_id:
            where += " AND a.job_id=?"
            params.append(job_id)
        rows = conn.execute(
            "SELECT a.*,j.title,j.company,c.name,c.current_title,c.skills FROM applications a JOIN jobs j ON a.job_id=j.id JOIN candidates c ON a.candidate_id=c.id WHERE "
            + where
            + " ORDER BY a.updated_at DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["skills"] = json.loads(item["skills"] or "[]")
            item["interviews"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM interviews WHERE application_id=? ORDER BY scheduled_at",
                    (item["id"],),
                )
            ]
            item["events"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT stage,created_at FROM application_events WHERE application_id=? ORDER BY id",
                    (item["id"],),
                )
            ]
            if user["role"] != "candidate":
                item["notes"] = [
                    dict(r)
                    for r in conn.execute(
                        "SELECT * FROM application_notes WHERE application_id=? ORDER BY created_at",
                        (item["id"],),
                    )
                ]
            results.append(item)
    return {"applications": results}


@router.patch("/applications/{application_id}")
def update_stage(application_id: str, body: StageInput, user=Depends(recruiter)):
    with get_conn() as conn:
        item = application_record(application_id, user, conn)
        if item["owner_id"] != user["workspace_id"]:
            raise HTTPException(403, "Only the hiring team can change stages.")
        allowed = {
            "applied": {"screened", "rejected"},
            "screened": {"interview", "rejected"},
            "interview": {"offer", "rejected"},
            "offer": {"hired", "rejected"},
        }
        if body.stage not in allowed.get(item["stage"], set()):
            raise HTTPException(409, "Invalid stage transition.")
        conn.execute(
            "UPDATE applications SET stage=?,updated_at=datetime('now') WHERE id=?",
            (body.stage, application_id),
        )
        event(conn, application_id, user, body.stage)
    return {"stage": body.stage}


@router.post("/applications/{application_id}/withdraw")
def withdraw(application_id: str, user=Depends(current_user)):
    with get_conn() as conn:
        item = application_record(application_id, user, conn)
        if item["applicant_id"] != user["username"]:
            raise HTTPException(403, "Only the applicant can withdraw.")
        if item["stage"] in {"hired", "rejected", "withdrawn"}:
            raise HTTPException(409, "This application is already closed.")
        conn.execute(
            "UPDATE applications SET stage='withdrawn',updated_at=datetime('now') WHERE id=?",
            (application_id,),
        )
        event(conn, application_id, user, "withdrawn")
    return {"stage": "withdrawn"}


@router.post("/applications/{application_id}/notes", status_code=201)
def note(application_id: str, body: NoteInput, user=Depends(recruiter)):
    with get_conn() as conn:
        item = application_record(application_id, user, conn)
        if item["owner_id"] != user["workspace_id"]:
            raise HTTPException(403, "Hiring team access required.")
        if not body.body.strip():
            raise HTTPException(422, "Note cannot be blank.")
        conn.execute(
            "INSERT INTO application_notes(id,application_id,author_id,body) VALUES(?,?,?,?)",
            (uuid.uuid4().hex, application_id, user["username"], body.body.strip()),
        )
    return {"status": "saved"}


@router.post("/applications/{application_id}/interviews", status_code=201)
def interview(application_id: str, body: InterviewInput, user=Depends(recruiter)):
    when = body.scheduled_at
    if when.tzinfo is None or when <= datetime.now(timezone.utc):
        raise HTTPException(422, "Choose a future time including a timezone.")
    with get_conn() as conn:
        item = application_record(application_id, user, conn)
        if item["owner_id"] != user["workspace_id"]:
            raise HTTPException(403, "Hiring team access required.")
        if item["stage"] not in {"screened", "interview"}:
            raise HTTPException(409, "Screen this applicant before scheduling an interview.")
        conn.execute(
            "INSERT INTO interviews(id,application_id,scheduled_at,meeting_url) VALUES(?,?,?,?)",
            (
                uuid.uuid4().hex,
                application_id,
                when.astimezone(timezone.utc).isoformat(),
                body.meeting_url,
            ),
        )
        if item["stage"] != "interview":
            conn.execute(
                "UPDATE applications SET stage='interview',updated_at=datetime('now') WHERE id=?",
                (application_id,),
            )
            event(conn, application_id, user, "interview")
    return {"status": "scheduled"}


@router.get("/jobs/{job_id}/match")
def match(job_id: str, user=Depends(current_user)):
    if user["role"] != "candidate":
        raise HTTPException(403, "Candidate account required.")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND status='open'", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Open job not found.")
    from scorer.skill_scorer import skill_score

    job = job_record(row)
    score, gaps = skill_score(
        get_candidate(user["candidate_id"]), {"required_skills": job["required_skills"]}
    )
    missing = [gap["skill"] for gap in gaps if gap["status"] == "missing"]
    partial = [gap["skill"] for gap in gaps if gap["status"] == "partial"]
    suggestions = []
    if missing:
        suggestions.append("Add evidence for: " + ", ".join(missing[:5]))
    if partial:
        suggestions.append("Strengthen project or role evidence for: " + ", ".join(partial[:5]))
    if not suggestions:
        suggestions.append("Your profile covers the listed skills. Add measurable outcomes to make that evidence easier to review.")
    return {
        "score": round(score * 100, 2),
        "skill_gap": gaps,
        "suggestions": suggestions,
        "method": "Required skill coverage with resume evidence. This is not a hiring probability.",
    }


@router.post("/jobs/{job_id}/rank-applicants")
async def rank_applicants(job_id: str, user=Depends(recruiter)):
    """Rank only the current workspace's applicants against their actual job."""
    with get_conn() as conn:
        job = owned_job(job_id, user, conn)
        applicants = conn.execute(
            "SELECT candidate_id FROM applications WHERE job_id=? AND stage!='withdrawn'",
            (job_id,),
        ).fetchall()
    candidate_ids = [row["candidate_id"] for row in applicants]
    if not candidate_ids:
        return {"job_id": job_id, "results": [], "message": "No active applicants to rank."}

    from ranker import rank_candidates

    required_skills = json.loads(job["required_skills"])
    parsed_job = {
        "job_title": job["title"],
        "seniority_level": "mid",
        "domain": "general",
        "required_skills": required_skills,
        "preferred_skills": [],
        "years_experience_min": 0,
        "years_experience_max": 20,
        "key_responsibilities": [],
        "deal_breakers": [],
        "soft_skills": [],
        "education_requirement": "any",
        "remote_friendly": None,
        "suggested_weight_bias": "balanced",
        "domain_keywords": required_skills,
    }
    result = await rank_candidates(
        job["description"] + "\nRequired skills: " + ", ".join(required_skills),
        top_n=len(candidate_ids),
        candidate_ids=candidate_ids,
        parsed_jd=parsed_job,
        pipeline_metadata={"job_id": job_id, "mode": "applicant_ranking"},
    )
    return {**result, "job_id": job_id, "message": "Ranked active applicants for this job."}


class InviteInput(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=254)


class JoinInput(BaseModel):
    token: str = Field(min_length=32, max_length=200)


@router.get("/team")
def team(user=Depends(recruiter)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT username,name FROM auth_users WHERE role='recruiter' AND (workspace_id=? OR (workspace_id IS NULL AND username=?))",
            (user["workspace_id"], user["workspace_id"]),
        ).fetchall()
    return {"workspace_id": user["workspace_id"], "members": [dict(r) for r in rows]}


@router.post("/team/invites", status_code=201)
def invite(body: InviteInput, user=Depends(recruiter)):
    import secrets, hashlib, time
    from auth import limit_requests

    if user["username"] != user["workspace_id"]:
        raise HTTPException(403, "Only the workspace owner can invite members.")
    limit_requests("invite:" + user["username"], 10)
    token = secrets.token_urlsafe(36)
    with get_conn() as conn:
        conn.execute("DELETE FROM team_invites WHERE expires_at<=?", (time.time(),))
        conn.execute(
            "INSERT INTO team_invites(token_hash,workspace_id,email,expires_at) VALUES(?,?,?,?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                user["workspace_id"],
                body.email.lower().strip(),
                time.time() + 604800,
            ),
        )
    return {"token": token, "expires_in_days": 7, "email": body.email.lower().strip()}


@router.post("/team/join")
def join(body: JoinInput, user=Depends(recruiter)):
    import hashlib, time

    with get_conn() as conn:
        invitation = conn.execute(
            "SELECT * FROM team_invites WHERE token_hash=? AND email=? AND expires_at>?",
            (hashlib.sha256(body.token.encode()).hexdigest(), user["username"], time.time()),
        ).fetchone()
        if not invitation:
            raise HTTPException(404, "Invitation is invalid or expired.")
        if user["workspace_id"] != user["username"]:
            raise HTTPException(409, "This account already belongs to a team.")
        for table in ("candidates", "jd_runs", "jobs"):
            if conn.execute(
                f"SELECT 1 FROM {table} WHERE owner_id=? LIMIT 1", (user["username"],)
            ).fetchone():
                raise HTTPException(
                    409, "Join with a recruiter account whose personal workspace has no data."
                )
        conn.execute(
            "UPDATE auth_users SET workspace_id=? WHERE username=?",
            (invitation["workspace_id"], user["username"]),
        )
        conn.execute("DELETE FROM team_invites WHERE token_hash=?", (invitation["token_hash"],))
    return {"workspace_id": invitation["workspace_id"]}


@router.delete("/team/members/{email}")
def remove_member(email: str, user=Depends(recruiter)):
    if user["username"] != user["workspace_id"]:
        raise HTTPException(403, "Only the workspace owner can remove members.")
    email = email.lower().strip()
    if email == user["workspace_id"]:
        raise HTTPException(409, "The workspace owner cannot be removed.")
    with get_conn() as conn:
        changed = conn.execute(
            "UPDATE auth_users SET workspace_id=NULL WHERE username=? AND workspace_id=?",
            (email, user["workspace_id"]),
        ).rowcount
        if not changed:
            raise HTTPException(404, "Team member not found.")
        conn.execute("DELETE FROM auth_sessions WHERE username=?", (email,))
    return {"status": "removed"}
