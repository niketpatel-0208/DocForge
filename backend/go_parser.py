"""Go source parser — extracts API routes from Gin, Echo, Chi, net/http registrations."""
import re
from dataclasses import dataclass, field

# Router patterns: (framework, method_group, router_var, http_method, path, handler)
_GIN_PATTERN = re.compile(
    r'(\w+)\.(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s*\(\s*"([^"]+)"\s*,\s*(\w[\w.]*)',
    re.IGNORECASE,
)
_ECHO_PATTERN = re.compile(
    r'(\w+)\.(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s*\(\s*"([^"]+)"\s*,\s*(\w[\w.]*)',
    re.IGNORECASE,
)
_CHI_PATTERN = re.compile(
    r'r\.(Get|Post|Put|Patch|Delete|Options|Head)\s*\(\s*"([^"]+)"\s*,\s*(\w[\w.]*)',
    re.IGNORECASE,
)
_NETHTTP_PATTERN = re.compile(
    r'(?:http\.)?HandleFunc\s*\(\s*"([^"]+)"\s*,\s*(\w[\w.]*)',
)
_MUX_PATTERN = re.compile(
    r'(\w+)\.HandleFunc\s*\(\s*"([^"]+)"\s*,\s*(\w[\w.]*)',
)

_FUNC_COMMENT = re.compile(r'//\s*(.*)')
_PARAM_ANNOTATION = re.compile(r'@param\s+(\w+)\s+(\w+)\s+(.*)')
_RETURN_ANNOTATION = re.compile(r'@return\s+(\d+)\s+(.*)')


@dataclass
class RouteInfo:
    method: str
    path: str
    handler: str
    file: str
    line: int
    comments: list[str] = field(default_factory=list)
    params: list[dict] = field(default_factory=list)
    returns: list[dict] = field(default_factory=list)
    framework: str = "unknown"


def detect_framework(source: str) -> str:
    if "github.com/gin-gonic/gin" in source:
        return "gin"
    if "github.com/labstack/echo" in source:
        return "echo"
    if "github.com/go-chi/chi" in source:
        return "chi"
    if "net/http" in source:
        return "net/http"
    return "unknown"


def _extract_comments_before(lines: list[str], line_idx: int) -> list[str]:
    comments = []
    i = line_idx - 1
    while i >= 0 and _FUNC_COMMENT.match(lines[i].strip()):
        m = _FUNC_COMMENT.match(lines[i].strip())
        comments.insert(0, m.group(1))
        i -= 1
    return comments


def parse_go_source(source: str, filename: str) -> list[RouteInfo]:
    lines = source.splitlines()
    framework = detect_framework(source)
    routes: list[RouteInfo] = []
    seen: set[tuple] = set()

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Gin / Echo style: r.GET("/path", handler)
        m = _GIN_PATTERN.search(stripped)
        if m:
            method = m.group(2).upper()
            path = m.group(3)
            handler = m.group(4)
            key = (method, path)
            if key not in seen:
                seen.add(key)
                comments = _extract_comments_before(lines, idx)
                routes.append(RouteInfo(method, path, handler, filename, idx + 1, comments, framework=framework))
            continue

        # Chi: r.Get("/path", handler)
        m = _CHI_PATTERN.search(stripped)
        if m:
            method = m.group(1).upper()
            path = m.group(2)
            handler = m.group(3)
            key = (method, path)
            if key not in seen:
                seen.add(key)
                comments = _extract_comments_before(lines, idx)
                routes.append(RouteInfo(method, path, handler, filename, idx + 1, comments, framework="chi"))
            continue

        # net/http HandleFunc
        m = _NETHTTP_PATTERN.search(stripped)
        if m:
            path = m.group(1)
            handler = m.group(2)
            key = ("ANY", path)
            if key not in seen:
                seen.add(key)
                comments = _extract_comments_before(lines, idx)
                routes.append(RouteInfo("ANY", path, handler, filename, idx + 1, comments, framework="net/http"))
            continue

        # Mux: mux.HandleFunc("/path", handler)
        m = _MUX_PATTERN.search(stripped)
        if m and m.group(1) not in ("http",):
            path = m.group(2)
            handler = m.group(3)
            key = ("ANY", path)
            if key not in seen:
                seen.add(key)
                comments = _extract_comments_before(lines, idx)
                routes.append(RouteInfo("ANY", path, handler, filename, idx + 1, comments, framework="mux"))

    return routes


def parse_go_files(files: dict[str, str]) -> list[RouteInfo]:
    """Parse multiple Go files. files = {filename: source_code}"""
    all_routes = []
    for filename, source in files.items():
        if filename.endswith(".go"):
            all_routes.extend(parse_go_source(source, filename))
    return all_routes
