import React, { useCallback, useEffect, useState } from "react";
import api from "../api/client";
import TeamSettings from "../components/TeamSettings";
import { useAuth } from "../context/AuthContext";
const transitions = {
  applied: ["screened", "rejected"],
  screened: ["interview", "rejected"],
  interview: ["offer", "rejected"],
  offer: ["hired", "rejected"],
};
export default function HiringWorkspace() {
  const { user } = useAuth();
  const candidate = user.role === "candidate";
  const [jobs, setJobs] = useState([]);
  const [applications, setApplications] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [match, setMatch] = useState({});
  const [applicantRanks, setApplicantRanks] = useState({});
  const [search, setSearch] = useState("");
  const load = useCallback(async () => {
    const [j, a] = await Promise.all([
      api.get("/jobs", { params: { mine: !candidate, limit: 100 } }),
      api.get("/applications", { params: { limit: 200 } }),
    ]);
    setJobs(j.data.jobs);
    setApplications(a.data.applications);
  }, [candidate]);
  useEffect(() => {
    load().catch(() => setError("Unable to load hiring data. Please refresh."));
  }, [load]);
  async function action(fn) {
    setBusy(true);
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError(
        typeof e.response?.data?.detail === "string"
          ? e.response.data.detail
          : "Unable to complete this action. Check the form and try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function createJob(e) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = new FormData(form);
    await action(async () => {
      await api.post("/jobs", {
        title: data.get("title"),
        company: data.get("company"),
        location: data.get("location"),
        description: data.get("description"),
        required_skills: data
          .get("skills")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      form.reset();
    });
  }
  const applied = new Set(applications.map((a) => a.job_id));
  const visible = jobs.filter((j) =>
    `${j.title} ${j.company} ${j.location} ${j.required_skills.join(" ")}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <section className="space-y-6 max-w-5xl mx-auto">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">
          {candidate ? "Jobs and applications" : "Hiring workspace"}
        </h1>
        <button
          className="btn-secondary"
          disabled={busy}
          onClick={() => action(load)}
        >
          Refresh
        </button>
      </div>
      {error && (
        <p role="alert" className="text-red-400">
          {error}
        </p>
      )}
      {!candidate && <TeamSettings />}
      {!candidate && (
        <details className="glass p-5 rounded-2xl">
          <summary className="cursor-pointer font-semibold">Post a job</summary>
          <form onSubmit={createJob} className="space-y-3 mt-4">
            {[
              ["title", "Job title"],
              ["company", "Company"],
              ["location", "Location or remote"],
              ["skills", "Required skills, separated by commas"],
            ].map(([name, label]) => (
              <label className="block text-sm" key={name}>
                {label}
                <input
                  name={name}
                  required
                  maxLength={name === "skills" ? 1000 : 160}
                  className="input-dark mt-1"
                />
              </label>
            ))}
            <label className="block text-sm">
              Job description
              <textarea
                name="description"
                required
                minLength={50}
                maxLength={30000}
                rows={5}
                className="input-dark mt-1"
              />
            </label>
            <button disabled={busy} className="btn-primary">
              Publish job
            </button>
          </form>
        </details>
      )}
      <label className="block text-sm">
        Search jobs
        <input
          className="input-dark mt-1"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Title, skill, company or location"
        />
      </label>
      <div className="space-y-3">
        {visible.length === 0 && (
          <p className="text-slate-400">
            {candidate
              ? "No open jobs match your search."
              : "Post your first job to begin collecting applications."}
          </p>
        )}
        {visible.map((j) => (
          <article key={j.id} className="glass rounded-2xl p-5 space-y-3">
            <h2 className="text-lg font-semibold">{j.title}</h2>
            <p className="text-slate-400 text-sm">
              {j.company} · {j.location} · {j.status}
            </p>
            <p className="text-sm whitespace-pre-wrap">{j.description}</p>
            <p className="text-sm text-teal-300">
              {j.required_skills.join(" · ")}
            </p>
            {candidate ? (
              <div className="space-y-3">
                <div className="flex gap-3 flex-wrap">
                  <button
                    disabled={busy || applied.has(j.id)}
                    className="btn-primary"
                    onClick={() =>
                      action(() =>
                        api.post(`/jobs/${j.id}/apply`, { cover_note: "" }),
                      )
                    }
                  >
                    {applied.has(j.id) ? "Applied" : "Apply with my profile"}
                  </button>
                  <button
                    disabled={busy}
                    className="btn-secondary"
                    onClick={() =>
                      action(async () => {
                        const r = await api.get(`/jobs/${j.id}/match`);
                        setMatch((m) => ({ ...m, [j.id]: r.data }));
                      })
                    }
                  >
                    Check skill coverage
                  </button>
                </div>
                <p className="text-xs text-slate-400">
                  Applying shares your profile with this job's recruiter,
                  including when your profile is private.
                </p>
                {match[j.id] && (
                  <div className="text-sm space-y-2">
                    <p>
                      Skill coverage: {match[j.id].score}/100.{" "}
                      {match[j.id].method}
                    </p>
                    <p>
                      Missing skills:{" "}
                      {match[j.id].skill_gap
                        .filter((g) => g.status === "missing")
                        .map((g) => g.skill)
                        .join(", ") || "None listed"}
                    </p>
                    <ul className="text-xs text-slate-300 list-disc pl-5 space-y-1">
                      {match[j.id].suggestions?.map((suggestion) => (
                        <li key={suggestion}>{suggestion}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex gap-2 flex-wrap">
                  <button
                    className="btn-primary"
                    disabled={busy}
                    onClick={() =>
                      action(async () => {
                        const response = await api.post(`/jobs/${j.id}/rank-applicants`);
                        setApplicantRanks((current) => ({ ...current, [j.id]: response.data }));
                      })
                    }
                  >
                    Rank applicants
                  </button>
                  {j.status === "open" && (
                    <button
                      className="btn-secondary"
                      disabled={busy}
                      onClick={() => action(() => api.patch(`/jobs/${j.id}`))}
                    >
                      Close applications
                    </button>
                  )}
                </div>
                {applicantRanks[j.id] && (
                  <div className="rounded-xl border border-teal-500/20 bg-teal-500/5 p-3 text-sm space-y-2">
                    <p className="font-medium text-teal-200">{applicantRanks[j.id].message}</p>
                    {applicantRanks[j.id].results?.map((rankedCandidate) => (
                      <p key={rankedCandidate.candidate_id} className="text-slate-300">
                        #{rankedCandidate.rank} {rankedCandidate.name} · {Math.round(rankedCandidate.composite_score)}/100
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
      <h2 className="text-xl font-semibold">
        {candidate ? "My applications" : "Applicant pipeline"}
      </h2>
      {applications.length === 0 && (
        <p className="text-slate-400">No applications yet.</p>
      )}
      {applications.map((a) => (
        <article className="glass rounded-2xl p-5 space-y-3" key={a.id}>
          <h3 className="font-semibold">
            {a.title} · {a.company}
          </h3>
          <p className="text-sm">
            {candidate ? "Your status" : a.name}:{" "}
            <strong className="text-teal-300">{a.stage}</strong>
          </p>
          {!candidate && (
            <>
              <p className="text-sm text-slate-400">
                {a.current_title} · {a.skills.join(", ")}
              </p>
              <div className="flex gap-2 flex-wrap">
                {(transitions[a.stage] || []).map((stage) => (
                  <button
                    disabled={busy}
                    className="btn-secondary"
                    key={stage}
                    onClick={() =>
                      action(() =>
                        api.patch(`/applications/${a.id}`, { stage }),
                      )
                    }
                  >
                    Move to {stage}
                  </button>
                ))}
              </div>
              <form
                className="flex flex-col sm:flex-row gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = e.currentTarget;
                  const body = new FormData(f).get("note");
                  action(async () => {
                    await api.post(`/applications/${a.id}/notes`, { body });
                    f.reset();
                  });
                }}
              >
                <input
                  aria-label="Internal recruiter note"
                  name="note"
                  required
                  maxLength={4000}
                  className="input-dark"
                  placeholder="Internal note (visible only to your workspace)"
                />
                <button disabled={busy} className="btn-secondary">
                  Save note
                </button>
              </form>
              {a.notes?.map((n) => (
                <p className="text-sm text-slate-400" key={n.id}>
                  {n.body}
                </p>
              ))}
              {["screened", "interview"].includes(a.stage) && (
                <details>
                  <summary className="text-sm cursor-pointer">
                    Schedule interview
                  </summary>
                  <form
                    className="space-y-2 mt-3"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const f = e.currentTarget;
                      const data = new FormData(f);
                      action(async () => {
                        await api.post(`/applications/${a.id}/interviews`, {
                          scheduled_at: new Date(
                            data.get("time"),
                          ).toISOString(),
                          meeting_url: data.get("url"),
                        });
                        f.reset();
                      });
                    }}
                  >
                    <label className="block text-sm">
                      Date and time (your local timezone)
                      <input
                        type="datetime-local"
                        name="time"
                        required
                        className="input-dark"
                      />
                    </label>
                    <label className="block text-sm">
                      Meeting link
                      <input
                        type="url"
                        pattern="https://.*"
                        name="url"
                        required
                        className="input-dark"
                      />
                    </label>
                    <button disabled={busy} className="btn-primary">
                      Schedule
                    </button>
                  </form>
                </details>
              )}
            </>
          )}
          {a.interviews?.map((i) => (
            <p className="text-sm" key={i.id}>
              Interview: {new Date(i.scheduled_at).toLocaleString()} ·{" "}
              <a
                className="text-teal-300 underline"
                href={i.meeting_url}
                target="_blank"
                rel="noreferrer"
              >
                Meeting link
              </a>
            </p>
          ))}
          <p className="text-xs text-slate-400">
            History:{" "}
            {a.events
              ?.map(
                (ev) =>
                  `${ev.stage} (${new Date(ev.created_at + "Z").toLocaleDateString()})`,
              )
              .join(" → ")}
          </p>
          {candidate &&
            !["hired", "rejected", "withdrawn"].includes(a.stage) && (
              <button
                disabled={busy}
                className="btn-secondary"
                onClick={() =>
                  action(() => api.post(`/applications/${a.id}/withdraw`))
                }
              >
                Withdraw application
              </button>
            )}
        </article>
      ))}
    </section>
  );
}
