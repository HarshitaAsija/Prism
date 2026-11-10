# Ranking evaluation

Replace the synthetic example with consented, representative profiles and independent recruiter relevance labels (0 irrelevant, 1 partial, 2 good, 3 strong). Record role, requirements, adjudication, reviewer identity and date, and why each candidate is relevant. Keep candidate identifiers pseudonymous.

Supply the actual ordered IDs returned by a ranking run, not a hand-crafted order. Run:

```sh
python backend/evaluate.py backend/evaluation/example-labels.json backend/evaluation/example-rankings.json --k 3
```

The tool reports precision, recall and NDCG at k. The example checks the evaluation machinery; it does not measure Prism's hiring quality. Label review, representative coverage, retrieval recall on a larger pool, stability across weight settings, and unsupported explanation claims still need independent evaluation. Compare results with a simple skill-overlap baseline. Track regressions by scorer/model version, input snapshot and weights.
