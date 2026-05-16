"""DocForge FastAPI backend  v3 – URL-based repo, endpoint-specific search, env LiteLLM key."""
import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from dotenv import load_dotenv

load_dotenv()  # Load .env file

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from gitlab_client import GitLabClient, EndpointFileContext, logger as gl_logger
from go_parser import parse_go_files
from php_parser import parse_php_files
from infra_parser import parse_infra_files, INFRA_FILE_PATTERNS, INFRA_EXTENSIONS
from normaliser import build_context_packet
from claude_client import generate_api_doc, generate_sop, pre_score_doc
from scorer import score_openapi_yaml
from export import package_yaml, package_sop

# ── App-level logger ───────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_app_formatter = logging.Formatter(
    fmt='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
_app_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "docforge.log"), encoding="utf-8")
_app_file_handler.setFormatter(_app_formatter)
_app_file_handler.setLevel(logging.DEBUG)

_app_console = logging.StreamHandler()
_app_console.setFormatter(_app_formatter)
_app_console.setLevel(logging.INFO)

app_logger = logging.getLogger("docforge.app")
app_logger.setLevel(logging.DEBUG)
if not app_logger.handlers:
    app_logger.addHandler(_app_file_handler)
    app_logger.addHandler(_app_console)

app = FastAPI(title="DocForge", version="3.0.0")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Constants ──────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "600"))
# LiteLLM key always comes from .env; no UI input needed
_LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")

# ── In-memory caches ───────────────────────────────────────────────────────────
_scan_cache: dict[int, dict] = {}
_routes_cache: dict[int, dict] = {}

_session: dict[str, Any] = {
    "docs": {},
    "stats": {
        "endpoints_documented": 0,
        "total_operations": 0,
        "scores": [],
    }
}


def _cache_valid(cache: dict, key: int) -> bool:
    if key not in cache:
        return False
    return (time.time() - cache[key]["timestamp"]) < CACHE_TTL_SECONDS


def _cache_get(cache: dict, key: int) -> Any:
    return cache[key]["data"]


def _cache_set(cache: dict, key: int, data: Any) -> None:
    cache[key] = {"data": data, "timestamp": time.time()}


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _gl_from_token(request: Request) -> GitLabClient:
    """Build GitLabClient from X-GitLab-Token header (uses default base URL)."""
    token = request.headers.get("X-GitLab-Token", "")
    if not token:
        raise HTTPException(401, "GitLab token not provided. Send X-GitLab-Token header.")
    return GitLabClient(token)


def _gl_from_url_and_token(repo_url: str, token: str) -> tuple[GitLabClient, dict]:
    """Build GitLabClient + resolve project from a full repo URL and token."""
    if not token:
        raise HTTPException(401, "GitLab PAT is required.")
    if not repo_url:
        raise HTTPException(422, "repo_url is required.")
    try:
        return GitLabClient.from_repo_url(repo_url, token)
    except Exception as e:
        app_logger.error("Failed to resolve repo URL=%s: %s", repo_url, e)
        raise HTTPException(400, f"Could not resolve repository: {e}")


def _litellm_key() -> str:
    """Always return the server-side LiteLLM key from .env."""
    if not _LITELLM_API_KEY:
        raise HTTPException(500, "LITELLM_API_KEY not configured on server. Check backend .env.")
    return _LITELLM_API_KEY


# ── 1. Auth/Validate ───────────────────────────────────────────────────────────

class AuthRequest(BaseModel):
    repo_url: str = ""
    gitlab_token: str


@app.post("/auth/validate")
def auth_validate(body: AuthRequest):
    """
    Validate a GitLab PAT (and optionally resolve a repo URL).
    Returns user info. LiteLLM key is always sourced from server .env.
    """
    if not body.gitlab_token.strip():
        raise HTTPException(422, "GitLab token cannot be empty.")

    if body.repo_url.strip():
        # Validate token AND resolve the repo in one shot
        try:
            gl, project = _gl_from_url_and_token(body.repo_url.strip(), body.gitlab_token)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(401, f"Validation failed: {e}")
        try:
            user = gl.validate_token()
        except Exception as e:
            raise HTTPException(401, f"GitLab token invalid: {e}")
        return {
            "ok": True,
            "user": user.get("name"),
            "username": user.get("username"),
            "project_id": project.get("id"),
            "project_name": project.get("name"),
            "project_path": project.get("path_with_namespace"),
        }
    else:
        # Token-only validation (for the settings modal)
        gl = GitLabClient(body.gitlab_token)
        try:
            user = gl.validate_token()
        except Exception as e:
            raise HTTPException(401, f"GitLab token invalid: {e}")
        return {"ok": True, "user": user.get("name"), "username": user.get("username")}


