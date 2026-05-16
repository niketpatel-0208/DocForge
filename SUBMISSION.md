# DocForge — Submission Form Content

---

## PROJECT TITLE

Tech Tantra Solution

---

## SHORT PITCH

DocForge reads Go and PHP source code from any GitLab repository, intelligently finds the controller, route, and model files for a specific endpoint, and generates a scored, publish-ready OpenAPI 3.0 specification in under 5 minutes — no manual YAML writing required.

---

## PROBLEM WE'RE SOLVING

Writing API docs from source code is slow, error-prone, and entirely manual — no tooling connects code repositories to documentation portals. Docs are written from scratch, quality is checked only after publishing, and they go stale the moment the code changes. DocForge automates this: it finds the right files, extracts the exact field names and response structures, and delivers a pre-scored draft in under 5 minutes.

---

## TECHNICAL JOURNEY / SKILL.MD

### What We Built

DocForge is a full-stack API documentation generator. It connects to any GitLab repository via a Personal Access Token, intelligently locates the source files relevant to a specific endpoint, assembles them as labelled multi-file context, and sends them to Claude Sonnet via a LiteLLM proxy to generate a production-grade OpenAPI 3.0 YAML. Every generated document is scored against a 22-criteria compliance rubric before the developer sees it.

**Stack:** React 18 frontend · FastAPI + Python 3.12 backend · Claude Sonnet 4.6 via LiteLLM proxy · GitLab API v4

---

### The Hardest Technical Problem: Finding the Right Files

The biggest challenge was not prompt engineering — it was reliably finding the correct set of source files across repositories of wildly varying structure.

A naive approach fails in two ways:
- Sending the whole repo is token-prohibitive and sends noise to the LLM
- Sending only the controller file misses the HTTP method and path (which live in the route registration file) and the exact field names (which live in the model or struct files)

We built a **4-phase file search system** inside `gitlab_client.py`:

**Phase 1 — GitLab Search API blob search**
Search for the controller filename using the GitLab Search API (`scope=blobs`). This resolves 80%+ of cases instantly without a tree walk.

**Phase 2 — Common directory walk**
If search does not resolve, walk known controller directories: `controllers/`, `handlers/`, `internal/`, `src/`, `api/`, and others.

**Phase 3 — Candidate scoring**
Rank all candidates using a scoring function: basename token match (+100), partial match (+50), controller keyword in path (+20), depth penalty (-1 per level). This handles non-standard naming conventions.

**Phase 4 — Full paginated tree walk**
As a last resort, walk the full repository tree paginated at 100 files per page. Ensures DocForge never silently fails.

---

### The Same-Service-Tree Constraint

The most subtle bug we solved: in a monorepo with multiple services, searching for a handler function name would find it in both the controller file AND in a completely different service's main file. The old code selected the wrong file and sent it to the LLM as the route file, resulting in a completely wrong HTTP method and path in the generated doc.

**The fix:** enforce a service-tree boundary. Extract the top-2-level directory path from the confirmed controller file. Only accept route and model file candidates from within that same directory prefix. Files from other services are rejected regardless of score.

Example: if the controller is at `src/ServiceA/Controllers/handler.go`, the service root is `src/ServiceA`. Any file from `src/ServiceB/` is automatically rejected — even if it scores higher on other criteria.

---

### gather_endpoint_context()

After finding the controller file, we gather all supporting files:

**Step 1 — Route registration file**
Extract all exported Go function names from the controller. Search for files that reference those names AND are in the same service tree. Score by handler function reference found (+50 points) and route or main filename pattern (+30 points). Parse the route file with regex patterns for Gin, Echo, Chi, Mux, net/http, and Laravel to extract the exact HTTP method and path.

**Step 2 — Model and struct files**
Extract struct names referenced in the controller source. Search for `type StructName struct` definitions within the same service tree. Also scan sibling files in the same package directory.

**Step 3 — Labelled assembly**
Combine all files as clearly labelled sections sent to the LLM:

```
=== ROUTE REGISTRATION FILE: src/ServiceA/main.go ===
=== CONTROLLER/HANDLER FILE: src/ServiceA/Controllers/url.go ===
=== MODEL/STRUCT FILE: src/ServiceA/Models/request.go ===
```

This gives the LLM the complete picture it needs for an accurate document.

---

### Prompt Engineering Decisions

The LLM prompt explicitly instructs Claude to:

- Extract field names from `json:` struct tags — not variable names
- Treat `binding:"required"` or `validate:"required"` as a mandatory field
- Treat `json:",omitempty"` or no binding tag as an optional field
- Turn every `if/else` error return in the handler into one response example with the actual error string literal from the source
- Never write TODO — infer from context and mark inferred values with a comment
- Write `info.description` as 30+ lines covering access control, key behavior, parameters, and output keys — matching the evaluation rubric exactly

Max LLM output: **12,000 tokens** · Source context window: **30,000 characters**

---

### 22-Criteria Scoring Engine

We built a local YAML parser that evaluates every generated document against 22 criteria matching the portal quality evaluation rubric. Each criterion returns YES, NO, or PARTIAL. A percentage score is calculated, and each failing criterion includes a specific quick-fix suggestion. This gives the developer actionable feedback before they open the portal — reducing the publish → evaluate → fix → republish cycle to a single iteration.

The 22 criteria cover: HTTP method semantics · endpoint path definition · server URL presence · request content type · input data types · required/optional status · meaningful descriptions · example values · default values · enum constraints · response content types · response schema types · response descriptions · response examples (min 2 per status code) · 2xx/4xx/5xx coverage · response enum constraints · schema consistency via `$ref` · security scheme definition · components reuse · API version.

---

