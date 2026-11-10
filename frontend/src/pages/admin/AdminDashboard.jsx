import React, { useCallback, useEffect, useState } from "react";
import api from "../../api/client";
export default function AdminDashboard() {
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const r = await api.get("/admin/metrics");
    setMetrics(r.data);
  }, []);
  useEffect(() => {
    load().catch(() => setError("Unable to load system metrics."));
  }, [load]);
  async function refresh(reindex = false) {
    setBusy(true);
    setError("");
    try {
      if (reindex) await api.post("/admin/reindex");
      await load();
    } catch {
      setError("The operation failed. Check the server logs and retry.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="max-w-4xl mx-auto space-y-5">
      <h1 className="text-2xl font-bold">System metrics</h1>
      {error && (
        <p role="alert" className="text-red-400">
          {error}
        </p>
      )}
      <div className="flex gap-3">
        <button
          disabled={busy}
          className="btn-secondary"
          onClick={() => refresh()}
        >
          Refresh
        </button>
        <button
          disabled={busy}
          className="btn-primary"
          onClick={() => refresh(true)}
        >
          Rebuild candidate index
        </button>
      </div>
      {metrics && (
        <>
          <p className="text-sm text-slate-400">
            {metrics.scope}. Token usage resets when the server restarts.
          </p>
          <dl className="glass rounded-2xl p-6 grid sm:grid-cols-2 gap-5">
            {Object.entries({
              Candidates: metrics.candidates,
              "AI configured": metrics.ai_configured ? "Yes" : "No",
              "Requests observed": metrics.requests_observed,
              "Failed requests": metrics.failed_requests,
              "Average duration":
                metrics.average_duration_ms == null
                  ? "No samples"
                  : `${metrics.average_duration_ms} ms`,
              "AI tokens used": metrics.token_usage.total_tokens,
            }).map(([k, v]) => (
              <div key={k}>
                <dt className="text-sm text-slate-400">{k}</dt>
                <dd className="text-xl mt-1">{v}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}