# ── 2. Resolve repo from URL ───────────────────────────────────────────────────

class ResolveRepoRequest(BaseModel):
    repo_url: str
    gitlab_token: str


@app.post("/repos/resolve")
def resolve_repo(body: ResolveRepoRequest):
    """
    Given a full GitLab repo URL and a PAT, resolve and return the project metadata.
    This replaces the old 'list all repos' UX.
    """
    app_logger.info("resolve_repo url=%s", body.repo_url)
    gl, project = _gl_from_url_and_token(body.repo_url.strip(), body.gitlab_token.strip())
    return {
        "id": project["id"],
        "name": project["name"],
        "path": project.get("path_with_namespace", ""),
        "description": project.get("description", ""),
        "last_activity_at": project.get("last_activity_at", ""),
        "web_url": project.get("web_url", ""),
        "default_branch": project.get("default_branch", "HEAD"),
    }


# ── 3. Repos list (kept for backward compat) ──────────────────────────────────

@app.get("/repos")
def list_repos(request: Request, search: str = "", page: int = 1):
    gl = _gl_from_token(request)
    repos = gl.list_repos(search=search, page=page)
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "path": r.get("path_with_namespace", ""),
            "description": r.get("description", ""),
            "last_activity_at": r.get("last_activity_at", ""),
            "web_url": r.get("web_url", ""),
        }
        for r in repos
    ]


# ── 4. Scan (with caching) ─────────────────────────────────────────────────────

@app.get("/repos/{project_id}/scan")
def scan_repo(project_id: int, request: Request, force_rescan: bool = False):
    if not force_rescan and _cache_valid(_scan_cache, project_id):
        return _cache_get(_scan_cache, project_id)

    gl = _gl_from_token(request)
    app_logger.info("scan_repo project_id=%d force=%s", project_id, force_rescan)

    try:
        files = gl.list_source_files(project_id)
    except Exception as e:
        raise HTTPException(400, f"Cannot list repo files: {e}")

    languages = {}
    try:
        languages = gl.get_languages(project_id)
    except Exception:
        pass

    last_commit = ""
    try:
        last_commit = gl.last_commit_date(project_id)
    except Exception:
        pass

    go_files = [f for f in files if f["name"].endswith(".go")]
    php_files = [f for f in files if f["name"].endswith(".php")]
    infra_files = [
        f for f in files
        if f["name"] in INFRA_FILE_PATTERNS
        or f["name"].startswith("Dockerfile")
        or any(f["name"].endswith(ext) for ext in INFRA_EXTENSIONS)
    ]

    result = {
        "project_id": project_id,
        "file_count": len(files),
        "go_files": len(go_files),
        "php_files": len(php_files),
        "infra_files": len(infra_files),
        "languages": languages,
        "last_commit_date": last_commit,
        "go_file_list": [f["path"] for f in go_files[:50]],
        "php_file_list": [f["path"] for f in php_files[:50]],
        "infra_file_list": [f["path"] for f in infra_files[:20]],
    }

    _cache_set(_scan_cache, project_id, result)
    return result


# ── 5. Parse routes (full repo scan, with caching) ────────────────────────────

