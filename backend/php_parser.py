"""PHP source parser — extracts API routes from Laravel, Slim, plain router patterns."""
import re
from dataclasses import dataclass, field

_LARAVEL_ROUTE = re.compile(
    r"Route::(get|post|put|patch|delete|options|any)\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*[\['\"]?([^'\"\],\)]+)",
    re.IGNORECASE,
)
_LARAVEL_CONTROLLER = re.compile(
    r"->([a-zA-Z_]\w*)\s*\(",
)
_SLIM_ROUTE = re.compile(
    r"\$app->(get|post|put|patch|delete|options)\s*\(\s*['\"]([^'\"]+)['\"]\s*,",
    re.IGNORECASE,
)
_PLAIN_ROUTE = re.compile(
    r"(?:\$router|router)->(get|post|put|patch|delete|options)\s*\(\s*['\"]([^'\"]+)['\"]\s*,",
    re.IGNORECASE,
)
_PHP_COMMENT = re.compile(r"//\s*(.*)|#\s*(.*)")
_DOCBLOCK = re.compile(r"/\*\*(.+?)\*/", re.DOTALL)


@dataclass
class PHPRouteInfo:
    method: str
    path: str
    handler: str
    file: str
    line: int
    comments: list[str] = field(default_factory=list)
    framework: str = "unknown"


def detect_php_framework(source: str) -> str:
    if "Illuminate\\Routing" in source or "Route::" in source:
        return "laravel"
    if "\\Slim\\App" in source or "$app->get" in source:
        return "slim"
    return "plain"


def _extract_php_comments(lines: list[str], line_idx: int) -> list[str]:
    comments = []
    i = line_idx - 1
    block = []
    while i >= 0:
        stripped = lines[i].strip()
        m = _PHP_COMMENT.match(stripped)
        if m:
            text = m.group(1) or m.group(2) or ""
            comments.insert(0, text)
            i -= 1
        elif stripped.endswith("*/"):
            while i >= 0 and "/**" not in lines[i]:
                dm = re.sub(r"^\s*\*\s?", "", lines[i].strip())
                if dm and dm != "*/":
                    block.insert(0, dm)
                i -= 1
            comments = block + comments
            break
        else:
            break
    return comments


def parse_php_source(source: str, filename: str) -> list[PHPRouteInfo]:
    lines = source.splitlines()
    framework = detect_php_framework(source)
    routes: list[PHPRouteInfo] = []
    seen: set[tuple] = set()

    for idx, line in enumerate(lines):
        stripped = line.strip()

        m = _LARAVEL_ROUTE.search(stripped)
        if m:
            method = m.group(1).upper()
            path = m.group(2)
            handler = m.group(3).strip()
            key = (method, path)
            if key not in seen:
                seen.add(key)
                comments = _extract_php_comments(lines, idx)
                routes.append(PHPRouteInfo(method, path, handler, filename, idx + 1, comments, framework))
            continue

        m = _SLIM_ROUTE.search(stripped) or _PLAIN_ROUTE.search(stripped)
        if m:
            method = m.group(1).upper()
            path = m.group(2)
            handler = ""
            key = (method, path)
            if key not in seen:
                seen.add(key)
                comments = _extract_php_comments(lines, idx)
                routes.append(PHPRouteInfo(method, path, handler, filename, idx + 1, comments, framework))

    return routes


def parse_php_files(files: dict[str, str]) -> list[PHPRouteInfo]:
    all_routes = []
    for filename, source in files.items():
        if filename.endswith(".php"):
            all_routes.extend(parse_php_source(source, filename))
    return all_routes