### What We Own End-to-End

- `gitlab_client.py` — GitLab API client, 4-phase file search, context gathering (~800 lines)
- `main.py` — FastAPI backend, all REST endpoints, deduplication, server-side caching
- `go_parser.py` + `php_parser.py` — Regex route extraction for Go and PHP frameworks
- `normaliser.py` — Language-agnostic EndpointContext builder
- `claude_client.py` — LiteLLM proxy integration, prompt templates v3
- `scorer.py` — 22-criteria YAML compliance engine
- `frontend/src/` — React 18 SPA: Setup, DocManager (targeted + full scan), DocDetail (YAML editor, score tab, export)
- Structured logging to `backend/logs/gitlab_api.log` — DEBUG level for every GitLab API call

---

### Key Technical Decisions

| Decision | Rationale |
|---|---|
| Regex parsing over AST | Zero dependency on language toolchains; works on any server |
| GitLab Search API first | Avoids full tree walk for 80%+ of cases — faster, fewer API calls |
| Same-service-tree constraint | Prevents cross-service contamination in monorepos |
| Server-side LLM key | API key never reaches the browser; only GitLab PAT used client-side |
| Session credential carry-forward | PAT + repo URL entered once; React state passes to all components |
| Endpoint deduplication by (method, path) | Eliminates duplicates from multi-file route registration patterns |
| 12k output / 30k source tokens | Handles large multi-file contexts without truncation |

---

## SKILL FOLDER (GITHUB REPO)

https://github.com/niketpatel-0208/DocForge

Canonical layout in repo root:
- `SKILL.md` — Agent Skills metadata + full technical narrative
- `backend/` — All Python source: parser, client, scorer, normaliser, exporter
- `frontend/src/` — React 18 SPA
- `README.md` — Full setup and usage guide with architecture diagram
- `docforge_architetcure_diagram.png` — Architecture diagram

---

## DEMO VIDEO URL

[PASTE YOUR YOUTUBE / LOOM / VIMEO URL HERE]

**Demo structure (5–10 minutes):**

**0:00–1:30 — The problem**
Show a GitLab repository with no documentation. Open a controller file and show how much source reading a developer would need to write a doc by hand.

**1:30–4:00 — Targeted Mode live demo**
Enter a repo URL + PAT. Enter a controller file path. Click Generate. Show the search trace (which files were found). Show the generated YAML with correct field names and HTTP method. Show the 22-criteria score.

**4:00–6:00 — Full Repo Scan**
Show the deduplicated endpoint list. Click Generate on one endpoint. Show that doc quality matches targeted mode — route and model files found automatically.

**6:00–7:30 — Edge case**
Enter only a partial filename or just an endpoint name. Show DocForge finding the correct file. Show the same-service-tree constraint rejecting wrong-service files.

**7:30–9:00 — Score tab and export**
Walk through the 22 criteria results. Show a failing criterion with its quick-fix. Fix one field in the YAML editor. Re-score. Download the `.yaml` file.

**9:00–10:00 — Closing**
"5 minutes from source code to a scored, publish-ready API document."

---

## IMPACT ANALYSIS

### Who Benefits and How

**Direct users:** Backend engineers who own services and need to document them. DocForge removes the most time-consuming part — reading source code and formatting it into valid YAML — and replaces it with reviewing and publishing a draft.

**Indirect beneficiaries:** Engineers who consume APIs (frontend, mobile, integration partners) gain accurate, typed, example-rich documentation instead of reading source code or asking the owning team.

---

### What DocForge Actually Changes

| Task | Without DocForge | With DocForge |
|---|---|---|
| Starting a new doc | Blank YAML + source reading | Enter repo URL + controller path |
| Getting field names right | Manually trace struct definitions | Extracted from `json:` tags automatically |
| Checking quality | After publishing | Pre-score before opening the portal |
| Keeping docs current | Manual re-read when someone complains | Commit-date drift immediately visible |

---

### Scalability

- Works on any GitLab instance — API base URL is parsed automatically from the repo URL
- Handles up to 5,000 files per repository via paginated GitLab API tree walk
- Stateless token auth — horizontally scalable, no shared server state
- Targeted mode sends ~1–4 files vs the entire repo — minimal LLM token cost
- Adding a new language = one new parser file, no architectural changes

---

### Solution Completeness

| Capability | Status |
|---|---|
| Go endpoint extraction (Gin, Echo, Chi, net/http, Mux) | Complete |
| PHP endpoint extraction (Laravel) | Complete |
| Route + model file discovery with same-service-tree enforcement | Complete |
| Endpoint deduplication in full scan mode | Complete |
| 22-criteria pre-scoring with actionable quick fixes | Complete |
| YAML export as direct .yaml file download | Complete |
| Session credential carry-forward | Complete |
| Structured GitLab API logging at DEBUG level | Complete |
| Additional language support (Node.js, Python, Java) | Extensible — one new parser file per language |
| Automated doc portal publishing | Copy and Download always available |

---

### Solution Robustness

| Scenario | How DocForge handles it |
|---|---|
| Monorepo with many services | Same-service-tree constraint isolates the correct service |
| No route file found | Endpoint hint used as path fallback; controller source as sole LLM context |
| Parser finds zero routes | Endpoint synthesised from extracted method and path |
| Non-standard router pattern | "No routes detected" with "Try whole-file mode" — never a crash |
| LLM returns malformed YAML | Parse warning shown; YAML pre-filled in editor for manual fix |
| File not found (404) | Empty string returned safely; processing continues |
| Duplicate endpoints in scan | Deduplicated by (method, path) key before display |

---

*Fill in the Demo Video URL before clicking Submit Final. All other fields are complete.*