@app.get("/repos/{project_id}/routes")
def get_routes(
    project_id: int,
    request: Request,
    whole_file_mode: bool = False,
    force_rescan: bool = False,
):
    cache_key = project_id
    if not force_rescan and _cache_valid(_routes_cache, cache_key):
        return _cache_get(_routes_cache, cache_key)

    gl = _gl_from_token(request)
    scan = scan_repo(project_id, request, force_rescan=force_rescan)
    service_name = gl.get_repo(project_id)["name"]

    go_sources: dict[str, str] = {}
    php_sources: dict[str, str] = {}
    infra_sources: dict[str, str] = {}

    # Prioritize route registration files so the parser finds HTTP method+path
    _ROUTE_FILE_KEYWORDS = ("main", "route", "router", "server", "app", "api", "handler")

    def _route_priority(path: str) -> int:
        bn = os.path.basename(path).lower().replace(".go", "").replace(".php", "")
        return 0 if any(kw in bn for kw in _ROUTE_FILE_KEYWORDS) else 1

    go_list_sorted = sorted(scan["go_file_list"], key=_route_priority)
    php_list_sorted = sorted(scan["php_file_list"], key=_route_priority)

    for path in go_list_sorted[:30]:
        try:
            go_sources[path] = gl.get_file(project_id, path)
        except Exception:
            pass

    for path in php_list_sorted[:30]:
        try:
            php_sources[path] = gl.get_file(project_id, path)
        except Exception:
            pass

    for path in scan["infra_file_list"]:
        try:
            infra_sources[path] = gl.get_file(project_id, path)
        except Exception:
            pass

    go_routes = parse_go_files(go_sources)
    php_routes = parse_php_files(php_sources)
    infra_ctx = parse_infra_files(infra_sources)

    packet = build_context_packet(
        service_name=service_name,
        go_routes=go_routes,
        php_routes=php_routes,
        infra_ctx=infra_ctx,
        file_list=list(go_sources.keys()) + list(php_sources.keys()),
        last_commit_date=scan["last_commit_date"],
        project_id=str(project_id),
    )

    packet_dict = packet.to_dict()

    # ── Deduplicate endpoints by (method, path) ───────────────────────────────
    seen_eps: set[tuple] = set()
    unique_endpoints = []
    for ep in packet_dict.get("endpoints", []):
        key = (ep.get("method", "").upper(), ep.get("path", ""))
        if key not in seen_eps:
            seen_eps.add(key)
            unique_endpoints.append(ep)

    app_logger.info(
        "get_routes: %d raw endpoints → %d unique after dedup",
        len(packet_dict.get("endpoints", [])), len(unique_endpoints)
    )

    if not unique_endpoints and not whole_file_mode:
        result = {
            "service_name": service_name,
            "endpoints": [],
            "infra": packet_dict["infra"],
            "no_routes_detected": True,
            "suggestion": "No API routes detected. Try whole-file mode or target a specific file.",
        }
    else:
        result = {
            "service_name": service_name,
            "language": packet_dict["language"],
            "framework": packet_dict["framework"],
            "endpoints": unique_endpoints,
            "infra": packet_dict["infra"],
            "file_list": packet_dict["file_list"],
            "last_commit_date": scan["last_commit_date"],
        }

    _cache_set(_routes_cache, cache_key, result)
    return result


# ── 6. Generate API doc (full scan) ───────────────────────────────────────────

class GenerateApiRequest(BaseModel):
    endpoint: dict
    project_id: int


@app.post("/generate/api")
def generate_api(body: GenerateApiRequest, request: Request):
    """
    Full-scan doc generation. Uses gather_endpoint_context to collect
    route file + model files for accurate documentation, same as targeted mode.
    """
    api_key = _litellm_key()
    gl = _gl_from_token(request)

    controller_file = body.endpoint.get("file", "")
    file_content = ""
    try:
        file_content = gl.get_file(body.project_id, controller_file)
    except Exception:
        pass

    # Use gather_endpoint_context for the same quality as targeted mode
    combined_source = file_content
    if controller_file and file_content:
        try:
            project_info = gl.get_repo(body.project_id)
            ref = project_info.get("default_branch", "HEAD")
            ep_ctx = gl.gather_endpoint_context(
                project_id=body.project_id,
                controller_file=controller_file,
                controller_source=file_content,
                endpoint_hint=body.endpoint.get("path", ""),
                ref=ref,
            )
            combined_source = ep_ctx.all_sources_combined() or file_content
            app_logger.info(
                "generate_api: gathered context route=%s models=%d for %s",
                ep_ctx.route_file, len(ep_ctx.model_files), controller_file
            )
        except Exception as e:
            app_logger.warning("generate_api: context gather failed: %s", e)

    try:
        yaml_text, confidence, missing_fields = generate_api_doc(
            body.endpoint, api_key=api_key, handler_source=combined_source
        )
    except Exception as e:
        raise HTTPException(500, f"LLM API error: {e}")

    score = score_openapi_yaml(yaml_text)
    _record_doc(body.project_id, body.endpoint, yaml_text, confidence, missing_fields, score)

    return {
        "yaml": yaml_text,
        "confidence": confidence,
        "missing": missing_fields,
        "score": score,
        "endpoint": body.endpoint,
        "parse_warning": score.get("parse_error"),
    }


