import React, { useCallback, useEffect, useState, lazy, Suspense } from "react";
import { getMyProfile, updateCandidate } from "../../api/client";
import ProfileBuilder from "./ProfileBuilder";
import ResumeAnalyzer from "./ResumeAnalyzer";
import ProgressRing from "../../components/ProgressRing";
const HiringWorkspace = lazy(() => import("../HiringWorkspace"));
const formatProfile = (p) => ({
  ...p,
  title: p.current_title || "",
  experienceYears: p.years_experience || 0,
  skills: p.skills || [],
  certifications: p.certifications || [],
});
export default function CandidateHome() {
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("profile");
  const load = useCallback(async () => {
    setError("");
    try {
      setProfile(formatProfile(await getMyProfile()));
    } catch {
      setError("Unable to load your profile. Please try again.");
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);
  async function save(data) {
    try {
      const result = await updateCandidate(profile.id, data);
      setProfile(formatProfile(result.candidate));
      setTab("profile");
      setError("");
    } catch {
      setError("Profile could not be saved. Please try again.");
    }
  }
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Your candidate workspace</h1>
        <p className="text-sm text-slate-400 mt-2">
          Manage your profile, find jobs, and track your applications.
        </p>
      </div>
      <nav className="flex gap-2 flex-wrap" aria-label="Candidate workspace">
        {[
          ["profile", "Profile"],
          ["builder", "Edit profile"],
          ["resume", "Upload resume"],
          ["jobs", "Jobs and applications"],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={tab === id ? "btn-primary" : "btn-secondary"}
            aria-current={tab === id ? "page" : undefined}
          >
            {label}
          </button>
        ))}
      </nav>
      {error && (
        <div role="alert" className="text-red-400">
          {error}{" "}
          <button className="underline" onClick={load}>
            Retry
          </button>
        </div>
      )}
      {tab === "jobs" ? (
        <Suspense fallback={<p>Loading jobs...</p>}>
          <HiringWorkspace />
        </Suspense>
      ) : !profile ? (
        <p role="status">Loading profile...</p>
      ) : (
        <>
          {tab === "builder" && (
            <ProfileBuilder profile={profile} onSave={save} />
          )}
          {tab === "resume" && (
            <ResumeAnalyzer
              onAnalysisFinished={async () => {
                await load();
                setTab("profile");
              }}
            />
          )}
          {tab === "profile" && (
            <section className="glass rounded-2xl p-6 space-y-5">
              <div className="flex gap-5 items-center">
                <ProgressRing
                  value={Math.round((profile.profile_completeness || 0) * 100)}
                />
                <div>
                  <h2 className="text-xl font-bold">{profile.name}</h2>
                  <p className="text-slate-400">
                    {profile.title || "Add your professional title"}
                  </p>
                  <p className="text-sm mt-2">
                    Profile completeness:{" "}
                    {Math.round((profile.profile_completeness || 0) * 100)}%
                  </p>
                </div>
              </div>
              <p className="text-sm text-slate-400">
                Completeness measures filled profile fields. To see skill gaps,
                choose an actual job in Jobs and applications.
              </p>
              <p>Experience: {profile.experienceYears} years</p>
              <p>Skills: {profile.skills.join(", ") || "Add your skills"}</p>
              <p>
                Certifications:{" "}
                {profile.certifications.join(", ") || "None added"}
              </p>
              <label className="flex gap-3 items-start text-sm">
                <input
                  type="checkbox"
                  checked={profile.visibility === "public"}
                  onChange={(e) =>
                    save({
                      visibility: e.target.checked ? "public" : "private",
                    })
                  }
                />
                <span>
                  Let recruiters discover my profile. Private profiles are
                  shared only when I apply to a job.
                </span>
              </label>
              <div className="flex gap-4">
                {["github", "linkedin"].map(
                  (key) =>
                    profile[key] && (
                      <a
                        key={key}
                        className="text-teal-300 underline"
                        href={profile[key]}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {key}
                      </a>
                    ),
                )}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
