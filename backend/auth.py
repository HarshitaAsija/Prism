"""Password authentication with revocable, hashed, expiring server sessions."""

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from database import get_conn, get_user, actor_context

router = APIRouter(prefix="/auth", tags=["authentication"])
COOKIE = "prism_session"
SESSION_SECONDS = 60 * 60 * 24 * 7


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, digest = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, AttributeError):
        return False


def public_user(user):
    return {
        "email": user["username"],
        "name": user["name"],
        "role": user["role"],
        "candidate_id": user.get("candidate_id"),
        "workspace_id": user.get("workspace_id") or user["username"],
    }


def limit_requests(key, maximum=15, window=60):
    now = int(time.time())
    bucket = now // window
    with get_conn() as conn:
        conn.execute("DELETE FROM request_limits WHERE bucket < ?", (bucket - 2,))
        conn.execute(
            "INSERT INTO request_limits (key, bucket, count) VALUES (?, ?, 1) "
            "ON CONFLICT(key, bucket) DO UPDATE SET count=count+1",
            (key, bucket),
        )
        count = conn.execute(
            "SELECT count FROM request_limits WHERE key=? AND bucket=?", (key, bucket)
        ).fetchone()[0]
    if count > maximum:
        raise HTTPException(
            429, "Too many requests. Try again shortly.", headers={"Retry-After": str(window)}
        )


async def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Please sign in.")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT u.* FROM auth_sessions s JOIN auth_users u ON u.username=s.username "
            "WHERE s.token_hash=? AND s.expires_at>?",
            (hashlib.sha256(token.encode()).hexdigest(), time.time()),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    # A custom header cannot be submitted by a cross-origin HTML form. CORS only
    # permits the configured frontend origins to send it.
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.headers.get("X-Prism-Client") != "web"
    ):
        raise HTTPException(403, "Missing request verification header.")
    user = dict(row)
    user["workspace_id"] = user.get("workspace_id") or user["username"]
    actor_context.set(user)
    return user


def recruiter(user=Depends(current_user)):
    if user["role"] not in {"recruiter", "admin"}:
        raise HTTPException(403, "Recruiter access required.")
    return user


def admin(user=Depends(current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")
    return user


def create_session(user, response):
    token = secrets.token_urlsafe(48)
    with get_conn() as conn:
        conn.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (time.time(),))
        conn.execute(
            "INSERT INTO auth_sessions VALUES (?, ?, ?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                user["username"],
                time.time() + SESSION_SECONDS,
            ),
        )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite=os.getenv("COOKIE_SAMESITE", "lax"),
        max_age=SESSION_SECONDS,
        path="/",
    )
    return public_user(user)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(pattern="^(candidate|recruiter)$")


@router.post("/register", status_code=201)
def register(body: Registration, request: Request, response: Response):
    limit_requests("register:" + (request.client.host if request.client else "unknown"), 10)
    email = body.email.strip().lower()
    if not body.name.strip():
        raise HTTPException(422, "Name cannot be blank.")
    candidate_id = "cand_" + uuid.uuid4().hex if body.role == "candidate" else None
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO auth_users(username,password,role,name,candidate_id) VALUES(?,?,?,?,?)",
                (email, hash_password(body.password), body.role, body.name.strip(), candidate_id),
            )
            if candidate_id:
                conn.execute(
                    "INSERT INTO candidates(id,name,email,owner_id,visibility,skills,career_history,education) "
                    "VALUES(?,?,?,?,'private','[]','[]','[]')",
                    (candidate_id, body.name.strip(), email, email),
                )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists.")
    return create_session(get_user(email), response)


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    limit_requests("login:" + (request.client.host if request.client else "unknown"), 10)
    user = get_user(body.email.strip().lower())
    # Always perform a password derivation, including for unknown accounts.
    encoded = user["password"] if user else "pbkdf2_sha256$600000$missing$" + "0" * 64
    valid = verify_password(body.password, encoded)
    if not user or not valid:
        raise HTTPException(401, "Invalid email or password.")
    return create_session(user, response)


@router.get("/me")
def me(user=Depends(current_user)):
    return public_user(user)


@router.post("/logout")
def logout(request: Request, response: Response, user=Depends(current_user)):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM auth_sessions WHERE token_hash=?",
            (hashlib.sha256(request.cookies[COOKIE].encode()).hexdigest(),),
        )
    response.delete_cookie(COOKIE, path="/")
    return {"status": "signed_out"}
