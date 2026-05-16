"""GitLab API client for scm.intermesh.net – read-only access, with structured logging."""
import httpx
import base64
import logging
import json
import time
import os
import re
from typing import Optional
from urllib.parse import quote, urlparse
from dataclasses import dataclass, field

# ── Structured logger ─────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_log_formatter = logging.Formatter(
    fmt='%(asctime)s | %(levelname)-7s | %(name)s | %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%S'
)
_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "gitlab_api.log"), encoding="utf-8")
_file_handler.setFormatter(_log_formatter)
_file_handler.setLevel(logging.DEBUG)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)
_console_handler.setLevel(logging.INFO)

logger = logging.getLogger("docforge.gitlab")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    logger.addHandler(_file_handler)
    logger.addHandler(_console_handler)

GITLAB_BASE = "https://scm.intermesh.net/api/v4"


# ── EndpointFileContext ────────────────────────────────────────────────────────

@dataclass
class EndpointFileContext:
    """All source files collected for one endpoint."""
    controller_file: str = ""
    controller_source: str = ""
    route_file: str = ""
    route_source: str = ""
    model_files: dict = field(default_factory=dict)   # path → source
    detected_method: str = ""
    detected_path: str = ""
    detected_handler_func: str = ""

    def all_sources_combined(self) -> str:
        parts = []
        if self.route_file and self.route_source:
            parts.append(
                f"=== ROUTE REGISTRATION FILE: {self.route_file} ===\n{self.route_source}"
            )
        if self.controller_file and self.controller_source:
            parts.append(
                f"=== CONTROLLER/HANDLER FILE: {self.controller_file} ===\n{self.controller_source}"
            )
        for path, src in self.model_files.items():
            parts.append(f"=== MODEL/STRUCT FILE: {path} ===\n{src}")
        return "\n\n".join(parts)

    def to_search_log(self) -> list[str]:
        lines = []
        if self.controller_file:
            lines.append(f"Controller: {self.controller_file}")
        if self.route_file:
            lines.append(
                f"Route file: {self.route_file} "
                f"(method={self.detected_method or '?'} path={self.detected_path or '?'})"
            )
        if self.model_files:
            lines.append(f"Model files: {', '.join(self.model_files.keys())}")
        return lines


# ── URL helpers ────────────────────────────────────────────────────────────────

def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url.rstrip("/"))
    scheme = parsed.scheme or "https"
    host = parsed.netloc or "scm.intermesh.net"
    path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{scheme}://{host}/api/v4", path


def _service_root(file_path: str) -> str:
    """
    Return the top-level service directory for a file.
    e.g. 'src/centralizedService-go/Controllers/foo.go'
         → 'src/centralizedService-go'
    For a flat file like 'main.go' returns ''.
    """
    parts = file_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0] if parts else ""


def _same_service(a: str, b: str) -> bool:
    """True if both paths share the same top-level service root."""
    ra, rb = _service_root(a), _service_root(b)
    return bool(ra) and ra == rb


# ── GitLabClient ───────────────────────────────────────────────────────────────

