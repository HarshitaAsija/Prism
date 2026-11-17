import database as db


def account(client, email="first@example.com", role="candidate"):
    response = client.post(
        "/auth/register",
        json={"email": email, "name": "Test User", "password": "a-good-password", "role": role},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_registration_password_session_and_logout(client):
    user = account(client)
    assert user["candidate_id"]
    assert client.get("/auth/me").json()["email"] == user["email"]
    stored = db.get_user(user["email"])
    assert stored["password"].startswith("pbkdf2_sha256$")
    assert "a-good-password" not in stored["password"]
    assert client.cookies.get("prism_session") not in str(stored)
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/me/profile").status_code == 401
    assert (
        client.post(
            "/auth/login", json={"email": user["email"], "password": "a-good-password"}
        ).status_code
        == 200
    )


def test_candidate_can_export_and_delete_own_account(client):
    user = account(client, "candidate@example.com")
    export = client.get("/me/export")
    assert export.status_code == 200
    assert export.json()["account"]["email"] == "candidate@example.com"
    assert export.json()["profile"]["id"] == user["candidate_id"]
    assert client.request("DELETE", "/me/account", json={"confirm_email": "wrong@example.com"}).status_code == 422
    assert client.request("DELETE", "/me/account", json={"confirm_email": "candidate@example.com"}).status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_anonymous_routes_are_protected(client):
    for path in ["/candidates", "/stats", "/analytics", "/runs", "/me/profile"]:
        assert client.get(path).status_code == 401
    assert client.delete("/runs").status_code == 401
    assert client.post("/admin/seed").status_code == 404


def test_candidate_ownership_and_role(client):
    first = account(client)
    original = client.get("/me/profile").json()
    assert original["id"] == first["candidate_id"]
    assert (
        client.put(
            "/candidates/" + original["id"],
            json={"title": "Engineer", "github": "https://github.com/test"},
        ).status_code
        == 200
    )
    client.post("/auth/logout")
    second = account(client, "second@example.com")
    assert second["candidate_id"] != first["candidate_id"]
    assert client.get("/candidates/" + first["candidate_id"]).status_code == 404
    assert (
        client.put("/candidates/" + first["candidate_id"], json={"name": "Attack"}).status_code
        == 404
    )
    assert client.get("/candidates").status_code == 403
    assert client.get("/me/profile").json()["current_title"] is None


def test_registration_cannot_promote_admin_or_overwrite(client):
    account(client)
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "name": "Admin",
                "password": "a-good-password",
                "role": "admin",
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "first@example.com",
                "name": "Again",
                "password": "a-good-password",
                "role": "candidate",
            },
        ).status_code
        == 409
    )


def test_csrf_header_required(client):
    account(client)
    del client.headers["X-Prism-Client"]
    assert client.post("/auth/logout").status_code == 403


def test_recruiter_scope(client):
    account(client, role="recruiter")
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO candidates(id,name,owner_id,visibility) VALUES('mine','Mine','first@example.com','private'),('other','Other','other@example.com','private'),('public','Public','other@example.com','public')"
        )
        conn.execute(
            "INSERT INTO jd_runs(run_id,jd_text,owner_id) VALUES('mine','JD','first@example.com'),('other','JD','other@example.com')"
        )
    assert {c["id"] for c in client.get("/candidates").json()["candidates"]} == {"mine", "public"}
    assert client.get("/runs/other").status_code == 404
    assert client.get("/runs/mine").status_code == 200
    assert client.put("/candidates/public", json={"name": "Attack"}).status_code == 403
    assert client.delete("/runs").status_code == 200
    with db.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM jd_runs WHERE run_id='other'").fetchone()[0] == 1


def test_profile_survives_restart_and_no_demo_seed(client):
    account(client)
    before = client.get("/me/profile").json()
    from main import startup

    startup()
    assert client.get("/me/profile").json()["id"] == before["id"]
    assert client.get("/me/profile").json()["name"] == "Test User"


def test_pagination_bounds(client):
    account(client, role="recruiter")
    for query in ["limit=-1", "limit=100000", "offset=-1"]:
        assert client.get("/candidates?" + query).status_code == 422


def test_score_units_and_cached_contract(client):
    account(client, role="recruiter")
    from combiner import build_score_dict

    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO candidates(id,name,owner_id) VALUES('c','Candidate','first@example.com')"
        )
        conn.execute(
            "INSERT INTO jd_runs(run_id,jd_text,owner_id) VALUES('r','JD','first@example.com')"
        )
    score = build_score_dict("c", 0.8, 0.8, 0.8, 0.8, 0.8)
    score["rank_position"] = 1
    db.save_score("r", "c", score)
    assert client.get("/analytics").json()["score_stats"]["avg"] == 80
    result = client.get("/runs/r/results").json()["results"][0]
    assert result["rank"] == 1
    assert result["score_breakdown"]["skill"] == 80
    assert result["composite_score"] == 80


def test_skill_boundaries_and_evidence():
    from scorer.skill_scorer import skill_score

    jd = {"required_skills": ["Go", "C"]}
    score, gaps = skill_score({"skills": ["Django", "React"], "career_history": []}, jd)
    assert score == 0 and all(g["status"] == "missing" for g in gaps)
    score, gaps = skill_score({"skills": ["Python"]}, {"required_skills": ["Python"]})
    assert score == 0.6 and gaps[0]["evidence"] == 0
    score, gaps = skill_score(
        {
            "skills": ["Python"],
            "career_history": [{"description": "Python APIs"}, {"description": "Python APIs"}],
        },
        {"required_skills": ["Python"]},
    )
    assert gaps[0]["evidence"] == 1 and gaps[0]["credibility"] == 1
    assert skill_score({"skills": ["golang"]}, {"required_skills": ["Go"]})[0] == 0.6


def test_additive_migration_preserves_original_database(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path

    schema = (Path(__file__).parent / "fixtures" / "legacy_schema.sql").read_text(encoding="utf-8")
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
        conn.execute("INSERT INTO candidates(id,name) VALUES('legacy','Existing Person')")
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    db.init_db()
    with db.get_conn() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE id='legacy'").fetchone()
        assert (
            row["name"] == "Existing Person"
            and row["visibility"] == "private"
            and row["owner_id"] is None
        )
        assert "workspace_id" in {r[1] for r in conn.execute("PRAGMA table_info(auth_users)")}


def test_invalid_career_dates_are_unknown():
    from scorer.trajectory_scorer import _parse_job

    assert _parse_job({"title": "Senior Engineer", "start_date": "not-a-date"}) is None
    assert (
        _parse_job({"title": "Senior Engineer", "start_date": "2035-01", "end_date": "2020-01"})
        is None
    )