# ── 7. Generate API doc (targeted: repo URL + PAT + file/endpoint hints) ──────

class TargetedGenerateRequest(BaseModel):
    repo_url: str = Field(..., description="Full GitLab repository URL")
    gitlab_token: str = Field(..., description="Personal Access Token")
    # At least one of the two below must be provided
    controller_file: str = Field(
        default="",
        description="Relative path to the controller file (e.g. controllers/sms.go)",
    )
    endpoint_name: str = Field(
        default="",
        description="Endpoint path or name to search for (e.g. /sms, sendSms)",
    )


@app.post("/generate/api/targeted")
def generate_api_targeted(body: TargetedGenerateRequest):
    """
    Targeted generation: resolve the repo from URL + PAT, then find the
    relevant file(s) using the controller_file hint and/or endpoint_name,
    and generate documentation. At least one of controller_file or
    endpoint_name must be provided.
    """
    if not body.controller_file.strip() and not body.endpoint_name.strip():
        raise HTTPException(
            422,
            "At least one of 'controller_file' or 'endpoint_name' must be provided."
        )

    api_key = _litellm_key()

    app_logger.info(
        "targeted generate: url=%s controller=%r endpoint=%r",
        body.repo_url, body.controller_file, body.endpoint_name
    )

    # Resolve project from URL
    gl, project = _gl_from_url_and_token(body.repo_url.strip(), body.gitlab_token.strip())
    project_id = project["id"]
    service_name = project["name"]
    ref = project.get("default_branch", "HEAD")

    app_logger.info("Resolved project: id=%s name=%s ref=%s", project_id, service_name, ref)

    # ── Find the target file ───────────────────────────────────────────────────
    resolved_file: Optional[str] = None
    search_log: list[str] = []

    if body.controller_file.strip():
        app_logger.info("Finding controller file: hint=%r", body.controller_file)
        resolved_file = gl.find_controller_file(project_id, body.controller_file.strip(), ref)
        search_log.append(f"controller_file hint '{body.controller_file}' → {resolved_file}")
        app_logger.info("find_controller_file result: %s", resolved_file)

    if not resolved_file and body.endpoint_name.strip():
        app_logger.info("Finding files for endpoint: hint=%r", body.endpoint_name)
        candidates = gl.find_files_for_endpoint(project_id, body.endpoint_name.strip(), ref)
        search_log.append(f"endpoint_name hint '{body.endpoint_name}' → candidates: {candidates[:3]}")
        app_logger.info("find_files_for_endpoint candidates: %s", candidates[:5])
        if candidates:
            resolved_file = candidates[0]

    if not resolved_file:
        app_logger.warning(
            "Could not resolve any file for controller=%r endpoint=%r",
            body.controller_file, body.endpoint_name
        )
        raise HTTPException(
            404,
            f"Could not find a matching source file. "
            f"Search log: {'; '.join(search_log)}. "
            f"Try providing the exact relative file path in 'controller_file'."
        )

    app_logger.info("Using file: %s", resolved_file)

    # ── Fetch primary file content ─────────────────────────────────────────────
    try:
        file_content = gl.get_file(project_id, resolved_file, ref)
    except Exception as e:
        app_logger.error("Failed to fetch file %s: %s", resolved_file, e)
        raise HTTPException(400, f"Could not fetch file '{resolved_file}': {e}")

    app_logger.info("Fetched %d bytes from %s", len(file_content), resolved_file)

    # ── Gather full endpoint context: routes + models ──────────────────────────
    app_logger.info("Gathering endpoint context (route file + model files)...")
    ep_ctx: EndpointFileContext = gl.gather_endpoint_context(
        project_id=project_id,
        controller_file=resolved_file,
        controller_source=file_content,
        endpoint_hint=body.endpoint_name.strip() if body.endpoint_name.strip() else "",
        ref=ref,
    )

    # Add context gather log to search_log
    search_log.extend(ep_ctx.to_search_log())
    app_logger.info(
        "Context gathered: route=%s method=%s path=%s models=%d",
        ep_ctx.route_file, ep_ctx.detected_method, ep_ctx.detected_path,
        len(ep_ctx.model_files)
    )

    # Combined source for LLM (route file + controller + models)
    combined_source = ep_ctx.all_sources_combined()
    if not combined_source:
        combined_source = file_content

    # ── Parse endpoints (try route file first, then controller) ───────────────
    ext = os.path.splitext(resolved_file)[1].lower()
    endpoints = []

    # Try parsing the route file if we found one — it will have the HTTP method/path
    parse_sources = {}
    if ep_ctx.route_file and ep_ctx.route_source:
        parse_sources[ep_ctx.route_file] = ep_ctx.route_source
    parse_sources[resolved_file] = file_content

    if ext == ".go":
        go_routes = parse_go_files(parse_sources)
        from normaliser import normalise_go_routes
        endpoints = [e.to_dict() for e in normalise_go_routes(go_routes, service_name)]
    elif ext == ".php":
        php_routes = parse_php_files(parse_sources)
        from normaliser import normalise_php_routes
        endpoints = [e.to_dict() for e in normalise_php_routes(php_routes, service_name)]

    app_logger.info("Parsed %d endpoint(s) from files (ext=%s)", len(endpoints), ext)

    # ── Filter by endpoint hint ────────────────────────────────────────────────
    if body.endpoint_name.strip() and endpoints:
        ep_hint = body.endpoint_name.strip().lower()
        filtered = [
            e for e in endpoints
            if ep_hint in e.get("path", "").lower()
            or ep_hint in e.get("handler_name", "").lower()
        ]
        if filtered:
            app_logger.info("Filtered endpoints %d → %d by hint=%r",
                            len(endpoints), len(filtered), body.endpoint_name)
            endpoints = filtered

    # ── Synthesise endpoint if parser found nothing ────────────────────────────
    if not endpoints:
        # Use detected method/path from route extraction if available
        detected_method = ep_ctx.detected_method or "POST"
        detected_path = (
            ep_ctx.detected_path
            or (body.endpoint_name if body.endpoint_name.startswith("/")
                else f"/{body.endpoint_name}" if body.endpoint_name else "/unknown")
        )
        detected_handler = (
            ep_ctx.detected_handler_func
            or os.path.splitext(os.path.basename(resolved_file))[0]
        )
        app_logger.warning(
            "No endpoints parsed; synthesising: method=%s path=%s handler=%s",
            detected_method, detected_path, detected_handler
        )
        endpoints = [{
            "service_name": service_name,
            "language": "go" if ext == ".go" else ("php" if ext == ".php" else "unknown"),
            "method": detected_method,
            "path": detected_path,
            "handler_name": detected_handler,
            "file": resolved_file,
            "line": 1,
            "comments": [],
            "params": [],
            "returns": [],
            "framework": "unknown",
            "existing_doc_fragment": "",
        }]

    # ── Generate docs ──────────────────────────────────────────────────────────
    results = []
    for ep in endpoints:
        app_logger.info("Generating doc: method=%s path=%s handler=%s",
                        ep.get("method"), ep.get("path"), ep.get("handler_name"))
        try:
            yaml_text, confidence, missing_fields = generate_api_doc(
                ep, api_key=api_key, handler_source=combined_source
            )
        except Exception as e:
            app_logger.error("LLM error for %s: %s", ep.get("path"), e)
            raise HTTPException(500, f"LLM API error: {e}")

        score = score_openapi_yaml(yaml_text)
        doc_id = _record_doc(project_id, ep, yaml_text, confidence, missing_fields, score)

        results.append({
            "doc_id": doc_id,
            "yaml": yaml_text,
            "confidence": confidence,
            "missing": missing_fields,
            "score": score,
            "endpoint": ep,
            "parse_warning": score.get("parse_error"),
        })

    return {
        "results": results,
        "resolved_file": resolved_file,
        "file_path": resolved_file,
        "route_file": ep_ctx.route_file,
        "model_files": list(ep_ctx.model_files.keys()),
        "endpoints_found": len(endpoints),
        "search_log": search_log,
        "project_id": project_id,
        "project_name": service_name,
    }


