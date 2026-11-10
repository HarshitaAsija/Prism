
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
