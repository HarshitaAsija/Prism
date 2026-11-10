import React, { useEffect, useState } from "react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
export default function TeamSettings() {
  const { user } = useAuth();
  const [team, setTeam] = useState(null);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api
      .get("/team")
      .then((r) => setTeam(r.data))
      .catch(() => setError("Unable to load team."));
  }, []);
  async function submit(e, join) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const value = new FormData(e.currentTarget).get(join ? "token" : "email");
    try {
      if (join) {
        await api.post("/team/join", { token: value });
        window.location.reload();
      } else {
        const r = await api.post("/team/invites", { email: value });
        setToken(r.data.token);
      }
    } catch (e) {
      setError(
        typeof e.response?.data?.detail === "string"
          ? e.response.data.detail
          : "Unable to complete team action.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function remove(email) {
    setBusy(true);
    setError("");
    try {
      await api.delete(`/team/members/${encodeURIComponent(email)}`);
      const r = await api.get("/team");
      setTeam(r.data);
    } catch {
      setError("Unable to remove team member.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="glass rounded-2xl p-5">
      <summary className="cursor-pointer font-semibold">Team access</summary>
      {error && (
        <p role="alert" className="text-red-400 mt-3">
          {error}
        </p>
      )}
      {team && (
        <p className="text-sm text-slate-400 my-3">
          Workspace: {team.workspace_id}. Members:{" "}
          {team.members.map((m) => m.name || m.username).join(", ")}
        </p>
      )}
      {team &&
        user.email === team.workspace_id &&
        team.members
          .filter((m) => m.username !== team.workspace_id)
          .map((m) => (
            <div
              key={m.username}
              className="flex items-center gap-3 my-2 text-sm"
            >
              <span>{m.name || m.username}</span>
              <button
                disabled={busy}
                className="btn-secondary"
                onClick={() => remove(m.username)}
              >
                Remove member
              </button>
            </div>
          ))}
      <p className="text-sm mb-3">
        Team members share candidate imports, ranking runs, jobs, and recruiter
        notes.
      </p>
      <form onSubmit={(e) => submit(e, false)} className="flex flex-wrap gap-2">
        <label className="flex-1 text-sm">
          Invite a recruiter
          <input
            name="email"
            type="email"
            required
            className="input-dark mt-1"
          />
        </label>
        <button disabled={busy} className="btn-secondary self-end">
          Create invitation
        </button>
      </form>
      {token && (
        <div className="my-3 text-sm">
          <p>
            Share this one-time code with the invited recruiter. It expires in 7
            days.
          </p>
          <code className="block break-all p-3 bg-slate-950 rounded-lg mt-2 select-all">
            {token}
          </code>
        </div>
      )}
      <form
        onSubmit={(e) => submit(e, true)}
        className="flex flex-wrap gap-2 mt-4"
      >
        <label className="flex-1 text-sm">
          Accept an invitation
          <input
            name="token"
            required
            minLength={32}
            className="input-dark mt-1"
          />
        </label>
        <button disabled={busy} className="btn-secondary self-end">
          Join team
        </button>
      </form>
    </details>
  );
}
