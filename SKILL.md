---
name: docforge
description: >
  Generates production-grade OpenAPI 3.0 YAML specifications from Go or PHP GitLab
  source code using LLM analysis. Use when a user needs to document a REST API endpoint,
  wants to generate endpoint-specific or full-repository API documentation, or needs a
  compliance-scored OpenAPI spec. DocForge finds the controller, route registration, and
  model/struct files automatically, assembles them as context, and targets 80%+ on a
  22-criteria quality rubric.
license: Proprietary
compatibility: >
  Requires Python 3.12+, Node.js 18+, a GitLab instance with API v4, and a LiteLLM
  proxy for Claude Sonnet. LLM key is server-side only. Users supply a GitLab PAT
  with read_api and read_repository scopes.
metadata:
  author: indiamart
  version: "3.0"
  stack: FastAPI, React 18, Claude Sonnet 4.6, GitLab API v4
  languages: Go, PHP
  frameworks: Gin, Echo, Chi, net/http, Mux, Laravel
---

# DocForge

Generate a scored, publish-ready OpenAPI 3.0 YAML from any GitLab repository in under
5 minutes by providing a repo URL, a GitLab PAT, and either a controller file path or
an endpoint name.

## Prerequisites

- GitLab Personal Access Token with `read_api` and `read_repository` scopes
- LiteLLM API key set in `backend/.env` as `LITELLM_API_KEY`
- Python 3.12+ (backend) and Node.js 18+ (frontend)

See [references/SETUP.md](references/SETUP.md) for installation steps.

## Usage — Targeted Mode (recommended)

Targeted mode finds only the files relevant to the specific endpoint you want to document.

**Step 1 — Connect**

Provide the full GitLab repository HTTPS URL and your PAT on the Setup screen. DocForge
resolves the project and carries the credentials forward — you will not be asked again.

**Step 2 — Enter a search hint**

In the DocManager, select **Path / Endpoint Specific** and fill in at least one field:

- `Controller / Handler File Path` — relative path from repo root, e.g. `controllers/sms.go`
  Partial names work: `sms` or `smsController` are both valid.
- `Endpoint Name / Path` — the route path or handler name, e.g. `/sms`, `SendSms`, `/api/gen`

**Step 3 — Generate**

Click **Generate Doc**. DocForge will:

1. Locate the controller file (4-phase search: Search API → dir walk → scoring → full tree)
2. Find the route registration file that references the handler function (same-service tree only)
3. Extract the HTTP method and path from the route file
4. Find model/struct files containing request and response field definitions
5. Assemble all files as labelled sections and send to Claude Sonnet
6. Return an OpenAPI 3.0 YAML scored against the 22-criteria rubric

The search trace shows every file found and why.

**Step 4 — Review and export**

- **YAML tab** — edit the generated spec in-browser, click Re-score at any time
- **Score tab** — see YES/NO/PARTIAL for each of the 22 criteria with quick-fix hints
- **Download** — saves as `{repo}-{endpoint}.yaml`
- **Open in Swagger Editor** — copies YAML to clipboard and opens editor.swagger.io

## Usage — Full Repo Scan Mode

Select **Full Repo Scan** in the DocManager (requires a repo URL from Setup).

DocForge will:
1. Walk the entire repository tree (paginated, up to 5,000 files)
2. Prioritise route registration files (main, router, server, app, api, handler)
3. Parse all Go and PHP router registrations and deduplicate by (method, path)
4. Display a clean endpoint list — click **Generate** on any row
5. Run the same context-gathering pipeline as targeted mode before calling the LLM

## Key behaviours

**Same-service-tree enforcement**
Route and model files are restricted to the same top-level service directory as the
controller. In a monorepo, files from other services are rejected regardless of score.
See [references/SEARCH.md](references/SEARCH.md) for details.

**Field extraction from struct tags**
The LLM is explicitly instructed to read `json:` struct tags for field names,
`binding:"required"` for mandatory fields, and `omitempty` for optional fields.
Guessing from variable names is prohibited.

**Error responses from source literals**
Every `if/else` error return in the handler generates one response example using the
actual error string from the source code.

**Deduplication**
Full-scan routes are deduplicated by `(method.upper(), path)` before display.

## Scoring

Every generated document is scored against 22 criteria before the developer sees it.
See [assets/rubric.md](assets/rubric.md) for the complete rubric.

Score ranges:
- 80–100% — publication-ready
- 60–79% — good foundation, review the quick-fix list
- 40–59% — key sections missing
- < 40% — significant gaps

## Supported languages and frameworks

| Language | Frameworks |
|---|---|
| Go | Gin, Echo, Chi, net/http, Gorilla Mux |
| PHP | Laravel (all HTTP verbs) |

## Reference files

- [references/SETUP.md](references/SETUP.md) — local installation and .env configuration
- [references/SEARCH.md](references/SEARCH.md) — 4-phase file search and same-service-tree logic
- [references/PROMPTS.md](references/PROMPTS.md) — LLM prompt templates and extraction rules
- [assets/rubric.md](assets/rubric.md) — full 22-criteria compliance rubric
- [scripts/score_yaml.py](scripts/score_yaml.py) — standalone YAML scorer (CLI)