# ── 8. Targeted generate (legacy project_id path, kept for compat) ─────────────

class TargetedByIdRequest(BaseModel):
    project_id: int
    file_path: str
    endpoint_path: str = ""


@app.post("/generate/api/targeted/by-id")
def generate_api_targeted_by_id(body: TargetedByIdRequest, request: Request):
    """
    Targeted generation using numeric project_id (requires X-GitLab-Token header).
    Kept for backward compatibility with old frontend.
    """
    api_key = _litellm_key()
    gl = _gl_from_token(request)

    try:
        file_content = gl.get_file(body.project_id, body.file_path)
    except Exception as e:
        raise HTTPException(400, f"Could not fetch file: {e}")

    service_name = gl.get_repo(body.project_id)["name"]
    sources = {body.file_path: file_content}
    endpoints = []
    ext = os.path.splitext(body.file_path)[1].lower()

    if ext == ".go":
        go_routes = parse_go_files(sources)
        from normaliser import normalise_go_routes
        endpoints = [e.to_dict() for e in normalise_go_routes(go_routes, service_name)]
    elif ext == ".php":
        php_routes = parse_php_files(sources)
        from normaliser import normalise_php_routes
        endpoints = [e.to_dict() for e in normalise_php_routes(php_routes, service_name)]

    if body.endpoint_path:
        endpoints = [e for e in endpoints if e["path"] == body.endpoint_path]

    if not endpoints:
        endpoints = [{
            "service_name": service_name,
            "language": "go" if ext == ".go" else "php",
            "method": "POST",
            "path": body.endpoint_path or "/unknown",
            "handler_name": os.path.splitext(os.path.basename(body.file_path))[0],
            "file": body.file_path,
            "line": 1,
            "comments": [],
            "params": [],
            "returns": [],
            "framework": "unknown",
            "existing_doc_fragment": "",
        }]

    results = []
    for ep in endpoints:
        try:
            yaml_text, confidence, missing_fields = generate_api_doc(
                ep, api_key=api_key, handler_source=file_content
            )
        except Exception as e:
            raise HTTPException(500, f"LLM API error: {e}")

        score = score_openapi_yaml(yaml_text)
        doc_id = _record_doc(body.project_id, ep, yaml_text, confidence, missing_fields, score)

        results.append({
            "doc_id": doc_id,
            "yaml": yaml_text,
            "confidence": confidence,
            "missing": missing_fields,
            "score": score,
            "endpoint": ep,
            "parse_warning": score.get("parse_error"),
        })

    return {
        "results": results,
        "file_path": body.file_path,
        "endpoints_found": len(endpoints),
    }