class GitLabClient:
    def __init__(self, token: str, base_url: str = GITLAB_BASE):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.headers = {"PRIVATE-TOKEN": token}

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{self.base_url}{path}"
        params = params or {}
        t0 = time.monotonic()
        logger.debug("GET %s params=%s", url, json.dumps(params, default=str))
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=self.headers, params=params)
            elapsed = round((time.monotonic() - t0) * 1000)
            logger.debug("RESPONSE %s status=%d elapsed=%dms size=%db",
                         url, resp.status_code, elapsed, len(resp.content))
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("HTTP ERROR %s status=%d body=%s",
                         url, e.response.status_code, e.response.text[:500])
            raise
        except Exception as e:
            logger.error("REQUEST FAILED %s error=%s", url, str(e))
            raise

    def _get_paginated(self, path: str, params: dict = None, max_pages: int = 20) -> list:
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results = []
        page = 1
        while page <= max_pages:
            params["page"] = page
            data = self._get(path, params)
            if not isinstance(data, list):
                break
            results.extend(data)
            logger.debug("Paginated %s page=%d got=%d total=%d",
                         path, page, len(data), len(results))
            if len(data) < params["per_page"]:
                break
            page += 1
        return results

    # ── Auth / project ────────────────────────────────────────────────────────

    def validate_token(self) -> dict:
        logger.info("Validating GitLab token")
        result = self._get("/user")
        logger.info("Token valid – user=%s username=%s",
                    result.get("name"), result.get("username"))
        return result

    def resolve_project(self, namespace_or_id: str | int) -> dict:
        if isinstance(namespace_or_id, int) or str(namespace_or_id).isdigit():
            logger.info("Resolving project by ID: %s", namespace_or_id)
            return self._get(f"/projects/{namespace_or_id}")
        encoded = quote(str(namespace_or_id), safe="")
        logger.info("Resolving project by namespace: %s", namespace_or_id)
        result = self._get(f"/projects/{encoded}")
        logger.info("Resolved: id=%s name=%s", result.get("id"), result.get("name"))
        return result

    @classmethod
    def from_repo_url(cls, repo_url: str, token: str) -> tuple["GitLabClient", dict]:
        base, namespace = _parse_repo_url(repo_url)
        logger.info("Building client from URL: %s base=%s namespace=%s",
                    repo_url, base, namespace)
        client = cls(token=token, base_url=base)
        project = client.resolve_project(namespace)
        return client, project

    def list_repos(self, search: str = "", page: int = 1, per_page: int = 50) -> list:
        params = {"membership": True, "per_page": per_page, "page": page}
        if search:
            params["search"] = search
        return self._get("/projects", params)

    def get_repo(self, project_id: int | str) -> dict:
        return self._get(f"/projects/{project_id}")

    # ── Tree / files ──────────────────────────────────────────────────────────

    def list_tree(self, project_id: int | str, path: str = "",
                  ref: str = "HEAD", recursive: bool = False) -> list:
        params = {"ref": ref, "recursive": recursive, "per_page": 100}
        if path:
            params["path"] = path
        logger.info("list_tree project=%s path=%r recursive=%s", project_id, path, recursive)
        try:
            return self._get(f"/projects/{project_id}/repository/tree", params)
        except Exception as e:
            logger.debug("list_tree(%r) failed: %s", path, e)
            return []

    def list_source_files(self, project_id: int | str, ref: str = "HEAD") -> list[dict]:
        logger.info("list_source_files project=%s ref=%s", project_id, ref)
        items = self._get_paginated(
            f"/projects/{project_id}/repository/tree",
            {"ref": ref, "recursive": True},
            max_pages=50,
        )
        blobs = [i for i in items if i["type"] == "blob"]
        logger.info("list_source_files → %d blobs", len(blobs))
        return blobs

    def get_file(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> str:
        encoded_path = quote(file_path, safe="")
        logger.info("get_file project=%s path=%s ref=%s", project_id, file_path, ref)
        data = self._get(
            f"/projects/{project_id}/repository/files/{encoded_path}", {"ref": ref}
        )
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        logger.debug("get_file %s → %d bytes", file_path, len(content))
        return content

    def get_file_safe(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> str:
        try:
            return self.get_file(project_id, file_path, ref)
        except Exception as e:
            logger.warning("get_file_safe: %s → %s", file_path, e)
            return ""

    def get_file_meta(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> dict:
        encoded_path = quote(file_path, safe="")
        return self._get(
            f"/projects/{project_id}/repository/files/{encoded_path}", {"ref": ref}
        )

    def file_exists(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> bool:
        try:
            self.get_file_meta(project_id, file_path, ref)
            return True
        except Exception:
            return False

    # ── Search API ────────────────────────────────────────────────────────────

    def search_blobs(self, project_id: int | str, query: str,
                     ref: str = "HEAD") -> list[dict]:
        """Raw blob search – returns full result objects with filename/startline/data."""
        logger.info("search_blobs project=%s query=%r ref=%s", project_id, query, ref)
        try:
            results = self._get(
                f"/projects/{project_id}/search",
                {"scope": "blobs", "search": query, "ref": ref},
            )
            logger.info("search_blobs query=%r → %d results", query, len(results))
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.warning("search_blobs failed query=%r: %s", query, e)
            return []

    def search_code(self, project_id: int | str, query: str,
                    ref: str = "HEAD") -> list[str]:
        """Return file paths that contain query."""
        results = self.search_blobs(project_id, query, ref)
        paths = list({r["filename"] for r in results if "filename" in r})
        logger.info("search_code query=%r → %s", query, paths)
        return paths

    # ── Controller finder ─────────────────────────────────────────────────────

    def find_controller_file(self, project_id: int | str, controller_hint: str,
                             ref: str = "HEAD") -> Optional[str]:
        hint = controller_hint.strip().lstrip("/")
        logger.info("find_controller_file project=%s hint=%r", project_id, hint)

        # 1. Exact path
        if "/" in hint or hint.endswith((".go", ".php", ".py")):
            if self.file_exists(project_id, hint, ref):
                logger.info("find_controller_file: exact match → %s", hint)
                return hint

        # 2. Search API by full hint then by basename
        for term in [hint, os.path.splitext(os.path.basename(hint))[0]]:
            if not term:
                continue
            results = self.search_blobs(project_id, term, ref)
            candidates = [r["filename"] for r in results
                          if _is_source_file(r.get("filename", ""))]
            ranked = _rank_candidates(candidates, hint)
            if ranked:
                logger.info("find_controller_file: search(%r) → %s", term, ranked[0])
                return ranked[0]

        # 3. Common controller directories
        for dir_name in _CONTROLLER_DIRS:
            items = self.list_tree(project_id, dir_name, ref, recursive=True)
            paths = [i["path"] for i in items
                     if i["type"] == "blob" and _is_source_file(i["path"])]
            ranked = _rank_candidates(paths, hint)
            if ranked:
                logger.info("find_controller_file: dir_walk(%s) → %s", dir_name, ranked[0])
                return ranked[0]

        # 4. Full tree walk
        try:
            all_files = self.list_source_files(project_id, ref)
            paths = [f["path"] for f in all_files if _is_source_file(f["path"])]
            ranked = _rank_candidates(paths, hint)
            if ranked:
                logger.info("find_controller_file: full-tree → %s", ranked[0])
                return ranked[0]
        except Exception as e:
            logger.error("find_controller_file: tree walk failed: %s", e)

        logger.warning("find_controller_file: no match for %r", hint)
        return None

    def find_files_for_endpoint(self, project_id: int | str, endpoint_name: str,
                                ref: str = "HEAD") -> list[str]:
        """
        Find controller files for an endpoint name/path.
        Returns ranked list of source file paths.
        """
        logger.info("find_files_for_endpoint project=%s endpoint=%r", project_id, endpoint_name)
        found: set[str] = set()
        clean = endpoint_name.strip().lstrip("/")
        tokens = _endpoint_to_search_tokens(clean)
        logger.info("find_files_for_endpoint: tokens=%s", tokens)

        # Phase 1: search each token
        for token in tokens:
            if len(token) < 2:
                continue
            for p in self.search_code(project_id, token, ref):
                if _is_source_file(p):
                    found.add(p)
            if found:
                logger.info("find_files_for_endpoint: token=%r → %d files", token, len(found))

        if found:
            ranked = _rank_candidates_lenient(list(found), endpoint_name)
            if ranked:
                logger.info("find_files_for_endpoint: phase1 → top=%s", ranked[:3])
                return ranked

        # Phase 2: dir walk
        for dir_name in _CONTROLLER_DIRS:
            items = self.list_tree(project_id, dir_name, ref, recursive=True)
            for item in items:
                if item["type"] == "blob" and _is_source_file(item["path"]):
                    found.add(item["path"])
            if found:
                break

        if found:
            ranked = _rank_candidates_lenient(list(found), endpoint_name)
            if ranked:
                logger.info("find_files_for_endpoint: dir-walk → top=%s", ranked[:3])
                return ranked

        # Phase 3: full tree walk
        try:
            all_files = self.list_source_files(project_id, ref)
            paths = [f["path"] for f in all_files if _is_source_file(f["path"])]
            ranked = _rank_candidates_lenient(paths, endpoint_name)
            logger.info("find_files_for_endpoint: full-tree → top=%s", ranked[:3])
            return ranked
        except Exception as e:
            logger.error("find_files_for_endpoint: full tree failed: %s", e)
        return []

    # ── Endpoint context gatherer ─────────────────────────────────────────────

    def gather_endpoint_context(
        self,
        project_id: int | str,
        controller_file: str,
        controller_source: str,
        endpoint_hint: str = "",
        ref: str = "HEAD",
    ) -> EndpointFileContext:
        """
        Given the confirmed controller file and its source, gather:
        1. The route registration file (same service tree only)
        2. The HTTP method + path from the route file
        3. Model/struct files (same service tree only)

        KEY CONSTRAINTS:
        - Route file MUST be in the same service tree as the controller
        - Route file MUST directly reference at least one handler func from the controller
        - Model files MUST be in the same service tree
        - If no route file is found in-tree, do NOT fall back to a different service's main.go
        """
        ctx = EndpointFileContext(
            controller_file=controller_file,
            controller_source=controller_source,
        )
        svc_root = _service_root(controller_file)
        ctrl_dir = os.path.dirname(controller_file)
        logger.info("gather_endpoint_context: controller=%s svc_root=%s endpoint_hint=%r",
                    controller_file, svc_root, endpoint_hint)

        # ── Extract handler func names ─────────────────────────────────────────
        handler_funcs = _extract_handler_funcs(controller_source)
        logger.info("gather_endpoint_context: handler funcs=%s", handler_funcs[:5])
        if handler_funcs:
            ctx.detected_handler_func = handler_funcs[0]

        # ── Find route file (SAME SERVICE only) ───────────────────────────────
        route_candidates: dict[str, int] = {}  # path → score

        # Search for each handler func name – only keep same-service results
        for func_name in handler_funcs[:5]:
            for p in self.search_code(project_id, func_name, ref):
                if (p != controller_file
                        and _is_source_file(p)
                        and _same_service(p, controller_file)):
                    score = route_candidates.get(p, 0)
                    score += 50  # found by handler func name = strong signal
                    bn = os.path.basename(p).lower()
                    if any(kw in bn for kw in ("main", "route", "router", "server", "app")):
                        score += 30
                    route_candidates[p] = score
                    logger.debug("route candidate (handler ref): %s score=%d", p, score)

        # Also walk the service tree for known route-file patterns
        for sub in ["", ctrl_dir]:
            try:
                items = self.list_tree(project_id, sub or svc_root, ref, recursive=True)
                for item in items:
                    p = item["path"]
                    if (item["type"] != "blob"
                            or not _is_source_file(p)
                            or p == controller_file
                            or not _same_service(p, controller_file)):
                        continue
                    bn = os.path.basename(p).lower()
                    if any(kw in bn for kw in ("main", "route", "router", "server", "app")):
                        score = route_candidates.get(p, 0) + 20
                        route_candidates[p] = score
            except Exception:
                pass

        # Sort by score, try to extract method/path from top candidates
        sorted_routes = sorted(route_candidates.items(), key=lambda x: x[1], reverse=True)
        logger.info("gather_endpoint_context: route candidates=%s",
                    [(p, s) for p, s in sorted_routes[:5]])

        for route_path, rscore in sorted_routes[:5]:
            src = self.get_file_safe(project_id, route_path, ref)
            if not src:
                continue
            method, path = _extract_route_registration(src, handler_funcs, endpoint_hint)
            if method and path:
                ctx.route_file = route_path
                ctx.route_source = src
                ctx.detected_method = method
                ctx.detected_path = path
                logger.info("gather_endpoint_context: route found %s %s in %s",
                            method, path, route_path)
                break
            elif rscore >= 50:
                # High-confidence file (referenced handler func) even without parsed route
                ctx.route_file = route_path
                ctx.route_source = src
                logger.info("gather_endpoint_context: route file (handler ref, no parse): %s",
                            route_path)
                break

        # Use endpoint_hint as path fallback
        if endpoint_hint and not ctx.detected_path:
            ctx.detected_path = (endpoint_hint if endpoint_hint.startswith("/")
                                 else f"/{endpoint_hint}")

        # ── Find model/struct files (SAME SERVICE only) ───────────────────────
        struct_names = _extract_struct_names(controller_source)
        logger.info("gather_endpoint_context: structs in controller=%s", struct_names[:8])

        model_candidates: dict[str, int] = {}  # path → score

        # 1. Same directory siblings (same package = highest relevance)
        try:
            items = self.list_tree(project_id, ctrl_dir, ref, recursive=False)
            for item in items:
                p = item["path"]
                if (item["type"] == "blob"
                        and _is_source_file(p)
                        and p != controller_file
                        and p != ctx.route_file):
                    model_candidates[p] = model_candidates.get(p, 0) + 10
        except Exception:
            pass

        # 2. Search for struct definitions in same service tree
        for struct_name in struct_names[:6]:
            if len(struct_name) < 3:
                continue
            for p in self.search_code(project_id, f"type {struct_name} struct", ref):
                if (p != controller_file
                        and p != ctx.route_file
                        and _is_source_file(p)
                        and _same_service(p, controller_file)):
                    model_candidates[p] = model_candidates.get(p, 0) + 40
                    logger.debug("model candidate (struct def): %s", p)

        # 3. Standard model dirs inside same service tree
        for model_suffix in ("models", "model", "structs", "types", "entities", "dto", "request"):
            candidate_dir = f"{svc_root}/{model_suffix}" if svc_root else model_suffix
            try:
                items = self.list_tree(project_id, candidate_dir, ref, recursive=True)
                for item in items:
                    p = item["path"]
                    if item["type"] == "blob" and _is_source_file(p):
                        model_candidates[p] = model_candidates.get(p, 0) + 25
            except Exception:
                pass

        # Sort model candidates by score and fetch top ones
        sorted_models = sorted(model_candidates.items(), key=lambda x: x[1], reverse=True)
        logger.info("gather_endpoint_context: model candidates=%s",
                    [(p, s) for p, s in sorted_models[:6]])

        fetched = 0
        for model_path, mscore in sorted_models:
            if fetched >= 4:
                break
            if model_path in (controller_file, ctx.route_file):
                continue
            src = self.get_file_safe(project_id, model_path, ref)
            if not src or len(src) < 50:
                continue
            has_struct = "type " in src and "struct" in src
            has_relevant = any(s.lower() in src.lower() for s in struct_names[:5])
            is_same_dir = os.path.dirname(model_path) == ctrl_dir
            if has_struct or has_relevant or (is_same_dir and mscore >= 10):
                ctx.model_files[model_path] = src
                logger.info("gather_endpoint_context: model=%s score=%d (%d bytes)",
                            model_path, mscore, len(src))
                fetched += 1

        logger.info(
            "gather_endpoint_context: DONE ctrl=%s route=%s(%s %s) models=%d",
            controller_file, ctx.route_file,
            ctx.detected_method, ctx.detected_path,
            len(ctx.model_files)
        )
        return ctx

    # ── Commit / languages ────────────────────────────────────────────────────

    def last_commit_date(self, project_id: int | str, ref: str = "HEAD") -> str:
        commits = self._get(
            f"/projects/{project_id}/repository/commits",
            {"ref_name": ref, "per_page": 1}
        )
        if commits:
            return commits[0].get("committed_date", "")
        return ""

    def get_languages(self, project_id: int | str) -> dict:
        return self._get(f"/projects/{project_id}/languages")


# ── Constants ──────────────────────────────────────────────────────────────────

_SOURCE_EXTS = {".go", ".php", ".py", ".js", ".ts", ".rb", ".java", ".kt", ".cs"}
_EXCLUDE_DIRS = {
    "vendor", "node_modules", ".git", "dist", "build", "bin", "pkg",
    "testdata", "test", "tests", "spec", "mocks", "mock", "__pycache__",
}
_CONTROLLER_KEYWORDS = {
    "controller", "handler", "route", "router", "api", "endpoint",
    "service", "action", "resource", "view", "http",
}
_CONTROLLER_DIRS = [
    "controllers", "controller", "handlers", "handler",
    "routes", "route", "api", "internal", "app", "src",
    "http", "web", "endpoints", "services", "service",
]

# ── Route extraction ───────────────────────────────────────────────────────────

_ROUTE_PATTERNS = [
    # Gin/Echo: r.POST("/path", Handler) or router.GET("/path", pkg.Handler)
    re.compile(
        r'\.\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s*\(\s*["\']([^"\']+)["\']'
        r'\s*,\s*([\w.]+)',
        re.IGNORECASE,
    ),
    # Chi: r.Get("/path", Handler)
    re.compile(
        r'\.\s*(Get|Post|Put|Patch|Delete|Options|Head)\s*\(\s*["\']([^"\']+)["\']'
        r'\s*,\s*([\w.]+)',
        re.IGNORECASE,
    ),
    # net/http: http.HandleFunc("/path", Handler) or mux.HandleFunc
    re.compile(
        r'HandleFunc\s*\(\s*["\']([^"\']+)["\']\s*,\s*([\w.]+)',
        re.IGNORECASE,
    ),
    # PHP: Route::get('/path', ...)
    re.compile(
        r'Route\s*::\s*(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)["\']',
        re.IGNORECASE,
    ),
]

_FUNC_PATTERN = re.compile(r'^\s*func\s+(\w+)\s*\(', re.MULTILINE)
_STRUCT_PATTERN = re.compile(r'\btype\s+(\w+)\s+struct\b')


def _extract_handler_funcs(source: str) -> list[str]:
    """Extract exported Go function names (likely HTTP handlers)."""
    funcs = _FUNC_PATTERN.findall(source)
    skip = {"init", "main", "New", "newRouter", "SetupRouter", "Setup"}
    return [f for f in funcs if f not in skip
            and not f.startswith("test") and not f.startswith("Test")]


def _extract_struct_names(source: str) -> list[str]:
    return _STRUCT_PATTERN.findall(source)


def _extract_route_registration(
    route_source: str,
    handler_funcs: list[str],
    endpoint_hint: str = "",
) -> tuple[str, str]:
    """
    Scan a route file for the registration of one of our handler funcs.
    Returns (HTTP_METHOD, path) or ("", "").
    """
    handler_set = set()
    for f in handler_funcs:
        handler_set.add(f)
        handler_set.add(f.lower())

    ep_lower = endpoint_hint.lower().lstrip("/") if endpoint_hint else ""
    best_method, best_path, best_score = "", "", -1

    for pat in _ROUTE_PATTERNS:
        for m in pat.finditer(route_source):
            groups = m.groups()
            if len(groups) == 3:
                method, path, handler_ref = groups
            elif len(groups) == 2:
                path, handler_ref = groups
                method = "ANY"
            else:
                continue

            method = method.upper()
            hbase = handler_ref.split(".")[-1]
            score = 0

            if hbase in handler_set:
                score += 100
            elif any(h.lower() in hbase.lower() or hbase.lower() in h.lower()
                     for h in handler_set):
                score += 50

            if ep_lower:
                pl = path.lower().lstrip("/")
                if pl == ep_lower:
                    score += 80
                elif ep_lower in pl or pl in ep_lower:
                    score += 40

            if score > best_score:
                best_score, best_method, best_path = score, method, path

    if best_score > 0:
        logger.debug("_extract_route_registration: method=%s path=%s score=%d",
                     best_method, best_path, best_score)
        return best_method, best_path

    # Fallback: endpoint hint matches a registered path
    if ep_lower:
        for pat in _ROUTE_PATTERNS:
            for m in pat.finditer(route_source):
                groups = m.groups()
                if len(groups) >= 2:
                    method = groups[0].upper() if len(groups) == 3 else "ANY"
                    path = groups[1] if len(groups) == 3 else groups[0]
                    if ep_lower in path.lower():
                        return method, path

    return "", ""


# ── Candidate scoring ──────────────────────────────────────────────────────────

def _is_source_file(path: str) -> bool:
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    if ext not in _SOURCE_EXTS:
        return False
    parts = path.lower().replace("\\", "/").split("/")
    if any(p in _EXCLUDE_DIRS for p in parts):
        return False
    if name.endswith("_test.go") or name.startswith("test_"):
        return False
    return True


def _score_candidate(path: str, hint: str) -> int:
    score = 0
    path_lower = path.lower()
    hint_clean = hint.lower().lstrip("/")
    hint_tokens = [t for t in re.split(r'[\s/._\-]', hint_clean) if t and len(t) > 1]
    basename = os.path.splitext(os.path.basename(path_lower))[0]

    for token in hint_tokens:
        if token == basename:
            score += 100
        elif token in basename:
            score += 50
        elif basename in token:
            score += 30
        elif token in path_lower:
            score += 15

    dir_parts = path_lower.replace("\\", "/").split("/")[:-1]
    for token in hint_tokens:
        for part in dir_parts:
            if token == part:
                score += 20
            elif token in part:
                score += 8

    for kw in _CONTROLLER_KEYWORDS:
        if kw in basename:
            score += 20
        elif kw in path_lower:
            score += 5

    # Mild depth penalty (deep monorepos shouldn't be over-penalised)
    score -= path.count("/") * 1

    for excl in _EXCLUDE_DIRS:
        if excl in path_lower:
            score -= 200

    return score


def _rank_candidates(paths: list[str], hint: str) -> list[str]:
    if not paths:
        return []
    scored = [(p, _score_candidate(p, hint)) for p in paths]
    scored.sort(key=lambda x: x[1], reverse=True)
    logger.debug("_rank_candidates hint=%r top5=%s", hint, [(p, s) for p, s in scored[:5]])
    return [p for p, s in scored if s >= 0]


def _rank_candidates_lenient(paths: list[str], hint: str) -> list[str]:
    if not paths:
        return []
    scored = [(p, _score_candidate(p, hint)) for p in paths]
    scored.sort(key=lambda x: x[1], reverse=True)
    logger.debug("_rank_candidates_lenient hint=%r top5=%s", hint, [(p, s) for p, s in scored[:5]])
    return [p for p, s in scored if s > -50]


def _endpoint_to_search_tokens(endpoint: str) -> list[str]:
    tokens = []
    clean = endpoint.strip("/")
    tokens.append(clean)
    last = clean.split("/")[-1] if "/" in clean else clean
    if last and last != clean:
        tokens.append(last)
    # camelCase split
    camel = re.sub(r"([A-Z])", r" \1", last).lower().split()
    tokens.extend(camel)
    # kebab/snake split
    tokens.extend(p for p in re.split(r"[-_]", last.lower()) if p)
    seen: set[str] = set()
    result = []
    for t in tokens:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    return result
