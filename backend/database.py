"""
database.py — SQLite persistence with additive migrations and workspace scoping.
Single file. All DB logic lives here.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import DB_PATH
from contextvars import ContextVar

# Set by the API dependency; propagated into worker threads. CLI tools have no scope.
actor_context = ContextVar("actor", default=None)


def candidate_scope(alias=""):
    actor = actor_context.get()
    prefix = alias + "." if alias else ""
    if actor is None or actor["role"] == "admin":
        return "1=1", []
    if actor["role"] == "candidate":
        return prefix + "owner_id=?", [actor["username"]]
    return (
        f"({prefix}owner_id=? OR {prefix}visibility='public' OR {prefix}id IN (SELECT a.candidate_id FROM applications a JOIN jobs j ON j.id=a.job_id WHERE j.owner_id=? AND a.stage!='withdrawn'))",
        [
            actor.get("workspace_id", actor["username"]),
            actor.get("workspace_id", actor["username"]),
        ],
    )


def run_scope():
    actor = actor_context.get()
    if actor is None or actor["role"] == "admin":
        return "1=1", []
    return "owner_id=?", [actor.get("workspace_id", actor["username"])]


import os

os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)


# ── Schema DDL ────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS candidates (
    id                  TEXT PRIMARY KEY,
    name                TEXT,
    email               TEXT,
    phone               TEXT,
    location            TEXT,
    current_title       TEXT,
    current_company     TEXT,
    years_experience    REAL DEFAULT 0,
    skills              TEXT,          -- JSON list
    career_history      TEXT,          -- JSON list
    education           TEXT,          -- JSON list
    domain              TEXT,
    last_active         TEXT,          -- ISO date string
    profile_completeness REAL DEFAULT 0,
    activity_score      REAL DEFAULT 0,
    raw_data            TEXT,          -- full original row as JSON
    headline            TEXT,
    summary             TEXT,
    country             TEXT,
    current_company_size TEXT,
    current_industry    TEXT,
    certifications      TEXT,          -- JSON list
    languages           TEXT,          -- JSON list
    redrob_signals      TEXT,          -- JSON dict
    intent_score        REAL DEFAULT 0,
    hidden_gem_score    REAL DEFAULT 0,
    max_promotion_velocity REAL DEFAULT 0,
    avg_time_in_role_months REAL DEFAULT 0,
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auth_users (
    username            TEXT PRIMARY KEY,
    password            TEXT NOT NULL,
    role                TEXT NOT NULL, -- 'recruiter' | 'candidate' | 'admin'
    created_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jd_runs (
    run_id          TEXT PRIMARY KEY,
    jd_text         TEXT NOT NULL,
    jd_parsed       TEXT,             -- JSON: structured extraction
    weights         TEXT,             -- JSON: weight dict used
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS candidate_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
    semantic_score  REAL DEFAULT 0,
    skill_score     REAL DEFAULT 0,
    trajectory_score REAL DEFAULT 0,
    behavioral_score REAL DEFAULT 0,
    domain_score    REAL DEFAULT 0,
    composite_score REAL DEFAULT 0,
    rank_position   INTEGER DEFAULT 0,
    explanation     TEXT,
    outreach_msg    TEXT,
    skill_gap       TEXT,             -- JSON
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    candidate_id    TEXT NOT NULL,
    feedback_type   TEXT,             -- 'not_a_fit' | 'strong_yes' | 'maybe'
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_scores_run   ON candidate_scores(run_id);
CREATE INDEX IF NOT EXISTS idx_scores_cand  ON candidate_scores(candidate_id);
CREATE INDEX IF NOT EXISTS idx_feedback_run ON feedback(run_id);
"""


@contextmanager
def get_conn():
    """Context manager — always closes connection cleanly."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL")  # safe concurrent reads
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables on first run."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        from hiring import SCHEMA as HIRING_SCHEMA

        conn.executescript(HIRING_SCHEMA)
        # Additive, idempotent migrations preserve existing installations.
        migrations = {
            "auth_users": {
                "name": "TEXT NOT NULL DEFAULT ''",
                "candidate_id": "TEXT",
                "workspace_id": "TEXT",
            },
            "candidates": {
                "owner_id": "TEXT",
                "visibility": "TEXT NOT NULL DEFAULT 'private'",
                "github": "TEXT DEFAULT ''",
                "linkedin": "TEXT DEFAULT ''",
                "index_status": "TEXT DEFAULT 'pending'",
            },
            "candidate_scores": {"profile_snapshot": "TEXT"},
            "jd_runs": {
                "pipeline_metadata": "TEXT",
                "owner_id": "TEXT",
                "status": "TEXT DEFAULT 'complete'",
                "error": "TEXT",
            },
        }
        for table, columns in migrations.items():
            existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            for column, ddl in columns.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS request_limits(key TEXT, bucket INTEGER, count INTEGER, PRIMARY KEY(key,bucket));
            CREATE INDEX IF NOT EXISTS idx_candidates_owner ON candidates(owner_id);
            CREATE INDEX IF NOT EXISTS idx_runs_owner ON jd_runs(owner_id);
        """)
    print(f"[DB] Initialised at {DB_PATH}")


