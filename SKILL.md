---
name: docforge
description: >
  Generates production-grade OpenAPI 3.0 YAML specifications and deployment SOPs from GitLab
  source code using LLM analysis. Use when a user needs to document a REST API from Go (Gin,
  Echo, Chi, net/http, Mux) or PHP (Laravel) source code, wants to generate endpoint-specific
  or full-repository API documentation, needs a compliance-scored OpenAPI spec, or wants to
  produce a Standard Operating Procedure from infrastructure files (Dockerfiles, K8s manifests,
  shell scripts). DocForge resolves GitLab repositories by URL, performs intelligent file
  search using the GitLab Search API, collects controller + route registration + model/struct
  files, and generates documentation that targets 80%+ on a strict 22-criteria evaluation rubric.
license: Proprietary
compatibility: >
  Requires Python 3.12+, Node.js 18+, access to a GitLab instance (scm.intermesh.net by default),
  and a LiteLLM proxy endpoint for Claude Sonnet. Backend LLM key is pre-configured server-side.
  Users need only a GitLab Personal Access Token with read_api and read_repository scopes.
metadata:
  author: indiamart
  version: "3.0"
  stack: "FastAPI, React 18, Claude Sonnet via LiteLLM, GitLab API v4"
  languages: "Go, PHP"
  frameworks: "Gin, Echo, Chi, net/http, Mux, Laravel"
---

# DocForge — AI-Powered API Documentation Generator

DocForge reads Go and PHP source code from GitLab repositories and generates production-grade
OpenAPI 3.0 YAML specifications using Claude Sonnet via LiteLLM. Every generated document is
scored against a strict 22-criteria compliance rubric targeting 80%+ accuracy — matching the
quality bar of professionally authored API documentation.

## How It Works

### Step 1 — Connect
The user provides a GitLab repository URL and Personal Access Token (PAT). DocForge resolves the
project metadata via the GitLab API and carries the session credentials forward so they are never
asked again during the session.

### Step 2 — Choose Mode

**Targeted Mode (recommended)**
The user supplies either:
- A relative controller file path (e.g. `controllers/smsController.go`), or
- An endpoint name/path (e.g. `/sms`, `sendSms`, `SmsController`)

DocForge then executes a 4-phase intelligent search:
1. GitLab Search API blob search for each token extracted from the hint
2. Directory walk of common controller directories (`controllers/`, `handlers/`, `internal/`, `src/`, etc.)
3. Candidate ranking using basename match, controller keyword bonus, and depth penalty scoring
4. Same-service-tree enforcement — route and model files are only collected from within the same top-level service directory as the controller, preventing cross-service contamination

After finding the controller file, `gather_endpoint_context()` collects:
- The **route registration file** (searches for handler function names; scores by handler reference match + route filename pattern)
- The **HTTP method and path** extracted from the route file using regex patterns for Gin/Echo/Chi/net-http/Mux/Laravel
- Up to 4 **model/struct files** (same-service tree, searched by `type StructName struct` definitions, sibling package files, and standard model directories)

All collected files are assembled as labelled sections and sent to the LLM:
```
=== ROUTE REGISTRATION FILE: src/service/ShortUrl/mainShortUrl.go ===
...
=== CONTROLLER/HANDLER FILE: src/service/Controllers/centralizedURL.go ===
...
=== MODEL/STRUCT FILE: src/service/Models/urlRequest.go ===
...
```

**Full Repo Scan Mode**
Scans the entire repository (paginated, up to 5000 files), prioritizes route registration files
(filenames matching `main`, `route`, `router`, `server`, `app`, `api`, `handler`), parses all Go
and PHP router registrations, deduplicates endpoints by `(method, path)`, and lists them for
one-click doc generation. Each generate call also invokes `gather_endpoint_context()` for the
same multi-file accuracy as targeted mode.

### Step 3 — Generate
The LLM receives:
- All collected source files with section labels
- Explicit instructions to extract exact field names from `json:` struct tags
- Instructions to classify mandatory fields via `binding:"required"` / `validate:"required"` tags
- Instructions to classify optional fields via `json:",omitempty"` or absence of binding tags
- Instructions to extract HTTP method and path from the route file (not to guess)
- A complete example of expected output quality matching the 22-criteria rubric
- Max output: 12,000 tokens to handle large multi-file contexts

### Step 4 — Review and Export
The generated YAML is displayed in an editable textarea with syntax highlighting. Users can:
- Re-score against the 22-criteria rubric at any time
- Copy YAML to clipboard
- Download as a `.yaml` file (named `{repo}-{endpoint-path}.yaml`)
- Open in Swagger Editor (YAML is auto-copied to clipboard)

## 22-Criteria Compliance Rubric

