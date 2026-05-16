# DocForge — AI-Powered API Documentation Generator

## Description

DocForge is an intelligent API documentation tool that reads Go and PHP source code from GitLab repositories and generates production-grade OpenAPI 3.0 YAML specifications using LLM analysis. It targets an **82%+ compliance score** against a strict 22-criteria evaluation rubric — matching the quality bar of professionally written API documentation.

DocForge also generates deployment SOPs from infrastructure files (Dockerfiles, K8s manifests, shell scripts) and includes a built-in Swagger UI previewer for immediate doc validation.

## Core Capabilities

### 1. Full Repository Scan
Scans an entire GitLab repository, parses Go (Gin, Echo, Chi, net/http) and PHP (Laravel) router registrations, extracts endpoint metadata, and generates comprehensive API docs for each endpoint.

### 2. Targeted File Generation (Token-Efficient Mode)
Instead of scanning the full repo, specify a single controller file path and optionally an endpoint path. Only that file is sent to the LLM — **~90% fewer tokens** while maintaining the same doc quality.

### 3. 22-Criteria Compliance Scoring
Every generated doc is scored against the same 22-question rubric used by the official API doc evaluation tool:
- Q1–Q2: HTTP method semantics, endpoint path clarity
- Q3: Production + Dev/Stage server URLs
- Q4–Q10: Request body — content types, data types, required status, descriptions, examples, defaults, enum constraints
- Q11–Q19: Response — content types, schema types, descriptions, examples, 2xx/4xx/5xx coverage, enums, consistency via `$ref`
- Q20–Q22: Security scheme, schema reuse, versioning

### 4. SOP Generation
Generates structured Standard Operating Procedure documents from Dockerfiles, Kubernetes manifests, and deployment scripts.

### 5. Swagger UI Preview
Built-in structured YAML previewer showing servers, endpoints, request parameters, and response codes. One-click link to Swagger Editor for full interactive preview.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  Setup → RepoList → DocManager → DocDetail          │
│  (Auth)   (Browse)   (Scan/Target) (Preview/Score)  │
└───────────────────────┬─────────────────────────────┘
                        │ HTTP + Auth Headers
┌───────────────────────┴─────────────────────────────┐
│                FastAPI Backend (v2)                   │
│                                                      │
│  /auth/validate          ← Token validation          │
│  /repos                  ← GitLab repo listing       │
│  /repos/{id}/scan        ← Cached file scanning      │
│  /repos/{id}/routes      ← Cached route parsing      │
│  /generate/api           ← Full-scan doc generation  │
│  /generate/api/targeted  ← Single-file generation    │
│  /generate/sop           ← SOP from infra files      │
│  /score                  ← 22-criteria scoring       │
│  /export/yaml/{id}/{did} ← ZIP download              │
└──┬──────────────┬───────────────────┬───────────────┘
   │              │                   │
   ▼              ▼                   ▼
GitLab API   LLM (Claude)      Local Scorer
(scm.inter   (via LiteLLM      (22 checks,
mesh.net)    proxy)             YAML parsing)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Axios, js-yaml |
| Backend | Python 3.12, FastAPI, Uvicorn |
| LLM | Claude Sonnet 4.6 via LiteLLM proxy |
| SCM | GitLab API (scm.intermesh.net) |
| Parsing | Regex-based Go/PHP router detection |
| Scoring | YAML-based 22-criteria rubric engine |

## Key Design Decisions

1. **Handler source code as LLM context** — The full handler function source is sent to Claude alongside metadata, enabling accurate extraction of validation rules, response codes, and routing logic.

2. **Prompt engineering aligned to evaluation rubric** — The system prompt explicitly lists all 22 evaluation criteria and requires structured output matching professionally written sample docs (email.yaml, sms.yaml patterns).

3. **Caching to reduce token waste** — Scan and route results are cached server-side with configurable TTL. Frontend also caches routes in React refs. Navigating back and forth never triggers duplicate LLM calls.

4. **Per-request auth via headers** — Tokens sent as `X-GitLab-Token` and `X-LiteLLM-Key` headers on every request, stored in `localStorage`. Multiple users can use different tokens without server restart.

5. **Targeted generation for precision** — `POST /generate/api/targeted` accepts a single file path, fetches only that file, and generates docs from it — solving the token efficiency problem while maintaining accuracy.

## Setup & Usage

### Prerequisites
- Python 3.12+
- Node.js 18+
- GitLab PAT with `read_api`, `read_repository` scope
- LiteLLM API key for Claude access

### Quick Start

```bash
# Backend
cd backend
python -m venv venv
.\venv\Scripts\activate     # Windows
pip install -r requirements.txt
# Edit .env with your LITELLM_API_KEY
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm start
```

### Environment Variables (backend/.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `LITELLM_BASE_URL` | LLM proxy endpoint | `https://imllm.intermesh.net` |
| `LITELLM_API_KEY` | API key for Claude | (required) |
| `LLM_MODEL` | Model identifier | `anthropic/claude-sonnet-4-6` |
| `ALLOWED_ORIGINS` | CORS allowed origins | `http://localhost:3000` |
| `CACHE_TTL_SECONDS` | Scan cache duration | `600` |

## Example Output Quality

Generated docs follow the structure of professionally written API documentation:
- Rich `info.description` with access control, key behavior, kibana buckets, consumers
- `components/schemas` with typed, described, enum'd response properties
- `components/examples` with named `$ref` entries per response code
- `requestBody` properties with descriptions, examples, defaults, and enum constraints
- Consistent response structure via shared schema references

## Metrics

| Metric | Value |
|--------|-------|
| Average doc generation time | ~15-25 seconds per endpoint |
| Target compliance score | 80%+ (22 criteria) |
| Token savings (targeted mode) | ~90% vs full scan |
| Supported languages | Go, PHP |
| Supported frameworks | Gin, Echo, Chi, net/http, Mux, Laravel |
