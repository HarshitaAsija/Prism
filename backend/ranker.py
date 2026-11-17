"""Rank only authorized profiles, using reproducible scores and recoverable indexing."""

import uuid
from starlette.concurrency import run_in_threadpool
from config import (
    DEFAULT_WEIGHTS,
    TOP_N_SEMANTIC,
    TOP_N_FINAL,
    TOP_N_EXPLAIN,
    TOP_N_OUTREACH,
    EMBEDDING_MODEL,
    NVIDIA_MODEL,
)
from database import (
    get_all_candidates,
    get_candidates_by_ids,
    get_conn,
    save_jd_run,
    save_score,
    get_ranked_results,
    get_feedback_map,
)
from combiner import build_score_dict, _normalise_weights
from scorer import semantic_score, skill_score, trajectory_score, behavioral_score, domain_score


def retrieve(jd_text, candidate_ids=None):
    from embedder import embed_text, embed_batch, build_candidate_profile_text
    from vector_store import add_candidates, search, collection

    # Job applicant ranking passes a small, explicit set. General discovery keeps
    # the existing workspace-scoped candidate pool.
    profiles = (
        get_candidates_by_ids(candidate_ids)
        if candidate_ids is not None
        else get_all_candidates(limit=100000)
    )
    ids = [c["id"] for c in profiles]
    if not ids:
        return [], {}
    # Reconcile missing vectors as well as edited profiles, without changing source data.
    indexed = set(collection().get(ids=ids, include=[])["ids"])
    pending = [c for c in profiles if c.get("index_status") != "ready" or c["id"] not in indexed]
    if pending:
        texts = [build_candidate_profile_text(c) for c in pending]
        add_candidates(
            [c["id"] for c in pending],
            embed_batch(texts),
            [{"candidate_id": c["id"], "name": c.get("name") or ""} for c in pending],
            texts,
        )
        with get_conn() as conn:
            conn.executemany(
                "UPDATE candidates SET index_status='ready' WHERE id=?",
                [(c["id"],) for c in pending],
            )
    return search(embed_text(jd_text), top_n=TOP_N_SEMANTIC, candidate_ids=ids), {
        c["id"]: c for c in profiles
    }


async def rank_candidates(
    jd_text,
    weights=None,
    run_id=None,
    previous_run_id=None,
    top_n=20,
    candidate_ids=None,
    parsed_jd=None,
    pipeline_metadata=None,
):
    from jd_parser import parse_jd
    from explainer import batch_explain, batch_outreach
    from feedback_reranker import apply_feedback_boost

    parsed = parsed_jd or await run_in_threadpool(parse_jd, jd_text)
    if candidate_ids is None:
        matches, profiles = await run_in_threadpool(retrieve, jd_text)
    else:
        matches, profiles = await run_in_threadpool(retrieve, jd_text, candidate_ids)
    weights = _normalise_weights(weights or DEFAULT_WEIGHTS)
    feedback = get_feedback_map(previous_run_id) if previous_run_id else {}
    scored = []
    for match in matches:
        candidate = profiles[match["candidate_id"]]
        sk, gaps = skill_score(candidate, parsed)
        score = build_score_dict(
            candidate["id"],
            semantic_score(match["similarity"]),
            sk,
            trajectory_score(candidate, parsed),
            behavioral_score(candidate),
            domain_score(candidate, parsed),
            weights,
        )
        score["skill_gap"] = gaps
        scored.append({**candidate, **score, "candidate_id": candidate["id"]})
    scored.sort(key=lambda r: (-r["composite_score"], -r["behavioral_score"], r["candidate_id"]))
    if feedback:
        scored = await run_in_threadpool(apply_feedback_boost, scored, previous_run_id, feedback)
    scored = scored[: min(top_n, TOP_N_FINAL)]
    for i, row in enumerate(scored, 1):
        row["rank_position"] = i
    explanations = await batch_explain(scored[:TOP_N_EXPLAIN], scored[:TOP_N_EXPLAIN], parsed)
    for row, text in zip(scored, explanations):
        row["explanation"] = text
    outreach = await batch_outreach(scored[:TOP_N_OUTREACH], parsed)
    for row, text in zip(scored, outreach):
        row["outreach_msg"] = text
    run_id = run_id or str(uuid.uuid4())
    # One transaction prevents partially saved runs.
    from database import actor_context
    import json

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jd_runs(run_id,jd_text,jd_parsed,weights,owner_id,pipeline_metadata) VALUES(?,?,?,?,?,?)",
            (
                run_id,
                jd_text,
                json.dumps(parsed),
                json.dumps(weights),
                (actor_context.get() or {}).get("workspace_id")
                or (actor_context.get() or {}).get("username"),
                json.dumps(
                    {
                        "scoring_version": "prism-2",
                        "embedding_model": EMBEDDING_MODEL,
                        "explanation_model": NVIDIA_MODEL,
                        "previous_run_id": previous_run_id,
                        "feedback": feedback,
                        **(pipeline_metadata or {}),
                    }
                ),
            ),
        )
        fields = [
            "semantic_score",
            "skill_score",
            "trajectory_score",
            "behavioral_score",
            "domain_score",
            "composite_score",
            "rank_position",
            "explanation",
            "outreach_msg",
            "skill_gap",
            "profile_snapshot",
        ]
        for row in scored:
            source = profiles[row["candidate_id"]]
            row["profile_snapshot"] = {
                key: source.get(key)
                for key in (
                    "name",
                    "current_title",
                    "current_company",
                    "years_experience",
                    "skills",
                    "domain",
                    "location",
                )
            }
            values = [
                json.dumps(row[k]) if k in {"skill_gap", "profile_snapshot"} else row.get(k)
                for k in fields
            ]
            conn.execute(
                "INSERT INTO candidate_scores(run_id,candidate_id,"
                + ",".join(fields)
                + ") VALUES("
                + ",".join("?" for _ in range(13))
                + ")",
                [run_id, row["candidate_id"], *values],
            )
    return {
        "run_id": run_id,
        "jd_parsed": parsed,
        "weights": weights,
        "total_candidates_evaluated": len(matches),
        "results": get_ranked_results(run_id),
    }
