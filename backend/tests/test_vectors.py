"""Real Chroma persistence/filtering tests with tiny deterministic vectors, no downloads."""

import pytest
import database as db


def test_vector_authorization_and_recovery(client, tmp_path, monkeypatch):
    chromadb = pytest.importorskip("chromadb")
    import vector_store, embedder, ranker

    collection = chromadb.PersistentClient(path=str(tmp_path / "vectors")).get_or_create_collection(
        "test_candidates", metadata={"hnsw:space": "cosine"}
    )
    monkeypatch.setattr(vector_store, "_collection", collection)
    vector_store.add_candidates(
        ["private", "mine"],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        [{"name": "Private"}, {"name": "Mine"}],
        ["private text", "mine text"],
    )
    assert (
        vector_store.search([1.0, 0.0, 0.0], top_n=1, candidate_ids=["mine"])[0]["candidate_id"]
        == "mine"
    )
    assert vector_store.search([1.0, 0.0, 0.0], candidate_ids=[]) == []
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO candidates(id,name,owner_id,skills,index_status) VALUES('mine','Mine','owner@example.com','[]','ready')"
        )
    token = db.actor_context.set({"username": "owner@example.com", "role": "recruiter"})
    try:
        collection.delete(ids=["mine"])
        monkeypatch.setattr(embedder, "embed_text", lambda _: [0.0, 1.0, 0.0])
        monkeypatch.setattr(embedder, "embed_batch", lambda texts: [[0.0, 1.0, 0.0] for _ in texts])
        matches, profiles = ranker.retrieve("Backend engineer")
        assert matches[0]["candidate_id"] == "mine"
        assert set(profiles) == {"mine"}
        assert db.get_candidate("mine")["name"] == "Mine"
        assert db.get_candidate("mine")["index_status"] == "ready"
    finally:
        db.actor_context.reset(token)


def test_integrity_accepts_employers():
    from redrob_signals import VerifyProfileIntegrity

    verifier = VerifyProfileIntegrity()
    for company in ["TCS", "Infosys", "Wipro", "Accenture", "Cognizant", "Capgemini"]:
        assert verifier.is_valid({"current_company": company, "years_experience": 2})