| # | Criterion |
|---|-----------|
| Q1 | HTTP methods match operation semantics (read vs write) |
| Q2 | Endpoint paths clearly defined |
| Q3 | Production server URL present (not localhost, not TODO) |
| Q4 | Request content type explicitly specified |
| Q5 | Data types for all input parameters |
| Q6 | Required status on all request parameters |
| Q7 | Meaningful descriptions (>15 chars, not just field name) |
| Q8 | Example values on all parameters |
| Q9 | Default values for optional parameters |
| Q10 | ENUM on categorical/flag parameters |
| Q11 | Response content types specified |
| Q12 | Response schema properties have explicit types |
| Q13 | Response properties have meaningful descriptions |
| Q14 | Response examples present (2+ per status code) |
| Q15 | 2xx response schema documented |
| Q16 | 4xx response schema documented |
| Q17 | 5xx response schema documented |
| Q18 | ENUM on categorical response fields |
| Q19 | Consistent response structure via shared `$ref` |
| Q20 | Security scheme defined |
| Q21 | Schemas in `components`, reused via `$ref` |
| Q22 | Version info present |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/validate` | Validate GitLab PAT + optionally resolve repo URL |
| POST | `/repos/resolve` | Resolve project metadata from full repo URL |
| GET | `/repos/{id}/scan` | Paginated full-repo file scan (cached) |
| GET | `/repos/{id}/routes` | Parse + deduplicate routes (cached) |
| POST | `/generate/api` | Full-scan doc generation with context gathering |
| POST | `/generate/api/targeted` | URL + PAT + controller/endpoint hint → doc |
| POST | `/score` | Score YAML against 22-criteria rubric |
| GET | `/export/yaml/{id}/{doc_id}` | Download generated YAML |

## Architecture

```
React Frontend (Setup → DocManager → DocDetail)
        │
        │ HTTPS + X-GitLab-Token header
        ▼
FastAPI Backend (v3)
   ├── GitLabClient
   │     ├── search_blobs()          GitLab Search API (scope=blobs)
   │     ├── find_controller_file()  4-phase search with scoring
   │     ├── find_files_for_endpoint() token search + dir walk + full tree
   │     └── gather_endpoint_context() route + model file collection
   ├── go_parser / php_parser        Regex route extraction
   ├── normaliser                    Language-agnostic endpoint context
   ├── claude_client                 LiteLLM → Claude Sonnet 4.6
   └── scorer                        22-criteria YAML rubric engine
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LITELLM_BASE_URL` | LLM proxy endpoint | `https://imllm.intermesh.net` |
| `LITELLM_API_KEY` | API key for Claude (server-side only) | required |
| `LLM_MODEL` | Model identifier | `anthropic/claude-sonnet-4-6` |
| `ALLOWED_ORIGINS` | CORS origins | `http://localhost:3000` |
| `CACHE_TTL_SECONDS` | Scan/route cache TTL | `600` |

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
# Ensure backend/.env contains LITELLM_API_KEY
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd frontend
npm install
npm start
# Opens at http://localhost:3000
```

## Key Design Decisions

1. **Same-service-tree constraint** — Route and model files are restricted to the same top-level service directory as the controller (e.g. `src/centralizedService-go/`). This prevents cross-service file contamination in monorepos.

2. **Handler function name search** — After finding the controller, DocForge searches the repo for files that reference the handler's exported function names. This reliably locates the route registration file without needing a static analysis dependency.

3. **`json:` tag extraction instructions** — The LLM prompt explicitly instructs extraction of field names from struct tags, `binding:"required"` for mandatory fields, and `omitempty` for optional fields, producing accurate request body schemas.

4. **Deduplication** — Full-scan routes are deduplicated by `(method.upper(), path)` before returning, eliminating the duplicate endpoint issue seen with multi-file router registrations.

5. **LiteLLM key server-side only** — The API key never reaches the browser. Users authenticate only with their GitLab PAT.

6. **Session credential carry-forward** — Repo URL and PAT entered on the Setup screen are carried in React state to the DocManager, so the targeted form shows only the controller/endpoint hint fields without re-asking for credentials.

## Supported Languages and Frameworks

| Language | Frameworks |
|----------|-----------|
| Go | Gin, Echo, Chi, net/http, Gorilla Mux |
| PHP | Laravel (Route::get/post/put/patch/delete) |

## Metrics

| Metric | Value |
|--------|-------|
| Target compliance score | 80%+ (22 criteria) |
| Max LLM output tokens | 12,000 |
| Source context window | 30,000 chars |
| Route file priority keywords | main, route, router, server, app, api, handler |
| Model files collected per endpoint | up to 4 |
| Supported frameworks | Gin, Echo, Chi, net/http, Mux, Laravel |
| File search phases | 4 (search API → dir walk → full tree → fallback) |