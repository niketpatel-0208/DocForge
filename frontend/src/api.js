import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: BASE });

// ── Inject GitLab token from localStorage into every request ─────────────────
api.interceptors.request.use((config) => {
  const gitlabToken = localStorage.getItem('docforge_gitlab_token') || '';
  if (gitlabToken) config.headers['X-GitLab-Token'] = gitlabToken;
  // LiteLLM key is always read from server .env – no client-side key needed
  return config;
});

// ── Auth ─────────────────────────────────────────────────────────────────────

/**
 * Validate a GitLab PAT and optionally resolve a repo URL in one shot.
 * Returns { ok, user, username, project_id?, project_name?, project_path? }
 */
export const validateAuth = (gitlab_token, repo_url = '') => {
  localStorage.setItem('docforge_gitlab_token', gitlab_token);
  return api
    .post('/auth/validate', { gitlab_token, repo_url })
    .then((r) => r.data);
};

export const clearAuth = () => {
  localStorage.removeItem('docforge_gitlab_token');
  localStorage.removeItem('docforge_repo_url');
};

export const hasStoredAuth = () => {
  return !!(localStorage.getItem('docforge_gitlab_token'));
};

export const getStoredRepoUrl = () =>
  localStorage.getItem('docforge_repo_url') || '';

export const setStoredRepoUrl = (url) =>
  localStorage.setItem('docforge_repo_url', url);

// ── Repo resolution (URL → project metadata) ─────────────────────────────────

/**
 * Given a full GitLab repo URL and a PAT, resolve the project metadata.
 */
export const resolveRepo = (repo_url, gitlab_token) =>
  api.post('/repos/resolve', { repo_url, gitlab_token }).then((r) => r.data);

// ── Repos list (legacy, kept for compat) ─────────────────────────────────────

export const listRepos = (search = '', page = 1) =>
  api.get('/repos', { params: { search, page } }).then((r) => r.data);

// ── Scan & Routes ─────────────────────────────────────────────────────────────

export const scanRepo = (id, forceRescan = false) =>
  api
    .get(`/repos/${id}/scan`, { params: { force_rescan: forceRescan } })
    .then((r) => r.data);

export const getRoutes = (id, wholeFile = false, forceRescan = false) =>
  api
    .get(`/repos/${id}/routes`, {
      params: { whole_file_mode: wholeFile, force_rescan: forceRescan },
    })
    .then((r) => r.data);

// ── Generate – full scan mode (project_id already known) ─────────────────────

export const generateApiDoc = (endpoint, project_id) =>
  api
    .post('/generate/api', { endpoint, project_id })
    .then((r) => r.data);

// ── Generate – targeted mode (repo URL + PAT + controller/endpoint hints) ────

/**
 * Targeted doc generation.
 * @param {string} repo_url        Full GitLab repo URL
 * @param {string} gitlab_token    Personal Access Token
 * @param {string} controller_file Relative path hint (optional if endpoint_name given)
 * @param {string} endpoint_name   Endpoint path/name hint (optional if controller_file given)
 */
export const generateApiDocTargeted = (
  repo_url,
  gitlab_token,
  controller_file = '',
  endpoint_name = ''
) =>
  api
    .post('/generate/api/targeted', {
      repo_url,
      gitlab_token,
      controller_file,
      endpoint_name,
    })
    .then((r) => r.data);

// ── Score ─────────────────────────────────────────────────────────────────────

export const scoreDoc = (yaml_content, use_claude = false) =>
  api.post('/score', { yaml_content, use_claude }).then((r) => r.data);

// ── SOP ───────────────────────────────────────────────────────────────────────

export const generateSop = (project_id) =>
  api.post('/generate/sop', { project_id }).then((r) => r.data);

// ── Stats ─────────────────────────────────────────────────────────────────────

export const getStats = () => api.get('/stats').then((r) => r.data);

// ── Export URLs ───────────────────────────────────────────────────────────────

export const exportYamlUrl = (project_id, doc_id) =>
  `${BASE}/export/yaml/${project_id}/${doc_id}`;

export const exportSopUrl = (project_id, doc_id) =>
  `${BASE}/export/sop/${project_id}/${doc_id}`;

// ── Cache management ──────────────────────────────────────────────────────────

export const clearCache = (project_id) =>
  api.delete(`/cache/${project_id}`).then((r) => r.data);