# ── Candidate operations ───────────────────────────────────────────────────────


def upsert_candidate(candidate: Dict[str, Any]):
    """Insert or replace a candidate record."""
    sql = """
        INSERT INTO candidates (
            id, name, email, phone, location,
            current_title, current_company, years_experience,
            skills, career_history, education, domain,
            last_active, profile_completeness, activity_score, raw_data,
            headline, summary, country, current_company_size, current_industry,
            certifications, languages, redrob_signals,
            intent_score, hidden_gem_score, max_promotion_velocity, avg_time_in_role_months
        ) VALUES (
            :id, :name, :email, :phone, :location,
            :current_title, :current_company, :years_experience,
            :skills, :career_history, :education, :domain,
            :last_active, :profile_completeness, :activity_score, :raw_data,
            :headline, :summary, :country, :current_company_size, :current_industry,
            :certifications, :languages, :redrob_signals,
            :intent_score, :hidden_gem_score, :max_promotion_velocity, :avg_time_in_role_months
        )
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            email=excluded.email,
            phone=excluded.phone,
            domain=excluded.domain,
            current_title=excluded.current_title,
            current_company=excluded.current_company,
            skills=excluded.skills,
            career_history=excluded.career_history,
            education=excluded.education,
            location=excluded.location,
            years_experience=excluded.years_experience,
            last_active=excluded.last_active,
            profile_completeness=excluded.profile_completeness,
            activity_score=excluded.activity_score,
            raw_data=excluded.raw_data,
            headline=excluded.headline,
            summary=excluded.summary,
            country=excluded.country,
            current_company_size=excluded.current_company_size,
            current_industry=excluded.current_industry,
            certifications=excluded.certifications,
            languages=excluded.languages,
            redrob_signals=excluded.redrob_signals,
            intent_score=excluded.intent_score,
            hidden_gem_score=excluded.hidden_gem_score,
            max_promotion_velocity=excluded.max_promotion_velocity,
            avg_time_in_role_months=excluded.avg_time_in_role_months
    """
    row = {
        "id": candidate.get("id"),
        "name": candidate.get("name"),
        "email": candidate.get("email"),
        "phone": candidate.get("phone"),
        "location": candidate.get("location"),
        "current_title": candidate.get("current_title"),
        "current_company": candidate.get("current_company"),
        "years_experience": candidate.get("years_experience"),
        "skills": candidate.get("skills"),
        "career_history": candidate.get("career_history"),
        "education": candidate.get("education"),
        "domain": candidate.get("domain"),
        "last_active": candidate.get("last_active"),
        "profile_completeness": candidate.get("profile_completeness"),
        "activity_score": candidate.get("activity_score"),
        "raw_data": candidate.get("raw_data"),
        "headline": candidate.get("headline", ""),
        "summary": candidate.get("summary", ""),
        "country": candidate.get("country", ""),
        "current_company_size": candidate.get("current_company_size", ""),
        "current_industry": candidate.get("current_industry", ""),
        "certifications": candidate.get("certifications", []),
        "languages": candidate.get("languages", []),
        "redrob_signals": candidate.get("redrob_signals", {}),
        "intent_score": candidate.get("intent_score", 0.0),
        "hidden_gem_score": candidate.get("hidden_gem_score", 0.0),
        "max_promotion_velocity": candidate.get("max_promotion_velocity", 0.0),
        "avg_time_in_role_months": candidate.get("avg_time_in_role_months", 0.0),
    }

    # Serialise lists and dicts
    for k, v in row.items():
        if isinstance(v, (list, dict)):
            row[k] = json.dumps(v)

    with get_conn() as conn:
        conn.execute(sql, row)
        actor = actor_context.get()
        owner = candidate.get("owner_id") or (
            (actor.get("workspace_id") or actor["username"]) if actor else None
        )
        conn.execute(
            "UPDATE candidates SET owner_id=COALESCE(owner_id,?), visibility=?, github=?, linkedin=? WHERE id=?",
            (
                owner,
                candidate.get("visibility", "private"),
                candidate.get("github", ""),
                candidate.get("linkedin", ""),
                candidate["id"],
            ),
        )


