from evaluate import metrics


def test_ranking_metrics_penalize_wrong_order_and_duplicates():
    relevance = {"a": 3, "b": 1, "c": 0}
    ideal = metrics(["a", "b", "c"], relevance, 2)
    wrong = metrics(["c", "b", "a"], relevance, 2)
    assert ideal["ndcg_at_k"] == 1 and ideal["recall_at_k"] == 1
    assert wrong["ndcg_at_k"] < ideal["ndcg_at_k"]
    assert metrics(["a", "a"], relevance, 2)["precision_at_k"] == 0.5
