import axios from "axios";

export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000, // 2 min for ranking (LLM calls are slow)
  withCredentials: true,
  headers: { "Content-Type": "application/json", "X-Prism-Client": "web" },
});

// ── Health & Stats ─────────────────────────────────────────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      !error.config?.url?.startsWith("/auth/")
    )
      window.dispatchEvent(new Event("prism-session-expired"));
    return Promise.reject(error);
  },
);
export const getMyProfile = () => api.get("/me/profile").then((r) => r.data);
export const rerankRun = (id) =>
  api.post(`/runs/${id}/rerank`).then((r) => r.data);
export const getHealth = () => api.get("/health").then((r) => r.data);
export const getStats = () => api.get("/stats").then((r) => r.data);

// ── Ranking ────────────────────────────────────────────────────────────────────
/**
 * POST /rank
 * @param {string} jd_text - Full job description
 * @param {object} weights - { semantic, skill, trajectory, behavioral, domain } (0-1 each)
 * @param {string|null} previous_run_id - Optional previous run ID for feedback re-ranking
 */
export const rankCandidates = ({ jd_text, weights, previous_run_id }) =>
  api.post("/rank", { jd_text, weights, previous_run_id }).then((r) => r.data);

// ── Candidates ─────────────────────────────────────────────────────────────────
export const getCandidates = (limit = 100, offset = 0) =>
  api.get("/candidates", { params: { limit, offset } }).then((r) => r.data);

export const getCandidateById = (id) =>
  api.get(`/candidates/${id}`).then((r) => r.data);

export const updateCandidate = (id, data) =>
  api.put(`/candidates/${id}`, data).then((r) => r.data);

// ── Feedback ───────────────────────────────────────────────────────────────────
/**
 * POST /feedback
 * feedback_type: 'strong_yes' | 'not_a_fit' | 'maybe'
 */
export const submitFeedback = ({
  run_id,
  candidate_id,
  feedback_type,
  notes = "",
}) =>
  api
    .post("/feedback", { run_id, candidate_id, feedback_type, notes })
    .then((r) => r.data);

// ── Export ─────────────────────────────────────────────────────────────────────
export const getExportUrl = (run_id) => `${API_BASE_URL}/export/${run_id}`;

export const downloadExport = async (run_id) => {
  const { data } = await api.get(`/export/${run_id}`, { responseType: "blob" });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `prism_ranked_${run_id.slice(0, 8)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

export const getAnalytics = () => api.get("/analytics").then((r) => r.data);

// ── Runs history ───────────────────────────────────────────────────────────────
export const getRuns = (limit = 50) =>
  api.get("/runs", { params: { limit } }).then((r) => r.data);

export const clearRuns = () => api.delete("/runs").then((r) => r.data);

export const getRunResults = (run_id) =>
  api.get(`/runs/${run_id}/results`).then((r) => r.data);

// ── Upload ─────────────────────────────────────────────────────────────────────
export const uploadCandidates = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  return api
    .post("/candidates/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
};

export const analyzeJd = (jd_text) =>
  api.post("/jd/analyze", { jd_text }).then((r) => r.data);

export const analyzeJdFile = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  return api
    .post("/jd/analyze/file", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
};

export const searchCandidates = (q, limit = 50) =>
  api.get("/candidates/search", { params: { q, limit } }).then((r) => r.data);

export const getInterviewQuestions = (candidate_id, parsed_jd) =>
  api
    .post(`/candidates/${candidate_id}/interview-questions`, { parsed_jd })
    .then((r) => r.data);

export const scanJdBias = (jd_text) =>
  api.post("/jd/bias-scan", { jd_text }).then((r) => r.data);

export default api;