# ── 9. Score ───────────────────────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    yaml_content: str
    use_claude: bool = False


@app.post("/score")
def score_doc(body: ScoreRequest):
    if body.use_claude:
        api_key = _litellm_key()
        try:
            result = pre_score_doc(body.yaml_content, api_key=api_key)
            _session["stats"]["total_operations"] += 1
        except Exception as e:
            raise HTTPException(500, f"LLM API error: {e}")
        return result
    return score_openapi_yaml(body.yaml_content)


# ── 10. Generate SOP ───────────────────────────────────────────────────────────

class GenerateSopRequest(BaseModel):
    project_id: int


@app.post("/generate/sop")
def generate_sop_endpoint(body: GenerateSopRequest, request: Request):
    api_key = _litellm_key()
    gl = _gl_from_token(request)
    scan = scan_repo(body.project_id, request)
    service_name = gl.get_repo(body.project_id)["name"]

    if not scan["infra_files"]:
        return {
            "sop": None,
            "no_infra_detected": True,
            "message": "No Dockerfile, K8s manifests, or shell scripts found in this repo.",
        }

    infra_sources: dict[str, str] = {}
    for path in scan["infra_file_list"]:
        try:
            infra_sources[path] = gl.get_file(body.project_id, path)
        except Exception:
            pass

    files_with_contents = "\n\n".join(
        f"=== {path} ===\n{content}" for path, content in infra_sources.items()
    )
    file_list = ", ".join(infra_sources.keys())
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        sop_raw = generate_sop(service_name, files_with_contents, file_list, timestamp, api_key=api_key)
    except Exception as e:
        raise HTTPException(500, f"LLM API error: {e}")

    _session["stats"]["total_operations"] += 1

    lines = sop_raw.splitlines()
    sop_lines, confidence, sections, needs_input = [], 0.5, [], []
    for line in lines:
        if line.startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("SECTIONS_INFERRED:"):
            sections = [s.strip() for s in line.split(":", 1)[1].split(",")]
        elif line.startswith("NEEDS_HUMAN_INPUT:"):
            needs_input = [s.strip() for s in line.split(":", 1)[1].split(",")]
        else:
            sop_lines.append(line)

    sop_text = "\n".join(sop_lines).strip()

    pid = str(body.project_id)
    if pid not in _session["docs"]:
        _session["docs"][pid] = []
    doc_id = len(_session["docs"][pid])
    _session["docs"][pid].append({
        "doc_id": doc_id,
        "type": "sop",
        "service_name": service_name,
        "sop": sop_text,
        "confidence": confidence,
        "sections": sections,
        "needs_human_input": needs_input,
        "generated_at": timestamp,
    })

    return {
        "doc_id": doc_id,
        "sop": sop_text,
        "confidence": confidence,
        "sections_inferred": sections,
        "needs_human_input": needs_input,
    }


