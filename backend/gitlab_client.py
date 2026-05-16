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


def _parse_repo_url(repo_url: str) -> tuple[str, str]:
    """
    Extract gitlab base URL and project namespace from a GitLab repo URL.
    e.g. https://scm.intermesh.net/group/subgroup/project
    Returns (base_api_url, namespace_with_path)
    """
    parsed = urlparse(repo_url.rstrip("/"))
    scheme = parsed.scheme or "https"
    host = parsed.netloc or "scm.intermesh.net"
    path = parsed.path.lstrip("/")
    # Remove .git suffix if present
    if path.endswith(".git"):
        path = path[:-4]
    base = f"{scheme}://{host}/api/v4"
    return base, path


class GitLabClient:
    def __init__(self, token: str, base_url: str = GITLAB_BASE):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.headers = {"PRIVATE-TOKEN": token}

    # ── low-level HTTP ─────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{self.base_url}{path}"
        params = params or {}
        t0 = time.monotonic()
        logger.debug("GET %s params=%s", url, json.dumps(params, default=str))
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=self.headers, params=params)
            elapsed = round((time.monotonic() - t0) * 1000)
            logger.debug(
                "RESPONSE %s status=%d elapsed=%dms size=%db",
                url, resp.status_code, elapsed, len(resp.content)
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP ERROR %s status=%d body=%s",
                url, e.response.status_code, e.response.text[:500]
            )
            raise
        except Exception as e:
            logger.error("REQUEST FAILED %s error=%s", url, str(e))
            raise

    def _get_paginated(self, path: str, params: dict = None, max_pages: int = 20) -> list:
        """Fetch all pages of a paginated GitLab API endpoint."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        results = []
        page = 1
        while page <= max_pages:
            params["page"] = page
            data = self._get(path, params)
            if not isinstance(data, list):
                logger.warning("Paginated response was not a list on page %d for %s", page, path)
                break
            results.extend(data)
            logger.debug("Paginated %s page=%d got=%d total=%d", path, page, len(data), len(results))
            if len(data) < params["per_page"]:
                break  # last page
            page += 1
        return results

    # ── Auth / project ─────────────────────────────────────────────────────────

    def validate_token(self) -> dict:
        logger.info("Validating GitLab token")
        result = self._get("/user")
        logger.info("Token valid – user=%s username=%s", result.get("name"), result.get("username"))
        return result

    def resolve_project(self, namespace_or_id: str | int) -> dict:
        """
        Resolve a project by numeric ID or by namespace path.
        e.g. 'group/subgroup/project' → project dict with 'id'
        """
        if isinstance(namespace_or_id, int) or str(namespace_or_id).isdigit():
            logger.info("Resolving project by ID: %s", namespace_or_id)
            return self._get(f"/projects/{namespace_or_id}")
        # URL-encode the namespace path
        encoded = quote(str(namespace_or_id), safe="")
        logger.info("Resolving project by namespace: %s (encoded: %s)", namespace_or_id, encoded)
        result = self._get(f"/projects/{encoded}")
        logger.info(
            "Resolved project namespace=%s → id=%s name=%s",
            namespace_or_id, result.get("id"), result.get("name")
        )
        return result

    @classmethod
    def from_repo_url(cls, repo_url: str, token: str) -> tuple["GitLabClient", dict]:
        """
        Build a GitLabClient from a full repo URL and return (client, project_dict).
        """
        base, namespace = _parse_repo_url(repo_url)
        logger.info("Building client from URL: %s base=%s namespace=%s", repo_url, base, namespace)
        client = cls(token=token, base_url=base)
        project = client.resolve_project(namespace)
        return client, project

    def list_repos(self, search: str = "", page: int = 1, per_page: int = 50) -> list:
        params = {"membership": True, "per_page": per_page, "page": page}
        if search:
            params["search"] = search
        logger.info("Listing repos search=%r page=%d", search, page)
        return self._get("/projects", params)

    def get_repo(self, project_id: int | str) -> dict:
        logger.info("Fetching project metadata id=%s", project_id)
        return self._get(f"/projects/{project_id}")

    # ── Repository tree ────────────────────────────────────────────────────────

    def list_tree(
        self,
        project_id: int | str,
        path: str = "",
        ref: str = "HEAD",
        recursive: bool = False,
    ) -> list:
        params = {"ref": ref, "recursive": recursive, "per_page": 100}
        if path:
            params["path"] = path
        logger.info("list_tree project=%s path=%r recursive=%s", project_id, path, recursive)
        return self._get(f"/projects/{project_id}/repository/tree", params)

    def list_source_files(self, project_id: int | str, ref: str = "HEAD") -> list[dict]:
        """Return ALL source files in the repo via paginated recursive tree walk."""
        logger.info("list_source_files project=%s ref=%s (full paginated)", project_id, ref)
        items = self._get_paginated(
            f"/projects/{project_id}/repository/tree",
            {"ref": ref, "recursive": True},
            max_pages=50,
        )
        blobs = [i for i in items if i["type"] == "blob"]
        logger.info("list_source_files project=%s → %d blobs found", project_id, len(blobs))
        return blobs

    # ── File access ────────────────────────────────────────────────────────────

    def get_file(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> str:
        encoded_path = quote(file_path, safe="")
        logger.info("get_file project=%s path=%s ref=%s", project_id, file_path, ref)
        data = self._get(f"/projects/{project_id}/repository/files/{encoded_path}", {"ref": ref})
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        logger.debug("get_file project=%s path=%s → %d bytes", project_id, file_path, len(content))
        return content

    def get_file_meta(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> dict:
        encoded_path = quote(file_path, safe="")
        return self._get(f"/projects/{project_id}/repository/files/{encoded_path}", {"ref": ref})

    def file_exists(self, project_id: int | str, file_path: str, ref: str = "HEAD") -> bool:
        """Return True if the file exists in the repo without raising."""
        try:
            self.get_file_meta(project_id, file_path, ref)
            return True
        except Exception:
            return False

    # ── GitLab Search API ──────────────────────────────────────────────────────

    def search_files(
        self,
        project_id: int | str,
        query: str,
        ref: str = "HEAD",
    ) -> list[dict]:
        """
        Use GitLab's repository search to find filenames matching *query*.
        Returns list of {basename, path, ...} blobs.
        """
        logger.info("search_files project=%s query=%r ref=%s", project_id, query, ref)
        try:
            results = self._get(
                f"/projects/{project_id}/search",
                {"scope": "blobs", "search": query, "ref": ref},
            )
            # Each result has: basename, data (file content snippet), filename, id, ref, startline
            logger.info(
                "search_files project=%s query=%r → %d results",
                project_id, query, len(results)
            )
            return results
        except Exception as e:
            logger.warning("search_files failed for query=%r: %s – falling back to tree walk", query, e)
            return []

    def search_code_in_file(
        self,
        project_id: int | str,
        query: str,
        ref: str = "HEAD",
    ) -> list[str]:
        """
        Search code across the project for a query string.
        Returns list of file paths that match.
        """
        logger.info("search_code project=%s query=%r", project_id, query)
        try:
            results = self._get(
                f"/projects/{project_id}/search",
                {"scope": "blobs", "search": query, "ref": ref},
            )
            paths = list({r["filename"] for r in results if "filename" in r})
            logger.info("search_code project=%s query=%r → paths=%s", project_id, query, paths)
            return paths
        except Exception as e:
            logger.warning("search_code failed query=%r: %s", query, e)
            return []

    # ── Smart file finder ──────────────────────────────────────────────────────

    def find_controller_file(
        self,
        project_id: int | str,
        controller_hint: str,
        ref: str = "HEAD",
    ) -> Optional[str]:
        """
        Given a hint (e.g. 'smsController', 'sms', 'controllers/sms.go'),
        find the best-matching controller/handler file path in the repo.

        Strategy:
        1. If the hint looks like a full path and the file exists → return it directly
        2. Use GitLab search API with the hint as query
        3. Walk a targeted subtree (controllers/, handlers/, routes/, etc.) and fuzzy-match
        4. Fall back to full tree walk with fuzzy filename match
        """
        hint = controller_hint.strip().lstrip("/")
        logger.info("find_controller_file project=%s hint=%r", project_id, hint)

        # ── Step 1: Exact path check ──────────────────────────────────────────
        if "/" in hint or hint.endswith((".go", ".php", ".py")):
            if self.file_exists(project_id, hint, ref):
                logger.info("find_controller_file: exact match found → %s", hint)
                return hint

        # ── Step 2: GitLab search API ─────────────────────────────────────────
        # Try the raw hint
        search_results = self.search_files(project_id, hint, ref)
        if search_results:
            # Filter to source files only
            source_exts = (".go", ".php", ".py", ".js", ".ts", ".rb", ".java")
            candidates = [
                r["filename"] for r in search_results
                if any(r.get("filename", "").endswith(ext) for ext in source_exts)
            ]
            if candidates:
                # Prefer files with "controller", "handler", "route" in name
                ranked = _rank_candidates(candidates, hint)
                logger.info(
                    "find_controller_file: search API candidates=%s → best=%s",
                    candidates[:5], ranked[0] if ranked else None
                )
                if ranked:
                    return ranked[0]

        # Try extracting the basename from hint and search for that
        basename_hint = os.path.splitext(os.path.basename(hint))[0]
        if basename_hint and basename_hint != hint:
            search_results2 = self.search_files(project_id, basename_hint, ref)
            if search_results2:
                source_exts = (".go", ".php", ".py", ".js", ".ts", ".rb", ".java")
                candidates2 = [
                    r["filename"] for r in search_results2
                    if any(r.get("filename", "").endswith(ext) for ext in source_exts)
                ]
                ranked2 = _rank_candidates(candidates2, basename_hint)
                if ranked2:
                    logger.info("find_controller_file: basename search → %s", ranked2[0])
                    return ranked2[0]

        # ── Step 3: Walk common controller directories ────────────────────────
        CONTROLLER_DIRS = [
            "controllers", "controller", "handlers", "handler",
            "routes", "route", "api", "internal", "app", "src",
            "http", "web", "endpoints", "services", "service",
        ]
        for dir_name in CONTROLLER_DIRS:
            try:
                tree_items = self.list_tree(project_id, dir_name, ref, recursive=True)
                file_paths = [
                    i["path"] for i in tree_items
                    if i["type"] == "blob" and _is_source_file(i["path"])
                ]
                if file_paths:
                    ranked3 = _rank_candidates(file_paths, hint)
                    if ranked3:
                        logger.info(
                            "find_controller_file: dir walk (%s) → %s",
                            dir_name, ranked3[0]
                        )
                        return ranked3[0]
            except Exception as e:
                logger.debug("list_tree(%s) failed: %s", dir_name, e)

        # ── Step 4: Full tree walk ────────────────────────────────────────────
        logger.info("find_controller_file: falling back to full tree walk for hint=%r", hint)
        try:
            all_files = self.list_source_files(project_id, ref)
            file_paths = [f["path"] for f in all_files if _is_source_file(f["path"])]
            ranked4 = _rank_candidates(file_paths, hint)
            if ranked4:
                logger.info("find_controller_file: full-tree fallback → %s", ranked4[0])
                return ranked4[0]
        except Exception as e:
            logger.error("find_controller_file: full tree walk failed: %s", e)

        logger.warning("find_controller_file: could not find any file for hint=%r", hint)
        return None

    def find_files_for_endpoint(
        self,
        project_id: int | str,
        endpoint_name: str,
        ref: str = "HEAD",
    ) -> list[str]:
        """
        Given an endpoint name/path (e.g. '/sms', 'sendSms', 'SmsController'),
        find all source files that likely define or register that endpoint.

        Returns list of file paths ranked by relevance.
        """
        logger.info("find_files_for_endpoint project=%s endpoint=%r", project_id, endpoint_name)
        found_paths: set[str] = set()

        # Normalise endpoint hint - strip leading slash, extract last component
        clean = endpoint_name.strip().lstrip("/")
        # Extract meaningful tokens for search
        tokens = _endpoint_to_search_tokens(clean)
        logger.info("find_files_for_endpoint: search tokens=%s", tokens)

        for token in tokens:
            if len(token) < 2:
                continue
            paths = self.search_code_in_file(project_id, token, ref)
            for p in paths:
                if _is_source_file(p):
                    found_paths.add(p)

        ranked = _rank_candidates(list(found_paths), endpoint_name)
        logger.info(
            "find_files_for_endpoint: %d candidates → ranked top=%s",
            len(ranked), ranked[:3]
        )
        return ranked

    # ── Commit / language info ─────────────────────────────────────────────────

    def last_commit_date(self, project_id: int | str, ref: str = "HEAD") -> str:
        commits = self._get(
            f"/projects/{project_id}/repository/commits",
            {"ref_name": ref, "per_page": 1}
        )
        if commits:
            return commits[0].get("committed_date", "")
        return ""

    def get_languages(self, project_id: int | str) -> dict:
        logger.info("get_languages project=%s", project_id)
        return self._get(f"/projects/{project_id}/languages")


# ── Helpers ────────────────────────────────────────────────────────────────────

_SOURCE_EXTS = {".go", ".php", ".py", ".js", ".ts", ".rb", ".java", ".kt", ".cs"}
_EXCLUDE_DIRS = {
    "vendor", "node_modules", ".git", "dist", "build", "bin", "pkg",
    "testdata", "test", "tests", "spec", "mocks", "mock", "__pycache__",
}

_CONTROLLER_KEYWORDS = {
    "controller", "handler", "route", "router", "api", "endpoint",
    "service", "action", "resource", "view", "http",
}


def _is_source_file(path: str) -> bool:
    """Return True if the file path is a recognised source file."""
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    if ext not in _SOURCE_EXTS:
        return False
    # Exclude test files and vendored dependencies
    parts = path.lower().replace("\\", "/").split("/")
    if any(p in _EXCLUDE_DIRS for p in parts):
        return False
    if name.endswith("_test.go") or name.startswith("test_"):
        return False
    return True


def _score_candidate(path: str, hint: str) -> int:
    """
    Score a file path against a search hint. Higher = better match.
    """
    score = 0
    path_lower = path.lower()
    hint_lower = hint.lower().replace("/", " ").replace(".", " ").replace("-", " ").replace("_", " ")
    hint_tokens = [t for t in hint_lower.split() if t]
    basename = os.path.splitext(os.path.basename(path_lower))[0]

    # Exact basename match (highest priority)
    for token in hint_tokens:
        if token == basename:
            score += 100
        elif token in basename:
            score += 50
        elif basename in token:
            score += 30
        elif token in path_lower:
            score += 10

    # Controller/handler keyword bonus
    for kw in _CONTROLLER_KEYWORDS:
        if kw in basename:
            score += 20
        elif kw in path_lower:
            score += 5

    # Penalty for deep nesting (prefer shallow paths)
    depth = path.count("/")
    score -= depth * 2

    # Penalty for test / vendor paths
    for excl in _EXCLUDE_DIRS:
        if excl in path_lower:
            score -= 200

    return score


def _rank_candidates(paths: list[str], hint: str) -> list[str]:
    """Sort paths by relevance to *hint*, best first. Remove obviously irrelevant ones."""
    if not paths:
        return []
    scored = [(p, _score_candidate(p, hint)) for p in paths]
    scored.sort(key=lambda x: x[1], reverse=True)
    logger.debug("_rank_candidates hint=%r top-5=%s", hint, [(p, s) for p, s in scored[:5]])
    # Return all paths with non-negative scores (filter out obvious mismatches)
    return [p for p, s in scored if s >= 0]


def _endpoint_to_search_tokens(endpoint: str) -> list[str]:
    """
    Convert an endpoint path/name into a list of search tokens.
    e.g. '/api/v1/send-sms' → ['send-sms', 'sendSms', 'send_sms', 'sms']
    e.g. 'SmsController' → ['SmsController', 'sms', 'controller']
    """
    tokens = []
    clean = endpoint.strip("/")

    # Add the raw value
    tokens.append(clean)

    # Last path segment
    last = clean.split("/")[-1] if "/" in clean else clean
    if last and last != clean:
        tokens.append(last)

    # camelCase → split
    # e.g. sendSms → ['send', 'sms']
    camel_parts = re.sub(r"([A-Z])", r" \1", last).lower().split()
    tokens.extend(camel_parts)

    # kebab/snake → parts
    parts = re.split(r"[-_]", last.lower())
    tokens.extend(p for p in parts if p)

    # De-duplicate while preserving order
    seen: set[str] = set()
    result = []
    for t in tokens:
        t = t.strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)

    return result
