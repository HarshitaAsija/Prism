import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── NVIDIA NIM API ─────────────────────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

# ── Embedding model (runs 100% locally, no API needed) ────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# ── Local storage paths ────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.getenv("PRISM_DB_PATH") or os.path.join(DATA_DIR, "recruiter.db")  # SQLite file
CHROMA_PATH = os.getenv("PRISM_CHROMA_PATH") or os.path.join(
    DATA_DIR, "chroma_store"
)  # ChromaDB folder
DATASET_PATH = os.path.join(DATA_DIR, "candidates.csv")  # challenge dataset

# ── ChromaDB collection name ──────────────────────────────────────────────────
CHROMA_COLLECTION = "candidates"

# ── Default scoring weights (must sum to 1.0) ─────────────────────────────────
DEFAULT_WEIGHTS = {
    "semantic": 0.35,
    "skill": 0.30,
    "trajectory": 0.25,
    # Activity and profile-completeness are not decision factors by default.
    # Recruiters can opt in for an availability-oriented workflow.
    "behavioral": 0.0,
    "domain": 0.10,
}

# ── Ranking config ─────────────────────────────────────────────────────────────
TOP_N_SEMANTIC = 100  # candidates retrieved from vector search
TOP_N_FINAL = 100  # candidates in final shortlist
TOP_N_EXPLAIN = 5  # how many get AI explanation
TOP_N_OUTREACH = 3  # how many get outreach message draft

# ── Behavioral score decay (days → score) ─────────────────────────────────────
ACTIVITY_DECAY = {
    30: 1.00,
    90: 0.75,
    180: 0.50,
    365: 0.25,
}
ACTIVITY_DEFAULT = 0.10  # score when last_active > 365 days or unknown

# ── Skill credibility multipliers ─────────────────────────────────────────────
SKILL_CREDIBILITY = {
    "no_evidence": 0.60,
    "one_project": 1.00,
    "multi_project": 1.20,
}

# ── CORS origins (add your frontend URL here) ─────────────────────────────────
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(
        ","
    )
    if origin.strip()
]