# ── 11. Export ─────────────────────────────────────────────────────────────────

@app.get("/export/yaml/{project_id}/{doc_id}")
def export_yaml(project_id: int, doc_id: int):
    pid = str(project_id)
    docs = _session["docs"].get(pid, [])
    if doc_id >= len(docs):
        raise HTTPException(404, "Doc not found")
    doc = docs[doc_id]
    service_name = doc.get("endpoint", {}).get("service_name", "service")
    zip_bytes = package_yaml(service_name, doc["yaml"], doc.get("score", {}), {})
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{service_name}-docforge.zip"'},
    )


@app.get("/export/sop/{project_id}/{doc_id}")
def export_sop(project_id: int, doc_id: int):
    pid = str(project_id)
    docs = _session["docs"].get(pid, [])
    if doc_id >= len(docs):
        raise HTTPException(404, "Doc not found")
    doc = docs[doc_id]
    service_name = doc.get("service_name", "service")
    zip_bytes = package_sop(service_name, doc["sop"], {})
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{service_name}-sop.zip"'},
    )


# ── 12. Stats ──────────────────────────────────────────────────────────────────

@app.get("/stats")
def get_stats():
    stats = _session["stats"]
    scores = stats["scores"]
    return {
        **stats,
        "avg_score": round(sum(scores) / len(scores)) if scores else 0,
    }


# ── 13. Cache management ───────────────────────────────────────────────────────

@app.delete("/cache/{project_id}")
def clear_cache(project_id: int):
    _scan_cache.pop(project_id, None)
    _routes_cache.pop(project_id, None)
    return {"ok": True, "message": f"Cache cleared for project {project_id}"}


# ── Shared helper ──────────────────────────────────────────────────────────────

def _record_doc(
    project_id: int | str,
    endpoint: dict,
    yaml_text: str,
    confidence: float,
    missing_fields: list,
    score: dict,
) -> int:
    """Store a generated doc in the session and update stats. Returns doc_id."""
    _session["stats"]["endpoints_documented"] += 1
    _session["stats"]["total_operations"] += 1
    _session["stats"]["scores"].append(score.get("score_percent", 0))

    pid = str(project_id)
    if pid not in _session["docs"]:
        _session["docs"][pid] = []
    doc_id = len(_session["docs"][pid])
    _session["docs"][pid].append({
        "doc_id": doc_id,
        "endpoint": endpoint,
        "yaml": yaml_text,
        "confidence": confidence,
        "missing": missing_fields,
        "score": score,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    })
    return doc_id


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
