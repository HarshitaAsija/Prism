import React from 'react';
export default function LoadingPipeline() {
  return <div role="status" aria-live="polite" className="glass rounded-2xl p-8 text-center space-y-3">
    <div className="w-8 h-8 mx-auto border-2 border-teal-500/30 border-t-teal-400 rounded-full animate-spin" />
    <h2 className="text-xl font-semibold">Ranking candidates</h2>
    <p className="text-sm text-slate-400">Analyzing the job, matching profiles, and preparing explanations. This may take up to two minutes.</p>
  </div>;
}
