import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database as db
from main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.actor_context.set(None)
    with TestClient(app) as c:
        c.headers["X-Prism-Client"] = "web"
        yield c
    db.actor_context.set(None)