def get_candidate(candidate_id: str) -> Optional[Dict]:
    where, params = candidate_scope()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM candidates WHERE id = ? AND " + where, [candidate_id, *params]
        ).fetchone()
    if not row:
        return None
    return _clean_floats(_deserialise(dict(row)))


import math


def _clean_floats(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return 0.0
        return obj
    elif isinstance(obj, dict):
        return {k: _clean_floats(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_floats(v) for v in obj]
    return obj


def get_all_candidates(limit: int = 5000, offset: int = 0) -> List[Dict]:
    where, params = candidate_scope()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE " + where + " ORDER BY id LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [_clean_floats(_deserialise(dict(r))) for r in rows]


def get_candidates_by_ids(candidate_ids: List[str]) -> List[Dict]:
    """Return only visible candidates from an explicit, bounded candidate set."""
    ids = list(dict.fromkeys(candidate_ids))
    if not ids:
        return []
    where, params = candidate_scope()
    placeholders = ",".join("?" for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE id IN (" + placeholders + ") AND " + where,
            [*ids, *params],
        ).fetchall()
    return [_clean_floats(_deserialise(dict(r))) for r in rows]


def count_candidates() -> int:
    where, params = candidate_scope()
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM candidates WHERE " + where, params).fetchone()[0]


# ── JD run operations ──────────────────────────────────────────────────────────


def save_jd_run(run_id: str, jd_text: str, jd_parsed: Dict, weights: Dict):
    sql = """
        INSERT INTO jd_runs (run_id, jd_text, jd_parsed, weights, owner_id)
        VALUES (?, ?, ?, ?, ?)
    """
    with get_conn() as conn:
        conn.execute(
            sql,
            (
                run_id,
                jd_text,
                json.dumps(jd_parsed),
                json.dumps(weights),
                (actor_context.get() or {}).get("workspace_id")
                or (actor_context.get() or {}).get("username"),
            ),
        )


def get_jd_run(run_id: str) -> Optional[Dict]:
    where, params = run_scope()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM jd_runs WHERE run_id = ? AND " + where, [run_id, *params]
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["jd_parsed"] = json.loads(d["jd_parsed"] or "{}")
    d["weights"] = json.loads(d["weights"] or "{}")
    d["pipeline_metadata"] = _safe_json(d.get("pipeline_metadata") or "{}")
    return d


# ── Score operations ───────────────────────────────────────────────────────────


def save_score(run_id: str, candidate_id: str, scores: Dict[str, Any]):
    sql = """
        INSERT INTO candidate_scores (
            run_id, candidate_id,
            semantic_score, skill_score, trajectory_score,
            behavioral_score, domain_score, composite_score,
            rank_position, explanation, outreach_msg, skill_gap
        ) VALUES (
            :run_id, :candidate_id,
            :semantic_score, :skill_score, :trajectory_score,
            :behavioral_score, :domain_score, :composite_score,
            :rank_position, :explanation, :outreach_msg, :skill_gap
        )
        ON CONFLICT(run_id, candidate_id) DO UPDATE SET
            semantic_score=excluded.semantic_score,
            skill_score=excluded.skill_score,
            trajectory_score=excluded.trajectory_score,
            behavioral_score=excluded.behavioral_score,
            domain_score=excluded.domain_score,
            composite_score=excluded.composite_score,
            rank_position=excluded.rank_position,
            explanation=excluded.explanation,
            outreach_msg=excluded.outreach_msg,
            skill_gap=excluded.skill_gap
    """
    row = dict(scores)
    row["run_id"] = run_id
    row["candidate_id"] = candidate_id
    if isinstance(row.get("skill_gap"), (list, dict)):
        row["skill_gap"] = json.dumps(row["skill_gap"])
    with get_conn() as conn:
        conn.execute(sql, row)


def get_ranked_results(run_id: str) -> List[Dict]:
    if not get_jd_run(run_id):
        return []
    sql = """
        SELECT cs.*, c.name, c.current_title, c.current_company,
               c.years_experience, c.skills, c.domain, c.location
        FROM candidate_scores cs
        JOIN candidates c ON cs.candidate_id = c.id
        WHERE cs.run_id = ?
        ORDER BY cs.rank_position ASC
    """
    with get_conn() as conn:
        rows = conn.execute(sql, (run_id,)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["skills"] = _safe_json(d.get("skills"))
        d["skill_gap"] = _safe_json(d.get("skill_gap"))
        snapshot = _safe_json(d.pop("profile_snapshot", None))
        if isinstance(snapshot, dict):
            for field in (
                "name",
                "current_title",
                "current_company",
                "years_experience",
                "skills",
                "domain",
                "location",
            ):
                if field in snapshot:
                    d[field] = snapshot[field]
        d["rank"] = d["rank_position"]
        d["score_breakdown"] = {
            k: d[k + "_score"] for k in ("semantic", "skill", "trajectory", "behavioral", "domain")
        }
        d["explanation"] = d.get("explanation") or "Explanation unavailable."
        d["outreach_msg"] = d.get("outreach_msg") or ""
        results.append(d)
    return results


# ── Feedback operations ────────────────────────────────────────────────────────


def save_feedback(run_id: str, candidate_id: str, feedback_type: str, notes: str = ""):
    if not get_jd_run(run_id) or not any(
        r["candidate_id"] == candidate_id for r in get_ranked_results(run_id)
    ):
        raise ValueError("Candidate is not part of this run.")
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM feedback WHERE run_id=? AND candidate_id=?", (run_id, candidate_id)
        )
        conn.execute(
            "INSERT INTO feedback(run_id,candidate_id,feedback_type,notes) VALUES(?,?,?,?)",
            (run_id, candidate_id, feedback_type, notes),
        )


def get_feedback_map(run_id):
    if not get_jd_run(run_id):
        return {}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT candidate_id,feedback_type FROM feedback WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def get_rejected_candidates(run_id: str) -> List[str]:
    """Return candidate IDs marked 'not_a_fit' for a given run."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT candidate_id FROM feedback WHERE run_id=? AND feedback_type='not_a_fit'",
            (run_id,),
        ).fetchall()
    return [r[0] for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────────────


def _safe_json(val):
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return val


def _deserialise(row: Dict) -> Dict:
    """Parse JSON string fields back into Python objects."""
    for field in (
        "skills",
        "career_history",
        "education",
        "raw_data",
        "certifications",
        "languages",
        "redrob_signals",
    ):
        if isinstance(row.get(field), str):
            row[field] = _safe_json(row[field])
    return row


# ── Auth operations ───────────────────────────────────────────────────────────


def save_user(username: str, password_hash: str, role: str):
    sql = """
        INSERT INTO auth_users (username, password, role)
        VALUES (?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password=excluded.password,
            role=excluded.role
    """
    with get_conn() as conn:
        conn.execute(sql, (username, password_hash, role))


def get_user(username: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM auth_users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    return dict(row)


# ── Analytics & run-listing operations ────────────────────────────────────────


def list_jd_runs(limit: int = 50) -> List[Dict]:
    where, params = run_scope()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM jd_runs WHERE " + where + " ORDER BY created_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    results = []
    for row in rows:
        d = dict(row)
        d["jd_parsed"] = _safe_json(d.get("jd_parsed") or "{}")
        d["weights"] = _safe_json(d.get("weights") or "{}")
        d["jd_preview"] = d["jd_text"][:200]
        results.append(d)
    return results


def clear_all_runs():
    where, params = run_scope()
    with get_conn() as conn:
        for table in ("feedback", "candidate_scores"):
            conn.execute(
                f"DELETE FROM {table} WHERE run_id IN (SELECT run_id FROM jd_runs WHERE {where})",
                params,
            )
        conn.execute("DELETE FROM jd_runs WHERE " + where, params)


def get_analytics() -> Dict:
    from collections import Counter

    candidates = get_all_candidates(limit=100000)
    domains = Counter(c.get("domain") or "Unknown" for c in candidates)
    skills = Counter(s for c in candidates for s in (c.get("skills") or []) if isinstance(s, str))
    experience = [c["years_experience"] for c in candidates if (c.get("years_experience") or 0) > 0]
    where, params = run_scope()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT cs.run_id, MAX(cs.created_at) created_at, COUNT(*) candidates_evaluated, "
            "MAX(composite_score) top_score FROM candidate_scores cs JOIN jd_runs r ON r.run_id=cs.run_id "
            "WHERE " + where + " GROUP BY cs.run_id ORDER BY created_at DESC LIMIT 10",
            params,
        ).fetchall()
        scores = [
            r[0]
            for r in conn.execute(
                "SELECT composite_score FROM candidate_scores WHERE run_id IN "
                "(SELECT run_id FROM jd_runs WHERE " + where + ")",
                params,
            )
        ]
        total_runs = conn.execute("SELECT COUNT(*) FROM jd_runs WHERE " + where, params).fetchone()[
            0
        ]
    return {
        "total_candidates": len(candidates),
        "avg_experience_years": round(sum(experience) / len(experience), 1) if experience else 0,
        "domain_distribution": [{"domain": k, "count": v} for k, v in domains.most_common(15)],
        "top_skills": [{"skill": k, "count": v} for k, v in skills.most_common(20)],
        "score_stats": {
            "avg": round(sum(scores) / len(scores), 1) if scores else 0,
            "max": max(scores, default=0),
            "min": min(scores, default=0),
            "total_runs": total_runs,
        },
        "recent_runs": [dict(r) for r in rows],
    }
