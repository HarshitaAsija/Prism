import test from "node:test";
import assert from "node:assert/strict";
import {
  normalizeScore,
  normalizeWeights,
  reweightResults,
} from "./helpers.js";
test("API scores use an unambiguous 0-100 scale, including low scores", () => {
  assert.equal(normalizeScore(0.8), 0.8);
  assert.equal(normalizeScore(80), 80);
  assert.equal(normalizeScore(8000), 100);
});
test("Changing weights preserves units and ranks by selected evidence", () => {
  const results = [
    {
      candidate_id: "a",
      score_breakdown: {
        semantic: 90,
        skill: 20,
        trajectory: 50,
        behavioral: 50,
        domain: 50,
      },
    },
    {
      candidate_id: "b",
      score_breakdown: {
        semantic: 20,
        skill: 90,
        trajectory: 50,
        behavioral: 50,
        domain: 50,
      },
    },
  ];
  const ranked = reweightResults(results, { skill: 100 });
  assert.equal(ranked[0].candidate_id, "b");
  assert.equal(ranked[0].composite_score, 90);
  assert.equal(ranked[0].rank, 1);
  assert.equal(results[0].rank, undefined);
});
test("Zero weights use server defaults and equal scores remain 80", () => {
  assert.equal(normalizeWeights({}).semantic, 0.3);
  assert.equal(
    reweightResults(
      [
        {
          candidate_id: "a",
          score_breakdown: {
            semantic: 80,
            skill: 80,
            trajectory: 80,
            behavioral: 80,
            domain: 80,
          },
        },
      ],
      {},
    )[0].composite_score,
    80,
  );
});
