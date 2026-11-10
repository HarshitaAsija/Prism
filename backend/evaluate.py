"""Evaluate supplied rankings against human relevance labels; never invent approval."""

import argparse
import json
import math
from pathlib import Path


def metrics(ranked_ids, relevance, k=10):
    if k < 1:
        raise ValueError("k must be positive")
    ranked = list(dict.fromkeys(ranked_ids))[:k]
    relevant = {key for key, value in relevance.items() if value > 0}
    hits = sum(cid in relevant for cid in ranked)
    dcg = sum((2 ** relevance.get(cid, 0) - 1) / math.log2(i + 2) for i, cid in enumerate(ranked))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum((2**value - 1) / math.log2(i + 2) for i, value in enumerate(ideal))
    return {
        "precision_at_k": hits / k,
        "recall_at_k": hits / len(relevant) if relevant else 0,
        "ndcg_at_k": dcg / idcg if idcg else 0,
        "k": k,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("rankings", type=Path, help="JSON mapping job ID to ordered candidate IDs")
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    data = json.loads(args.dataset.read_text(encoding="utf-8-sig"))
    rankings = json.loads(args.rankings.read_text(encoding="utf-8-sig"))
    print(
        json.dumps(
            {
                "label_status": data.get("label_status", "unreviewed"),
                "results": {
                    case["job_id"]: metrics(
                        rankings.get(case["job_id"], []), case["relevance"], args.k
                    )
                    for case in data["cases"]
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
