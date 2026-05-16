#!/usr/bin/env python3
"""
DocForge standalone YAML scorer — CLI tool.
Scores an OpenAPI 3.0 YAML file against the 22-criteria compliance rubric.

Usage:
    python score_yaml.py path/to/spec.yaml
    python score_yaml.py path/to/spec.yaml --json
"""
import sys
import json
import re

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Run: pip install pyyaml")
    sys.exit(1)


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def score(spec: dict) -> dict:
    checks = []

    def check(qid, status, finding):
        checks.append({"id": qid, "status": status, "finding": finding})

    # Q1 — HTTP method semantics
    methods = set()
    for path_item in spec.get("paths", {}).values():
        methods.update(k.upper() for k in path_item if k.upper() in
                       ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"))
    if methods:
        check(1, "YES", f"Methods present: {', '.join(sorted(methods))}")
    else:
        check(1, "NO", "No HTTP methods found in paths")

    # Q2 — Endpoint paths defined
    paths = list(spec.get("paths", {}).keys())
    if paths and not any("TODO" in p or "unknown" in p.lower() for p in paths):
        check(2, "YES", f"{len(paths)} path(s) defined")
    elif paths:
        check(2, "PARTIAL", "Some paths contain placeholder values")
    else:
        check(2, "NO", "No paths defined")

    # Q3 — Server URL
    servers = spec.get("servers", [])
    valid = [s for s in servers if s.get("url") and
             "localhost" not in s["url"] and "TODO" not in s["url"]]
    if valid:
        check(3, "YES", f"Server URL: {valid[0]['url']}")
    elif servers:
        check(3, "PARTIAL", "Server present but uses localhost or TODO")
    else:
        check(3, "NO", "No servers block")

    # Q4–Q10 — Request body checks
    rb_schemas = []
    for path_item in spec.get("paths", {}).values():
        for op in path_item.values():
            if isinstance(op, dict):
                rb = op.get("requestBody", {})
                for ct_val in rb.get("content", {}).values():
                    if "schema" in ct_val:
                        rb_schemas.append(ct_val["schema"])

    if rb_schemas:
        check(4, "YES", "Request content type declared")
    else:
        check(4, "NO", "No requestBody content type found")

    # Q5 — types
    all_props = []
    for s in rb_schemas:
        all_props.extend(s.get("properties", {}).values())
    no_type = [p for p in all_props if "type" not in p and "$ref" not in p]
    if all_props and not no_type:
        check(5, "YES", f"All {len(all_props)} request fields have types")
    elif no_type:
        check(5, "PARTIAL", f"{len(no_type)} field(s) missing type")
    else:
        check(5, "NO", "No request properties found")

    # Q6 — required
    has_required = any("required" in s for s in rb_schemas)
    check(6, "YES" if has_required else "NO",
          "required array present" if has_required else "No required array in request schema")

    # Q7 — descriptions
    short_desc = [p for p in all_props if len(p.get("description", "")) < 15]
    if all_props and not short_desc:
        check(7, "YES", "All descriptions meaningful")
    elif short_desc:
        check(7, "PARTIAL", f"{len(short_desc)} field(s) have short/missing descriptions")
    else:
        check(7, "NO", "No descriptions found")

    # Q8 — examples
    no_example = [p for p in all_props if "example" not in p]
    if all_props and not no_example:
        check(8, "YES", "All fields have examples")
    elif no_example:
        check(8, "PARTIAL", f"{len(no_example)} field(s) missing examples")
    else:
        check(8, "NO", "No examples found")

    # Q9 — defaults for optional
    check(9, "PARTIAL", "Default values: manual review recommended")

    # Q10 — enums
    has_enum = any("enum" in p for p in all_props)
    check(10, "YES" if has_enum else "NO",
          "Enum found on at least one field" if has_enum else "No enum constraints found")

    # Q11–Q19 — Response checks
    all_responses = []
    for path_item in spec.get("paths", {}).values():
        for op in path_item.values():
            if isinstance(op, dict):
                for code, resp in op.get("responses", {}).items():
                    all_responses.append((str(code), resp))

    resp_with_content = [(c, r) for c, r in all_responses if r.get("content")]
    check(11, "YES" if resp_with_content else "NO",
          f"{len(resp_with_content)} response(s) have content type"
          if resp_with_content else "No response content types")

    # Q12 — response schema types
    check(12, "PARTIAL", "Response schema types: review components/schemas")

    # Q13 — response descriptions
    resp_desc = [r.get("description", "") for _, r in all_responses]
    short_resp = [d for d in resp_desc if len(d) < 10]
    check(13, "YES" if not short_resp else "PARTIAL",
          "All responses have descriptions" if not short_resp
          else f"{len(short_resp)} response(s) have short descriptions")

    # Q14 — 2+ examples per status
    has_examples = any(
        len(ct_val.get("examples", {})) >= 2
        for _, r in all_responses
        for ct_val in r.get("content", {}).values()
    )
    check(14, "YES" if has_examples else "NO",
          "2+ named examples found" if has_examples else "Fewer than 2 named examples per status")

    # Q15–Q17 — coverage
    codes = [c for c, _ in all_responses]
    check(15, "YES" if any(c.startswith("2") for c in codes) else "NO",
          "2xx response documented" if any(c.startswith("2") for c in codes)
          else "No 2xx response")
    check(16, "YES" if any(c.startswith("4") for c in codes) else "NO",
          "4xx response documented" if any(c.startswith("4") for c in codes)
          else "No 4xx response")
    check(17, "YES" if any(c.startswith("5") for c in codes) else "NO",
          "5xx response documented" if any(c.startswith("5") for c in codes)
          else "No 5xx response")

    # Q18 — response enums
    components = spec.get("components", {})
    schemas = components.get("schemas", {})
    resp_enum = any("enum" in str(v) for v in schemas.values())
    check(18, "YES" if resp_enum else "NO",
          "Enum found in response schemas" if resp_enum else "No enums in response schemas")

    # Q19 — $ref usage
    path_str = json.dumps(spec.get("paths", {}))
    inline_count = path_str.count('"properties"')
    ref_count = path_str.count('"$ref"')
    if ref_count > 0 and inline_count == 0:
        check(19, "YES", f"{ref_count} $ref usage(s), no inline schemas in paths")
    elif ref_count > 0:
        check(19, "PARTIAL", "Mix of $ref and inline schemas")
    else:
        check(19, "NO", "No $ref usage — schemas are inlined")

    # Q20 — security scheme
    sec_schemes = components.get("securitySchemes", {})
    check(20, "YES" if sec_schemes else "NO",
          f"Security schemes: {list(sec_schemes.keys())}" if sec_schemes
          else "No securitySchemes in components")

    # Q21 — components/schemas reuse
    check(21, "YES" if schemas else "NO",
          f"{len(schemas)} schema(s) in components" if schemas
          else "No schemas in components")

    # Q22 — version
    version = spec.get("info", {}).get("version", "")
    check(22, "YES" if version and version != "TODO" else "NO",
          f"Version: {version}" if version else "No version in info block")

    yes = sum(1 for c in checks if c["status"] == "YES")
    partial = sum(1 for c in checks if c["status"] == "PARTIAL")
    score_pct = round((yes + partial * 0.5) / 22 * 100)

    return {
        "score_percent": score_pct,
        "checks": checks,
        "summary": {"yes": yes, "partial": partial,
                    "no": sum(1 for c in checks if c["status"] == "NO")},
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python score_yaml.py <spec.yaml> [--json]")
        sys.exit(1)

    path = sys.argv[1]
    as_json = "--json" in sys.argv

    try:
        spec = load_yaml(path)
    except Exception as e:
        print(f"ERROR loading {path}: {e}")
        sys.exit(1)

    result = score(spec)

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        pct = result["score_percent"]
        s = result["summary"]
        print(f"\nDocForge OpenAPI Compliance Score: {pct}%")
        print(f"  YES: {s['yes']}  PARTIAL: {s['partial']}  NO: {s['no']}\n")
        for c in result["checks"]:
            icon = "✓" if c["status"] == "YES" else "~" if c["status"] == "PARTIAL" else "✗"
            print(f"  {icon} Q{c['id']:2d} [{c['status']:<7}] {c['finding']}")
        print()
        if pct >= 80:
            print("→ Publication-ready")
        elif pct >= 60:
            print("→ Good foundation — review PARTIAL/NO items above")
        else:
            print("→ Significant gaps — see NO items above")


if __name__ == "__main__":
    main()