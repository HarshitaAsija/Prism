import sys
import types
from datetime import datetime, timedelta, timezone
import pytest
from test_security import account
import database as db


def test_hiring_flow_and_private_notes(client):
    account(client, "recruiter@example.com", "recruiter")
    job = client.post(
        "/jobs",
        json={
            "title": "Backend Engineer",
            "company": "Prism",
            "location": "Remote",
            "description": "Build reliable backend APIs and maintain production services with a small team.",
            "required_skills": ["Python", "Go"],
        },
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    client.post("/auth/logout")
    candidate = account(client, "candidate@example.com")
    assert client.post(f"/jobs/{job_id}/apply", json={}).status_code == 422
    client.put(
        "/candidates/" + candidate["candidate_id"], json={"title": "Engineer", "skills": ["Python"]}
    )
    assert client.get(f"/jobs/{job_id}/match").json()["score"] == 30
    response = client.post(f"/jobs/{job_id}/apply", json={"cover_note": "Interested"})
    assert response.status_code == 201, response.text
    app_id = response.json()["id"]
    assert client.post(f"/jobs/{job_id}/apply", json={}).status_code == 409
    assert client.patch(f"/applications/{app_id}", json={"stage": "hired"}).status_code == 403
    client.post("/auth/logout")
    account(client, "stranger@example.com", "recruiter")
    assert client.get("/applications").json()["applications"] == []
    assert client.post(f"/applications/{app_id}/notes", json={"body": "attack"}).status_code == 404
    assert client.get("/candidates/" + candidate["candidate_id"]).status_code == 404
    client.post("/auth/logout")
    client.post(
        "/auth/login", json={"email": "recruiter@example.com", "password": "a-good-password"}
    )
    assert client.get("/candidates/" + candidate["candidate_id"]).status_code == 200
    assert client.patch(f"/applications/{app_id}", json={"stage": "hired"}).status_code == 409
    assert client.patch(f"/applications/{app_id}", json={"stage": "screened"}).status_code == 200
    assert (
        client.post(
            f"/applications/{app_id}/notes", json={"body": "Private evaluation"}
        ).status_code
        == 201
    )
    when = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert (
        client.post(
            f"/applications/{app_id}/interviews",
            json={"scheduled_at": when, "meeting_url": "https://meet.example.com/interview"},
        ).status_code
        == 201
    )
    assert client.get("/applications").json()["applications"][0]["stage"] == "interview"
    client.post("/auth/logout")
    client.post(
        "/auth/login", json={"email": "candidate@example.com", "password": "a-good-password"}
    )
    app = client.get("/applications").json()["applications"][0]
    assert "notes" not in app and app["interviews"]
    assert client.post(f"/applications/{app_id}/withdraw").status_code == 200
    client.post("/auth/logout")
    client.post(
        "/auth/login", json={"email": "recruiter@example.com", "password": "a-good-password"}
    )
    assert client.get("/candidates/" + candidate["candidate_id"]).status_code == 404


def test_ai_failure_is_not_success(client, monkeypatch):
    account(client, role="recruiter")
    import jd_parser, resume_parser
    from llm_client import AIUnavailable

    def unavailable(*args, **kwargs):
        raise AIUnavailable("Unavailable")

    monkeypatch.setattr(jd_parser, "chat", unavailable)
    response = client.post(
        "/jd/bias-scan",
        json={"jd_text": "A useful job description with enough detail to exceed fifty characters."},
    )
    assert response.status_code == 503 and "score" not in response.json()
    monkeypatch.setattr(resume_parser, "chat", lambda *a, **k: "not JSON")
    with pytest.raises(AIUnavailable):
        resume_parser.parse_resume_text("Python engineer")
    monkeypatch.setattr(jd_parser, "chat", lambda *a, **k: '{"required_skills": "Python"}')
    assert (
        client.post(
            "/jd/analyze",
            json={
                "jd_text": "A useful job description with enough detail to exceed fifty characters."
            },
        ).status_code
        == 503
    )


def test_upload_bounds_and_role_before_ai_import(client):
    account(client)
    assert (
        client.post(
            "/candidates/upload", files={"file": ("test.txt", b"text", "text/plain")}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/candidates/upload",
            files={"file": ("test.csv", b"name,skills\nTest,Python", "text/csv")},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/candidates/upload",
            files={"file": ("large.pdf", b"0" * (5 * 1024 * 1024 + 1), "application/pdf")},
        ).status_code
        == 413
    )


def test_ranking_contract_fallback_and_atomic_save(client, monkeypatch):
    account(client, role="recruiter")
    import ranker, jd_parser, explainer
    from fastapi import HTTPException
    from llm_client import AIUnavailable

    profile = {
        "id": "c",
        "name": "Candidate",
        "skills": ["Python"],
        "years_experience": 3,
        "career_history": [],
        "domain": "saas",
    }
    # Source data visible to this recruiter, without any model downloads.
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO candidates(id,name,owner_id,skills) VALUES('c','Candidate','first@example.com','[\"Python\"]')"
        )
    monkeypatch.setattr(
        jd_parser, "parse_jd", lambda text: {"required_skills": ["Python"], "domain": "saas"}
    )
    monkeypatch.setattr(
        ranker,
        "retrieve",
        lambda text: ([{"candidate_id": "c", "similarity": 0.8}], {"c": profile}),
    )

    async def fail(*a, **k):
        raise AIUnavailable("down")

    monkeypatch.setattr(explainer, "generate_explanation", fail)
    monkeypatch.setattr(explainer, "generate_outreach", fail)
    response = client.post(
        "/rank",
        json={
            "jd_text": "Build and maintain production Python backend services for our product.",
            "top_n": 1,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    row = data["results"][0]
    assert row["rank"] == 1 and 0 <= row["composite_score"] <= 100
    assert row["explanation"].startswith("Explanation unavailable")
    assert client.get("/runs/" + data["run_id"] + "/results").json()["results"] == data["results"]
    assert client.get("/analytics").json()["score_stats"]["max"] == row["composite_score"]
    with db.get_conn() as conn:
        conn.execute("UPDATE candidates SET name='Changed later' WHERE id='c'")
    assert (
        client.get("/runs/" + data["run_id"] + "/results").json()["results"][0]["name"]
        == "Candidate"
    )
    response = client.post(
        "/feedback",
        json={"run_id": data["run_id"], "candidate_id": "missing", "feedback_type": "strong_yes"},
    )
    assert response.status_code == 422


def test_session_revocation_and_expiry(client):
    account(client)
    with db.get_conn() as conn:
        conn.execute("UPDATE auth_sessions SET expires_at=0")
    assert client.get("/auth/me").status_code == 401


def test_login_throttle(client, monkeypatch):
    monkeypatch.setattr("auth.time.time", lambda: 1700000000)
    for i in range(10):
        response = client.post(
            "/auth/login", json={"email": "unknown@example.com", "password": "a-good-password"}
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": "unknown@example.com", "password": "a-good-password"}
        ).status_code
        == 429
    )


def test_static_search_route_is_not_candidate_id(client):
    import main

    paths = [r.path for r in main.app.routes if hasattr(r, "path")]
    assert paths.index("/candidates/search") < paths.index("/candidates/{candidate_id}")


def test_team_invitation_shares_workspace_only_with_recipient(client):
    account(client, "owner@example.com", "recruiter")
    job = client.post(
        "/jobs",
        json={
            "title": "Backend Engineer",
            "company": "Team",
            "location": "Remote",
            "description": "Build reliable backend APIs and maintain production services with a small team.",
            "required_skills": ["Python"],
        },
    ).json()
    token = client.post("/team/invites", json={"email": "member@example.com"}).json()["token"]
    client.post("/auth/logout")
    account(client, "stranger@example.com", "recruiter")
    assert client.post("/team/join", json={"token": token}).status_code == 404
    client.post("/auth/logout")
    account(client, "member@example.com", "recruiter")
    response = client.post("/team/join", json={"token": token})
    assert response.status_code == 200, response.text
    assert client.get("/auth/me").json()["workspace_id"] == "owner@example.com"
    assert client.get("/jobs?mine=true").json()["jobs"][0]["id"] == job["id"]
    assert len(client.get("/team").json()["members"]) == 2
    assert client.post("/team/invites", json={"email": "third@example.com"}).status_code == 403
    assert client.post("/team/join", json={"token": token}).status_code == 404


def test_admin_metrics_not_public_or_recruiter_accessible(client):
    assert client.get("/admin/metrics").status_code == 401
    account(client, role="recruiter")
    assert client.get("/admin/metrics").status_code == 403
    with db.get_conn() as conn:
        conn.execute("UPDATE auth_users SET role='admin' WHERE username='first@example.com'")
    data = client.get("/admin/metrics").json()
    assert isinstance(data["requests_observed"], int) and data["requests_observed"] > 0
    assert data["token_usage"]["total_tokens"] == 0


def test_team_removal_revokes_member_session(client):
    account(client, "owner@example.com", "recruiter")
    token = client.post("/team/invites", json={"email": "member@example.com"}).json()["token"]
    client.post("/auth/logout")
    account(client, "member@example.com", "recruiter")
    assert client.post("/team/join", json={"token": token}).status_code == 200
    member_cookie = client.cookies.get("prism_session")
    client.post("/auth/login", json={"email": "owner@example.com", "password": "a-good-password"})
    assert client.delete("/team/members/member@example.com").status_code == 200
    client.cookies.clear()
    client.cookies.set("prism_session", member_cookie)
    assert client.get("/auth/me").status_code == 401
