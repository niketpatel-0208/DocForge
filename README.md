# ⚙ DocForge — AI-Powered API Documentation Generator

> **Generate publish-ready OpenAPI 3.0 API documentation directly from GitLab source code — in minutes, not hours.**

[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![React 18](https://img.shields.io/badge/React-18-61dafb.svg)](https://react.dev)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green.svg)](https://fastapi.tiangolo.com)
[![Claude Sonnet](https://img.shields.io/badge/LLM-Claude%20Sonnet%204.6-purple.svg)](https://anthropic.com)
[![OpenAPI 3.0](https://img.shields.io/badge/Spec-OpenAPI%203.0-orange.svg)](https://spec.openapis.org)

---

## 📋 Table of Contents

- [The Problem](#-the-problem)
- [The Solution](#-the-solution)
- [How It Works](#-how-it-works)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Local Setup](#-local-setup)
- [Usage Guide](#-usage-guide)
- [Doc Quality Scoring](#-doc-quality-scoring)
- [Metrics & Impact](#-metrics--impact)
- [Project Structure](#-project-structure)
- [Extending DocForge](#-extending-docforge)

---

## 🚨 The Problem

**Internal developer portals exist. Quality evaluation tools exist. But the documents themselves often don't.**

Engineering teams managing large numbers of microservices face a structural gap:

| Pain Point | Reality |
|---|---|
| **No automated doc pipeline** | No tooling connects source code repositories to documentation portals — the link has to be made manually |
| **Documentation quality is uneven** | Teams document differently; some endpoints are thorough, others have placeholder text or missing schemas |
| **Quality checks come too late** | Documentation quality is evaluated *after* publishing — by which point the effort to fix it is high |
| **Writing docs from scratch is slow** | Reading source code, inferring request/response shapes, and formatting valid OpenAPI YAML by hand takes significant time |
| **Docs go stale** | When code changes, documents rarely follow — there is no mechanism to flag drift |

The consequence: engineers integrating with undocumented or poorly documented services have to read source code directly, ask the owning team, or make assumptions — all of which slow down development and increase the chance of errors.

**DocForge is the missing upstream step.** It reads source code from a GitLab repository, generates a structured OpenAPI 3.0 draft, and pre-scores it against a 22-criteria quality rubric — before the developer even opens a documentation portal.

---

## 💡 The Solution

DocForge is a full-stack web application that:

1. **Connects to any GitLab repository** via a Personal Access Token — no additional access approvals needed
2. **Intelligently finds the right source files** — controller, route registration, and model/struct files — using the GitLab Search API and a 4-phase ranking algorithm
3. **Sends only the relevant files** (not the whole repo) to Claude Sonnet via a configured LiteLLM proxy
4. **Generates a production-grade OpenAPI 3.0 YAML** with accurate field names from struct tags, correct HTTP methods from route files, and realistic response examples extracted directly from the source
5. **Pre-scores the output** against a 22-criteria quality rubric, giving immediate feedback on what needs improvement
6. **Exports a `.yaml` file** ready for any OpenAPI-compatible tool or documentation portal

### What this changes

| Step | Without DocForge | With DocForge |
|---|---|---|
| Starting a new doc | Open a blank YAML file and read the source | Enter a repo URL and controller path |
| Getting the field names right | Manually trace through struct definitions | Extracted automatically from `json:` tags |
| Knowing what's missing | Find out after publishing when someone flags it | Pre-score shows gaps before you paste anything |
| Keeping up with code changes | Manual re-read and re-write | Drift is visible from commit-date comparison |

---

## 🔍 How It Works

### Targeted Mode (Recommended)

```
Engineer inputs: Repo URL + PAT + Controller file hint OR endpoint name
         ↓
1. Resolve GitLab project from URL (namespace → project ID)
         ↓
2. Find controller file (4-phase search)
   Phase 1: GitLab Search API blob search (exact filename + basename)
   Phase 2: Common controller directories (controllers/, handlers/, internal/, src/)
   Phase 3: Ranked candidate scoring (basename match + controller keyword bonus)
   Phase 4: Full paginated tree walk (fallback for non-standard structures)
         ↓
3. Gather endpoint context — same-service files only
   ├── Extract handler function names from controller source
   ├── Search repo for files referencing those function names → route registration file
   ├── Extract HTTP method + path from route file (Gin/Echo/Chi/Mux/Laravel patterns)
   ├── Extract struct names from controller source
   └── Find model/struct files in the same service directory tree
         ↓
4. Assemble multi-file context with labelled sections:
   "=== ROUTE REGISTRATION FILE === ... CONTROLLER FILE === ... MODEL FILE ==="
         ↓
5. LLM generation (Claude Sonnet via LiteLLM proxy)
   · Extract json: struct tags → exact field names
   · binding:"required" → mandatory fields
   · omitempty / no binding → optional fields
   · Every if/else error return → one response example with the actual error string
         ↓
6. Score against 22 criteria, return YAML + compliance percentage
```

### Full Repo Scan Mode

```
Engineer inputs: Repo URL + PAT (resolved during Setup)
         ↓
1. Paginated recursive tree walk (100 files/page, up to 50 pages)
         ↓
2. Sort: route files first (filenames: main, router, server, app, api, handler)
         ↓
3. Parse all Go and PHP router registrations with regex
         ↓
4. Deduplicate by (HTTP method, path) key
         ↓
5. Display clean endpoint list → click Generate on any endpoint
         ↓
6. Same context-gathering + LLM pipeline as targeted mode
```

### Same-Service-Tree Constraint

In monorepos with many services, a naive file search can pull route files from **a completely different service** that happens to match the same keyword. DocForge prevents this by enforcing a service-tree boundary:

```
Given: controller at  src/ServiceA/Controllers/handler.go
                      └── service root: "src/ServiceA"

DocForge considers ONLY route and model files from within "src/ServiceA"
Files from "src/ServiceB/" are automatically rejected
```

This makes DocForge safe to run on large monorepos without cross-service contamination.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎯 **Targeted Search** | Find controller + route + model files from a single path or endpoint hint |
| 🔍 **Full Repo Scan** | Parse all endpoints across the entire repository, deduplicated |
| 🤖 **LLM Doc Generation** | Claude Sonnet generates detailed, standards-aligned OpenAPI 3.0 YAML |
| 📊 **22-Criteria Pre-scoring** | Every doc scored before publishing — see exactly what's missing |
| 🏗️ **Multi-file Context** | Route + controller + model files assembled for field-accurate documentation |
| 🚫 **No Cross-contamination** | Same-service-tree constraint prevents monorepo confusion |
| 📁 **YAML Export** | Download `.yaml` file named by repo + endpoint path |
| 🔗 **Swagger Editor** | One-click open in Swagger Editor (YAML auto-copied to clipboard) |
| 🔐 **Server-side LLM Key** | LiteLLM key stays on server — engineers only need their GitLab PAT |
| ⚡ **Session Carry-forward** | Repo URL + PAT entered once at login, reused throughout the session |
| 📝 **Editable Output** | YAML is editable in-browser with re-score on demand |
| 🧠 **Structured API Logging** | Every GitLab API call logged to `backend/logs/gitlab_api.log` |

---

## 🏛️ Architecture

![DocForge System Architecture](docforge_architetcure_diagram.png)

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Frontend** | React 18, Axios, js-yaml | Single-page app with dark glassmorphism UI |
| **Backend** | Python 3.12, FastAPI, Uvicorn | REST API server |
| **LLM** | Claude Sonnet 4.6 via LiteLLM proxy | Documentation generation |
| **SCM** | GitLab API v4 | Repository access + code search |
| **Parsing** | Regex-based (Go + PHP router patterns) | Route registration extraction |
| **Scoring** | Custom 22-criteria YAML engine | Pre-scores docs to mirror portal quality standards |
| **Logging** | Python `logging` → structured log files | GitLab API call tracing for debugging |

---

## 🚀 Local Setup

### Prerequisites

- **Python 3.12+**
- **Node.js 18+** and npm
- A **GitLab Personal Access Token** with `read_api` and `read_repository` scopes
- A **LiteLLM API key** configured by your team for Claude access

---

### Step 1 — Create a GitLab Personal Access Token (PAT)

DocForge reads source code from your GitLab instance on your behalf using a read-only token.

1. Log in to your GitLab instance
2. Click your **avatar icon** (top-right corner) to open the user menu
3. Click **Edit profile** from the dropdown
4. In the **User Settings** left sidebar, click **Access Tokens**
5. On the right side under **Add a personal access token**, fill in:
   - **Token name:** `docforge` (or any descriptive name)
   - **Expiration date:** Set an appropriate future date (`YYYY-MM-DD`)
   - **Select scopes:** Check **`read_api`** and **`read_repository`** only
6. Scroll down and click **Create personal access token**
7. **Copy the token immediately** — it is only shown once and cannot be retrieved again

> **Security:** DocForge never stores your PAT on the server. It is sent as an HTTP header on each request and lives only in your browser session memory.

---

### Step 2 — Clone the repository

```bash
git clone <your-docforge-repo-url>
cd DocForge
```

---

### Step 3 — Configure the backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv venv

# Windows
.\venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

#### Edit `backend/.env`

Open `backend/.env` in any text editor:

```env
# ── LLM Configuration ──────────────────────────────────────────────────────
# Replace with the LiteLLM API key provided by your team
LITELLM_API_KEY=sk-YOUR_LITELLM_KEY_HERE

# Model identifier — change only if instructed
LLM_MODEL=anthropic/claude-sonnet-4-6

# ── Server Configuration ────────────────────────────────────────────────────
# CORS allowed origins — match your frontend URL
ALLOWED_ORIGINS=http://localhost:3000

# Cache scan/route results for this many seconds (600 = 10 minutes)
CACHE_TTL_SECONDS=600
```

> **The only required change is `LITELLM_API_KEY`.**  
> The proxy endpoint is pre-configured in the backend — do not expose or modify it.

#### Start the backend

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

---

### Step 4 — Start the frontend

Open a **new terminal**:

```bash
cd frontend
npm install
npm start
```

Opens at **[http://localhost:3000](http://localhost:3000)**

---

### Step 5 — Verify

1. Open [http://localhost:3000](http://localhost:3000)
2. Enter your GitLab PAT in the **Personal Access Token** field
3. Click **Connect & Generate Docs →**
4. You should see the **🎯 Path / Endpoint Specific** mode ready

---

### Troubleshooting

| Issue | Fix |
|---|---|
| `LITELLM_API_KEY not configured on server` | Open `backend/.env` and set `LITELLM_API_KEY` |
| `GitLab token invalid` | Ensure the PAT has `read_api` + `read_repository` scopes |
| `Could not resolve repository` | Use the full HTTPS URL, not SSH (e.g. `https://gitlab.yourcompany.com/group/project`) |
| `CORS error in browser console` | Check `ALLOWED_ORIGINS` in `backend/.env` matches your frontend URL |
| Frontend shows blank page | Run `npm install` inside the `frontend/` directory |
| `ModuleNotFoundError` in backend | Run `pip install -r requirements.txt` with the venv activated |

---

### View logs

```bash
# Every GitLab API call: URL, params, HTTP status, elapsed time
type backend\logs\gitlab_api.log

# App events: file search results, context gathering, endpoint resolution
type backend\logs\docforge.log
```

Log lines are structured as:
```
2026-05-16T12:21:38 | INFO    | docforge.gitlab | search_code query='Handler' → paths=[...]
```

---

## 📖 Usage Guide

### 🎯 Targeted Mode

Recommended for accuracy. Finds only the files relevant to your specific endpoint.

1. Select **🎯 Path / Endpoint Specific**
2. If you provided a repo URL during setup, a green **"Connected to …"** badge confirms credentials are carried forward — no need to re-enter them
3. Enter **at least one** of:
   - **Controller / Handler File Path** — relative path from repo root (e.g. `controllers/smsController.go`); partial names work
   - **Endpoint Name / Path** — e.g. `/sms`, `sendSms`, `/api/process`
4. Click **⚡ Generate Doc**
5. A **search trace** shows which files were found and used
6. Click **View Doc** to open the YAML and score

DocForge automatically finds:
- The controller file (from your hint or by searching the repo)
- The route registration file (where HTTP method + path are defined)
- Model/struct files (containing request/response field definitions)

### 🔍 Full Repo Scan Mode

Use when you want to see all endpoints in a repository at once.

1. Select **🔍 Full Repo Scan** (requires a repo URL to have been provided during setup)
2. Click **🔍 Scan Repository**
3. A deduplicated list of endpoints appears with method badges and handler names
4. Click **Generate** next to any endpoint

### 📄 Doc Detail View

| Tab | Description |
|---|---|
| **YAML** | Editable OpenAPI 3.0 YAML. Click **↻ Re-score** to refresh the compliance score |
| **Score** | Full 22-criteria breakdown with YES / NO / PARTIAL per criterion and improvement suggestions |

**Actions:**
- **📋 Copy YAML** — copies to clipboard
- **↓ Download** — saves as `{repo}-{endpoint}.yaml`
- **🔗 Open in Swagger Editor** — copies YAML and opens `editor.swagger.io`

---

## 📊 Doc Quality Scoring

Every generated document is scored against a **22-criteria compliance rubric** — the same criteria used by professional API documentation quality tools. The score gives an immediate, objective view of what is complete, what is partial, and what is missing.

### How scoring works

The scorer parses the generated OpenAPI YAML and checks each criterion with a `YES`, `NO`, or `PARTIAL` result. A percentage score is calculated from the weighted outcomes. Each failing criterion is accompanied by a specific, actionable quick-fix suggestion.

### The 22 Criteria

| # | Category | Criterion |
|---|---|---|
| Q1 | HTTP semantics | HTTP method matches operation intent (read operation → GET, write → POST/PUT/PATCH/DELETE) |
| Q2 | Endpoint definition | Endpoint paths are clearly and completely defined |
| Q3 | Server URL | At least one non-localhost, non-placeholder server URL is present |
| Q4 | Request content type | Request body content type is explicitly declared (`application/json`, `application/x-www-form-urlencoded`, etc.) |
| Q5 | Input types | Every request parameter and body field has an explicit data type |
| Q6 | Required status | Each request parameter is marked as required or optional |
| Q7 | Descriptions | All parameters have meaningful descriptions (not just the field name repeated) |
| Q8 | Examples | Example values are provided for every request parameter |
| Q9 | Defaults | Optional parameters have explicit default values documented |
| Q10 | Enums | Categorical or flag fields have an `enum` list of valid values |
| Q11 | Response content type | Response content types are explicitly declared |
| Q12 | Response schema types | Every response body property has an explicit data type |
| Q13 | Response descriptions | Response properties have meaningful descriptions |
| Q14 | Response examples | At least 2 named examples per response status code |
| Q15 | 2xx coverage | Successful response schema is fully documented |
| Q16 | 4xx coverage | At least one client error response (4xx) is documented with schema |
| Q17 | 5xx coverage | At least one server error response (5xx) is documented |
| Q18 | Response enums | Categorical response fields have enum constraints |
| Q19 | Schema consistency | Response schemas use `$ref` to shared `components/schemas` — not inlined |
| Q20 | Security scheme | A security scheme is defined in `components/securitySchemes` |
| Q21 | Schema reuse | All schemas defined in `components/schemas` and referenced via `$ref` |
| Q22 | Version | API version is present in the `info` block |

### Score interpretation

| Score range | Meaning |
|---|---|
| **80–100%** | Publication-ready. Meets professional API documentation standards. |
| **60–79%** | Good foundation. A few gaps — check the quick-fix list for specifics. |
| **40–59%** | Partial. Key sections may be missing or incomplete. Review Score tab carefully. |
| **< 40%** | Needs significant improvement. Likely missing request/response schemas or examples. |

The Score tab in DocDetail shows every criterion result individually, so you can see precisely which checks passed, which failed, and what to fix.

---

## 📈 Metrics & Impact

### The gap DocForge addresses

Across engineering organisations managing many microservices, documentation tends to fall behind code — not because engineers don't want to write it, but because the tooling to do it efficiently doesn't exist. Specifically:

- **No automated connection** exists between source code repositories and documentation portals — every doc must be written and published manually
- **Quality is checked after publishing**, not before — meaning low-quality docs reach consumers before anyone flags them
- **Writing valid OpenAPI YAML from scratch** requires knowing the exact field names, data types, required/optional status, and error response structure — all of which requires careful source reading

DocForge eliminates this by generating a scored first draft directly from source code, reducing the task from "write a document from scratch" to "review and publish a draft".

### What DocForge produces

- A valid OpenAPI 3.0 YAML with field names extracted from `json:` struct tags (not guessed)
- HTTP methods and paths extracted from the actual route registration file (not inferred from file names)
- Response examples derived from real error string literals in the source code
- A compliance score showing exactly which of the 22 quality criteria are met before any human review

### Scalability

| Dimension | Detail |
|---|---|
| **Repository size** | Handles up to 5,000 files via paginated GitLab API tree walk |
| **Concurrent users** | Stateless token auth — each request is independent, horizontally scalable |
| **Caching** | Server-side scan + route cache reduces repeat GitLab API calls significantly |
| **Token efficiency** | Targeted mode sends ~1–4 files vs the entire repo — far fewer LLM tokens than whole-repo approaches |
| **Language coverage** | Go (Gin, Echo, Chi, net/http, Mux) and PHP (Laravel) — extensible to additional languages |

### Solution Completeness

| Capability | Status |
|---|---|
| Go endpoint extraction | ✅ Full |
| PHP endpoint extraction | ✅ Full |
| Route registration file detection | ✅ Full |
| Model/struct file collection | ✅ Full |
| Same-service-tree enforcement | ✅ Full |
| Endpoint deduplication | ✅ Full |
| 22-criteria pre-scoring with actionable fixes | ✅ Full |
| YAML export as direct file download | ✅ Full |
| Structured GitLab API logging | ✅ Full |
| Session credential carry-forward | ✅ Full |
| Additional language support (Node.js, Python, Java) | 🔶 Extensible — one new parser file per language |
| Automated doc portal publishing | 🔶 Copy + Download always available |

### Solution Robustness

| Scenario | How DocForge handles it |
|---|---|
| Monorepo with many services | Same-service-tree constraint isolates the correct service |
| No route file found | Falls back to endpoint hint for path; controller source used directly |
| Parser finds 0 routes | Synthesises endpoint using method/path extracted from route file |
| Non-standard router patterns | "No routes detected" state with "Try whole-file mode" — never a crash |
| LLM returns malformed YAML | Parse warning banner shown; YAML pre-filled in editor for manual fix |
| Very large repos | Paginated tree walk (100 files/page, up to 50 pages) |
| File not found (404) | `get_file_safe()` returns empty string; processing continues gracefully |
| Duplicate endpoints in scan | Deduplicated by `(method, path)` key before display |

---

## 📁 Project Structure

```
DocForge/
├── README.md                           ← This file
├── SKILL.md                            ← Agent Skills metadata
├── backend/
│   ├── main.py                         ← FastAPI app, all REST endpoints (v3)
│   ├── gitlab_client.py                ← GitLab API client
│   │     ├── find_controller_file()    ← 4-phase controller search
│   │     ├── find_files_for_endpoint() ← Token search + dir walk + full tree
│   │     └── gather_endpoint_context() ← Route + model file collection
│   ├── go_parser.py                    ← Go router pattern extraction
│   ├── php_parser.py                   ← PHP Laravel route extraction
│   ├── infra_parser.py                 ← Dockerfile / K8s / shell parsing
│   ├── normaliser.py                   ← Language-agnostic EndpointContext builder
│   ├── claude_client.py                ← LiteLLM → Claude Sonnet; prompt templates
│   ├── scorer.py                       ← 22-criteria YAML compliance engine
│   ├── export.py                       ← YAML file packaging
│   ├── requirements.txt                ← Python dependencies
│   ├── .env                            ← Environment variables (edit LITELLM_API_KEY here)
│   └── logs/
│         ├── gitlab_api.log            ← Structured GitLab API call log
│         └── docforge.log              ← App event log
└── frontend/
      ├── package.json
      └── src/
            ├── App.js                  ← Root component, routing, session state
            ├── App.css                 ← Global styles (glassmorphism dark theme)
            ├── api.js                  ← Axios client, all API call functions
            └── pages/
                  ├── Setup.js          ← Connect screen (Repo URL + PAT)
                  ├── DocManager.js     ← Targeted + Full Scan modes
                  └── DocDetail.js      ← YAML editor + 22-criteria Score tab
```

---

## 🔧 Extending DocForge

### Add a new language (e.g. Python FastAPI)

1. Create `backend/fastapi_parser.py` with a `parse_fastapi_source(source, filename)` function returning `RouteInfo` objects
2. Import and call it in `main.py` `get_routes()` alongside `parse_go_files()`
3. Add `normalise_fastapi_routes()` in `normaliser.py`

### Change the LLM model

Edit `backend/.env`:
```env
LLM_MODEL=anthropic/claude-opus-4   # any model supported by your LiteLLM proxy
```

### Use a different GitLab instance

The GitLab base URL is parsed automatically from the repo URL you provide:
```
https://gitlab.yourcompany.com/group/project
→ API base: https://gitlab.yourcompany.com/api/v4
```

No `.env` change required — just provide the correct full repo URL in the UI.

---

## 📄 License

Proprietary — IndiaMART Intermesh Ltd.

---