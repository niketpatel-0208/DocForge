# File Search Reference

## Overview

DocForge uses a 4-phase search to locate the controller file, then calls
`gather_endpoint_context()` to collect the route registration file and model/struct
files. All searches enforce the same-service-tree constraint.

## Phase 1 — GitLab Search API (scope=blobs)

Searches the repository using the GitLab Search API for the controller filename or
basename. Resolves ~80% of cases instantly. Returns ranked file paths.

## Phase 2 — Common directory walk

If Phase 1 returns no usable match, walks these directories recursively:
`controllers/`, `handlers/`, `internal/`, `src/`, `api/`, `http/`, `web/`,
`endpoints/`, `services/`, `service/`

## Phase 3 — Candidate scoring

All candidates are ranked by:

| Signal | Score |
|---|---|
| Basename exact match | +100 |
| Basename partial match | +50 |
| Basename contained in hint | +30 |
| Token in path | +15 |
| Directory token match | +20 |
| Controller keyword in basename | +20 |
| Each path depth level | -1 |
| Excluded dir (vendor, test, mock…) | -200 |

## Phase 4 — Full paginated tree walk

Walks the complete repository tree (100 files/page, up to 50 pages = 5,000 files)
as a final fallback. Same scoring applies.

## gather_endpoint_context()

After the controller file is confirmed:

### Route file discovery

1. Extract exported function names from the controller source
2. Search for files referencing those names — same-service tree only
3. Score: handler func reference found = +50, route/main/server filename = +30
4. Parse the top-scoring file with regex patterns to extract HTTP method and path

Supported route registration patterns:

| Framework | Pattern example |
|---|---|
| Gin | `r.POST("/path", Handler)` |
| Echo | `e.GET("/path", Handler)` |
| Chi | `r.Get("/path", Handler)` |
| net/http | `http.HandleFunc("/path", Handler)` |
| Gorilla Mux | `mux.HandleFunc("/path", Handler)` |
| Laravel | `Route::post('/path', ...)` |

### Model/struct file discovery

1. Extract struct names from controller source (`type X struct` pattern)
2. Search for `type StructName struct` definitions — same-service tree only (+40)
3. Scan sibling files in the same package directory (+10)
4. Scan standard model directories: `models/`, `model/`, `structs/`, `types/`,
   `entities/`, `dto/`, `request/` — same-service tree only (+25)
5. Fetch top 4 candidates that contain struct definitions

## Same-service-tree constraint

**Problem it solves:** In a monorepo, searching for a handler function name may return
hits from multiple services. Without a boundary, a file from `src/ServiceB/` could be
selected as the route file for a controller in `src/ServiceA/`.

**Implementation:**

```
service_root = first 2 path components
e.g. "src/ServiceA/Controllers/handler.go" → service root = "src/ServiceA"

A candidate file is accepted only if its service root == controller's service root.
```

**Example:**

```
Controller:  src/ServiceA/Controllers/url.go   → root: src/ServiceA  ✓
Route file:  src/ServiceA/ShortUrl/main.go     → root: src/ServiceA  ✓ accepted
Other file:  src/ServiceB/main.go              → root: src/ServiceB  ✗ rejected
```

## Context assembly

All collected files are assembled as labelled sections sent to the LLM:

```
=== ROUTE REGISTRATION FILE: src/ServiceA/ShortUrl/main.go ===
<source>

=== CONTROLLER/HANDLER FILE: src/ServiceA/Controllers/url.go ===
<source>

=== MODEL/STRUCT FILE: src/ServiceA/Models/request.go ===
<source>