"""
embedder.py — Loads the embedding model lazily on first use.
All other modules import embed_text / embed_batch from here.
Model runs 100% locally — no API call, no cost, no latency.
"""

from config import EMBEDDING_MODEL, DATA_DIR
import os
from typing import List

from threading import Lock

_model = None
_model_lock = Lock()


def model():
    global _model
    with _model_lock:
        if _model is None:
            from fastembed import TextEmbedding

            _model = TextEmbedding(
                model_name="sentence-transformers/" + EMBEDDING_MODEL,
                cache_dir=os.path.join(DATA_DIR, "embedding_cache"),
            )
    return _model


def embed_text(text: str) -> List[float]:
    """Convert a single string to a vector (list of floats)."""
    vecs = list(model().embed([text]))
    return vecs[0].tolist()


def embed_batch(texts: List[str], batch_size: int = 64) -> List[List[float]]:
    """
    Convert a list of strings to vectors efficiently.
    Uses batching — 10x faster than calling embed_text in a loop.
    """
    vecs = list(model().embed(texts, batch_size=batch_size))
    return [v.tolist() for v in vecs]


def build_candidate_profile_text(candidate: dict) -> str:
    """
    Combine all meaningful candidate fields into one rich text string.
    This is what gets embedded — richer text = better semantic matching.
    """
    parts = []

    if candidate.get("current_title"):
        parts.append(f"Current role: {candidate['current_title']}")

    if candidate.get("current_company"):
        parts.append(f"at {candidate['current_company']}")

    if candidate.get("years_experience"):
        parts.append(f"{candidate['years_experience']} years of experience")

    if candidate.get("domain"):
        parts.append(f"Domain: {candidate['domain']}")

    skills = candidate.get("skills", [])
    if isinstance(skills, list) and skills:
        parts.append(f"Skills: {', '.join(str(s) for s in skills)}")

    career = candidate.get("career_history", [])
    if isinstance(career, list):
        for job in career[:5]:  # cap at 5 most recent jobs
            if isinstance(job, dict):
                title = job.get("title", "")
                company = job.get("company", "")
                desc = job.get("description", "")
                if title:
                    parts.append(f"Worked as {title} at {company}. {desc}")

    education = candidate.get("education", [])
    if isinstance(education, list):
        for edu in education[:2]:
            if isinstance(edu, dict):
                degree = edu.get("degree", "")
                field = edu.get("field", "")
                school = edu.get("school", "")
                if degree:
                    parts.append(f"Education: {degree} in {field} from {school}")

    return " | ".join(p for p in parts if p.strip())
