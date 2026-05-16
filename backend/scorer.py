"""OpenAPI doc scorer — 22-criteria rubric matching the official evaluation report."""
import yaml
from typing import Any


def _load_yaml_safe(yaml_content: str) -> tuple[dict | None, str]:
    try:
        data = yaml.safe_load(yaml_content)
        return data, ""
    except yaml.YAMLError as e:
        return None, str(e)


def _has_meaningful_description(desc: str | None) -> bool:
    """Check if a description is meaningful (not just the field name restated)."""
    if not desc or not isinstance(desc, str):
        return False
    desc = desc.strip()
    return len(desc) > 10  # More than just a word or two


def score_openapi_yaml(yaml_content: str) -> dict:
    """Run the full 22-check rubric against an OpenAPI YAML string."""
    doc, err = _load_yaml_safe(yaml_content)
    if doc is None:
        return {
            "score_percent": 0,
            "parse_error": err,
            "checks": [],
            "critical_gaps": ["YAML parse error — document is not valid"],
            "quick_fixes": [{"issue": "Invalid YAML", "fix": "Correct the YAML syntax"}],
        }

    checks = []
    info = doc.get("info", {})
    paths = doc.get("paths", {})
    servers = doc.get("servers", [])
    components = doc.get("components", {})
    schemas = components.get("schemas", {})
    examples_section = components.get("examples", {})
    security_schemes = components.get("securitySchemes", {})

    # Collect all operations
    ops = []
    for path_str, methods in paths.items():
        if isinstance(methods, dict):
            for method, op in methods.items():
                if method.lower() in ("get", "post", "put", "patch", "delete", "options", "head"):
                    ops.append((method.upper(), path_str, op or {}))

    # Collect all request body properties across operations
    def _get_request_props(op: dict) -> dict:
        """Extract request body properties from an operation."""
        rb = op.get("requestBody", {})
        if not isinstance(rb, dict):
            return {}
        content = rb.get("content", {})
        for ct, ct_val in content.items():
            if isinstance(ct_val, dict):
                schema = ct_val.get("schema", {})
                if isinstance(schema, dict):
                    # Handle $ref to components/schemas
                    if "$ref" in schema:
                        ref_name = schema["$ref"].split("/")[-1]
                        return schemas.get(ref_name, {}).get("properties", {})
                    return schema.get("properties", {})
        return {}

    def _get_request_required(op: dict) -> list:
        """Extract required array from request body schema."""
        rb = op.get("requestBody", {})
        if not isinstance(rb, dict):
            return []
        content = rb.get("content", {})
        for ct, ct_val in content.items():
            if isinstance(ct_val, dict):
                schema = ct_val.get("schema", {})
                if isinstance(schema, dict):
                    if "$ref" in schema:
                        ref_name = schema["$ref"].split("/")[-1]
                        return schemas.get(ref_name, {}).get("required", [])
                    return schema.get("required", [])
        return []

    def _add(id_: int, status: str, finding: str, positive: list = None, issues: list = None):
        entry = {"id": id_, "status": status, "finding": finding}
        if positive:
            entry["positive"] = positive
        if issues:
            entry["issues"] = issues
        checks.append(entry)

    # ──────────────────────────────────────────────────────────────────────────
    # Q1: HTTP methods match operation semantics
    # ──────────────────────────────────────────────────────────────────────────
    if not ops:
        _add(1, "NA", "No operations found.")
    else:
        semantic_ok = all(
            not (m in ("GET", "HEAD") and "requestBody" in op)
            for m, _, op in ops
        )
        _add(1, "YES" if semantic_ok else "NO",
             "HTTP methods align with operation semantics." if semantic_ok
             else "GET/HEAD operations have a requestBody — incorrect semantics.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q2: Endpoints clearly listed with full paths
    # ──────────────────────────────────────────────────────────────────────────
    if paths:
        _add(2, "YES", f"{len(paths)} endpoint path(s) clearly defined.",
             positive=[f"paths.{p}" for p in paths.keys()])
    else:
        _add(2, "NO", "No paths defined in spec.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q3: Production + Dev/Stage server URLs (domain names only)
    # ──────────────────────────────────────────────────────────────────────────
    prod_servers = [
        s for s in servers if isinstance(s, dict)
        and s.get("url")
        and "TODO" not in s.get("url", "")
        and "localhost" not in s.get("url", "")
        and "dev" not in s.get("url", "").lower()
        and "stage" not in s.get("url", "").lower()
        and "test" not in s.get("url", "").lower()
        and "sandbox" not in s.get("url", "").lower()
    ]
    dev_servers = [
        s for s in servers if isinstance(s, dict)
        and s.get("url")
        and any(k in s.get("url", "").lower() for k in ("dev", "stage", "test", "sandbox"))
    ]
    if prod_servers and dev_servers:
        _add(3, "YES", f"Production and dev/stage server URLs defined.")
    elif prod_servers or dev_servers:
        _add(3, "PARTIAL", f"Only {'production' if prod_servers else 'dev/stage'} server URL defined.")
    else:
        _add(3, "NO", "No valid server URLs defined (missing production and dev/stage).")

    # ──────────────────────────────────────────────────────────────────────────
    # Q4: Request content types explicitly specified
    # ──────────────────────────────────────────────────────────────────────────
    needs_body = [(m, p, op) for m, p, op in ops if m in ("POST", "PUT", "PATCH")]
    if not needs_body:
        _add(4, "NA", "No POST/PUT/PATCH operations.")
    else:
        has_ct = all(
            op.get("requestBody", {}).get("content") if isinstance(op.get("requestBody"), dict) else False
            for _, _, op in needs_body
        )
        _add(4, "YES" if has_ct else "NO",
             "Request content types explicitly specified." if has_ct
             else "Missing explicit content type on request body.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q5: Data types for ALL inputs (params + body fields)
    # ──────────────────────────────────────────────────────────────────────────
    all_typed = True
    typed_count = 0
    total_fields = 0
    for _, _, op in ops:
        # Check query/path parameters
        for param in op.get("parameters", []):
            total_fields += 1
            if param.get("schema", {}).get("type"):
                typed_count += 1
            else:
                all_typed = False
        # Check request body properties
        props = _get_request_props(op)
        for prop_name, prop_val in props.items():
            total_fields += 1
            if isinstance(prop_val, dict) and prop_val.get("type"):
                typed_count += 1
            else:
                all_typed = False

    if total_fields == 0:
        _add(5, "NA", "No input fields found.")
    elif all_typed:
        _add(5, "YES", f"All {total_fields} input fields have explicit data types.")
    elif typed_count / total_fields > 0.5:
        _add(5, "PARTIAL", f"{typed_count}/{total_fields} input fields have explicit types.")
    else:
        _add(5, "NO", f"Only {typed_count}/{total_fields} input fields have explicit types.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q6: All request params defined with required status
    # ──────────────────────────────────────────────────────────────────────────
    has_required_array = False
    for _, _, op in ops:
        required_list = _get_request_required(op)
        if required_list:
            has_required_array = True
            break
        rb = op.get("requestBody", {})
        if isinstance(rb, dict) and rb.get("required") is True:
            has_required_array = True
            break

    if not needs_body:
        _add(6, "NA", "No write operations with request body.")
    elif has_required_array:
        _add(6, "YES", "Required fields are explicitly listed in schema.")
    else:
        _add(6, "NO", "No required array defined on request body schema.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q7: Request params have meaningful descriptions
    # ──────────────────────────────────────────────────────────────────────────
    desc_count = 0
    total_props = 0
    for _, _, op in ops:
        props = _get_request_props(op)
        for pname, pval in props.items():
            total_props += 1
            if isinstance(pval, dict) and _has_meaningful_description(pval.get("description")):
                desc_count += 1

    if total_props == 0:
        _add(7, "NA", "No request body properties found.")
    elif desc_count == total_props:
        _add(7, "YES", f"All {total_props} request properties have meaningful descriptions.")
    elif desc_count / total_props >= 0.5:
        _add(7, "PARTIAL", f"{desc_count}/{total_props} request properties have meaningful descriptions.")
    else:
        _add(7, "NO", f"Only {desc_count}/{total_props} request properties have meaningful descriptions.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q8: Request params have example values
    # ──────────────────────────────────────────────────────────────────────────
    example_count = 0
    for _, _, op in ops:
        props = _get_request_props(op)
        for pname, pval in props.items():
            if isinstance(pval, dict) and "example" in pval:
                example_count += 1

    if total_props == 0:
        _add(8, "NA", "No request body properties found.")
    elif example_count == total_props:
        _add(8, "YES", f"All {total_props} request properties have example values.")
    elif example_count / total_props >= 0.5:
        _add(8, "PARTIAL", f"{example_count}/{total_props} request properties have examples.")
    else:
        _add(8, "NO", f"Only {example_count}/{total_props} request properties have examples.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q9: Default values for optional request params
    # ──────────────────────────────────────────────────────────────────────────
    optional_count = 0
    defaults_count = 0
    for _, _, op in ops:
        props = _get_request_props(op)
        required_list = _get_request_required(op)
        for pname, pval in props.items():
            if pname not in required_list:
                optional_count += 1
                if isinstance(pval, dict) and "default" in pval:
                    defaults_count += 1

    if optional_count == 0:
        _add(9, "NA", "No optional request parameters found.")
    elif defaults_count == optional_count:
        _add(9, "YES", f"All {optional_count} optional parameters have default values.")
    elif defaults_count / optional_count >= 0.5:
        _add(9, "PARTIAL", f"{defaults_count}/{optional_count} optional parameters have defaults.")
    else:
        _add(9, "NO", f"Only {defaults_count}/{optional_count} optional parameters have defaults.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q10: ENUM constraints for categorical request params
    # ──────────────────────────────────────────────────────────────────────────
    categorical_count = 0
    enum_count = 0
    for _, _, op in ops:
        props = _get_request_props(op)
        for pname, pval in props.items():
            if isinstance(pval, dict):
                ex = pval.get("example", "")
                # Detect categorical: example is "0" or "1", or description mentions flag/set
                if str(ex) in ("0", "1") or (isinstance(pval.get("description", ""), str) and
                        any(kw in pval.get("description", "").lower() for kw in ("set to", "flag", "\"0\"", "\"1\""))):
                    categorical_count += 1
                    if "enum" in pval:
                        enum_count += 1

    if categorical_count == 0:
        _add(10, "NA", "No categorical request parameters detected.")
    elif enum_count == categorical_count:
        _add(10, "YES", f"All {categorical_count} categorical parameters have enum constraints.")
    elif enum_count / categorical_count >= 0.5:
        _add(10, "PARTIAL", f"{enum_count}/{categorical_count} categorical parameters have enums.")
    else:
        _add(10, "NO", f"Only {enum_count}/{categorical_count} categorical parameters have enums.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q11: Response content types explicitly specified
    # ──────────────────────────────────────────────────────────────────────────
    resp_with_content = 0
    resp_total = 0
    for _, _, op in ops:
        for code, resp in op.get("responses", {}).items():
            if isinstance(resp, dict):
                resp_total += 1
                if resp.get("content"):
                    resp_with_content += 1

    if resp_total == 0:
        _add(11, "NA", "No responses defined.")
    elif resp_with_content == resp_total:
        _add(11, "YES", f"All {resp_total} responses have explicit content types.")
    elif resp_with_content / resp_total >= 0.5:
        _add(11, "PARTIAL", f"{resp_with_content}/{resp_total} responses have content types.")
    else:
        _add(11, "NO", f"Only {resp_with_content}/{resp_total} responses have content types.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q12: Response schemas with explicit data types
    # ──────────────────────────────────────────────────────────────────────────
    resp_schema_typed = True
    resp_schemas_found = 0
    for schema_name, schema_val in schemas.items():
        if isinstance(schema_val, dict) and schema_val.get("properties"):
            for prop_name, prop_val in schema_val["properties"].items():
                resp_schemas_found += 1
                if not isinstance(prop_val, dict) or not prop_val.get("type"):
                    resp_schema_typed = False

    if resp_schemas_found == 0:
        # Check inline response schemas
        for _, _, op in ops:
            for code, resp in op.get("responses", {}).items():
                if isinstance(resp, dict):
                    for ct, ct_val in resp.get("content", {}).items():
                        if isinstance(ct_val, dict):
                            schema = ct_val.get("schema", {})
                            if isinstance(schema, dict) and schema.get("properties"):
                                for pn, pv in schema["properties"].items():
                                    resp_schemas_found += 1
                                    if not isinstance(pv, dict) or not pv.get("type"):
                                        resp_schema_typed = False

    if resp_schemas_found == 0:
        _add(12, "NO", "No response schema properties found.")
    elif resp_schema_typed:
        _add(12, "YES", f"All {resp_schemas_found} response schema properties have explicit types.")
    else:
        _add(12, "PARTIAL", "Some response schema properties lack explicit types.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q13: Response properties have meaningful descriptions
    # ──────────────────────────────────────────────────────────────────────────
    resp_desc_count = 0
    resp_prop_total = 0
    for schema_name, schema_val in schemas.items():
        if isinstance(schema_val, dict) and schema_val.get("properties"):
            for prop_name, prop_val in schema_val["properties"].items():
                resp_prop_total += 1
                if isinstance(prop_val, dict) and _has_meaningful_description(prop_val.get("description")):
                    resp_desc_count += 1

    if resp_prop_total == 0:
        _add(13, "NA", "No response schema properties found.")
    elif resp_desc_count == resp_prop_total:
        _add(13, "YES", f"All {resp_prop_total} response properties have meaningful descriptions.")
    elif resp_desc_count / resp_prop_total >= 0.5:
        _add(13, "PARTIAL", f"{resp_desc_count}/{resp_prop_total} response properties have descriptions.")
    else:
        _add(13, "NO", f"Only {resp_desc_count}/{resp_prop_total} response properties have descriptions.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q14: Response schemas include examples
    # ──────────────────────────────────────────────────────────────────────────
    has_response_example = any(
        "example" in str(op.get("responses", {})) or "examples" in str(op.get("responses", {}))
        for _, _, op in ops
    )
    _add(14, "YES" if has_response_example else "NO",
         "Response schemas include example values." if has_response_example
         else "No response examples found.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q15: 2xx response schemas documented
    # ──────────────────────────────────────────────────────────────────────────
    has_2xx_schema = any(
        any(
            str(code).startswith("2") and isinstance(resp, dict) and
            ("schema" in str(resp.get("content", {})) or "$ref" in str(resp.get("content", {})))
            for code, resp in op.get("responses", {}).items()
        )
        for _, _, op in ops
    )
    _add(15, "YES" if has_2xx_schema else "NO",
         "2xx success response has a documented schema." if has_2xx_schema
         else "No 2xx response schema found.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q16: 4xx response schemas documented
    # ──────────────────────────────────────────────────────────────────────────
    has_4xx = any(
        any(str(code).startswith("4") for code in op.get("responses", {}).keys())
        for _, _, op in ops
    )
    _add(16, "YES" if has_4xx else "NO",
         "At least one 4xx response documented." if has_4xx
         else "No 4xx error response documented.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q17: 5xx response schemas documented
    # ──────────────────────────────────────────────────────────────────────────
    has_5xx = any(
        any(str(code).startswith("5") for code in op.get("responses", {}).keys())
        for _, _, op in ops
    )
    _add(17, "YES" if has_5xx else "NO",
         "At least one 5xx response documented." if has_5xx
         else "No 5xx error response documented.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q18: ENUM constraints for categorical response fields
    # ──────────────────────────────────────────────────────────────────────────
    resp_categorical = 0
    resp_enum_count = 0
    for schema_name, schema_val in schemas.items():
        if isinstance(schema_val, dict) and schema_val.get("properties"):
            for prop_name, prop_val in schema_val["properties"].items():
                if isinstance(prop_val, dict):
                    desc = prop_val.get("description", "")
                    # Response fields like CODE, RESPONSE, STATUS are categorical
                    if (prop_name.upper() in ("CODE", "STATUS", "RESPONSE") or
                            (isinstance(desc, str) and any(kw in desc for kw in ("success", "failure", "Success", "FAILURE")))):
                        resp_categorical += 1
                        if "enum" in prop_val:
                            resp_enum_count += 1

    if resp_categorical == 0:
        _add(18, "NA", "No categorical response fields detected.")
    elif resp_enum_count == resp_categorical:
        _add(18, "YES", f"All {resp_categorical} categorical response fields have enum constraints.")
    elif resp_enum_count / resp_categorical >= 0.5:
        _add(18, "PARTIAL", f"{resp_enum_count}/{resp_categorical} categorical response fields have enums.")
    else:
        _add(18, "NO", f"Only {resp_enum_count}/{resp_categorical} categorical response fields have enums.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q19: Response structure consistent across status codes (shared via $ref)
    # ──────────────────────────────────────────────────────────────────────────
    uses_shared_schema = False
    for _, _, op in ops:
        refs = set()
        for code, resp in op.get("responses", {}).items():
            resp_str = str(resp)
            if "$ref" in resp_str:
                # Extract ref paths
                import re
                ref_matches = re.findall(r'\$ref[\'\":\s]+([^\s\'"]+)', resp_str)
                refs.update(ref_matches)
        if len(refs) > 0:
            uses_shared_schema = True

    _add(19, "YES" if uses_shared_schema else "NO",
         "Responses use shared schemas via $ref for consistency." if uses_shared_schema
         else "Response schemas are inline — not reusing shared components.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q20: Authentication mechanism clearly defined
    # ──────────────────────────────────────────────────────────────────────────
    if security_schemes:
        # Check if the scheme is actually applied
        top_security = doc.get("security", [])
        op_securities = [op.get("security") for _, _, op in ops]

        # security: [] on operation means explicitly no auth (IP-based)
        has_explicit_empty = any(s == [] for s in op_securities if s is not None)
        has_applied = any(s for s in op_securities if s) or bool(top_security)

        if has_applied or has_explicit_empty:
            _add(20, "YES", "Security scheme defined and applied/documented on operations.")
        else:
            _add(20, "PARTIAL", "Security scheme defined but not applied to any operation.")
    else:
        _add(20, "NO", "No security scheme defined.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q21: Schemas defined in components and reused via $ref
    # ──────────────────────────────────────────────────────────────────────────
    ref_count = str(doc).count("$ref")
    component_schemas = len(schemas)

    if component_schemas > 0 and ref_count >= 2:
        _add(21, "YES", f"{component_schemas} component schema(s) defined with {ref_count} $ref usages.")
    elif component_schemas > 0 or ref_count > 0:
        _add(21, "PARTIAL", "Some schemas in components but not fully reused via $ref.")
    else:
        _add(21, "NO", "No component schemas — all schemas are inline.")

    # ──────────────────────────────────────────────────────────────────────────
    # Q22: Versioning info present
    # ──────────────────────────────────────────────────────────────────────────
    has_version = bool(info.get("version"))
    _add(22, "YES" if has_version else "NO",
         f"Version info present: {info.get('version')}" if has_version
         else "No version info in the info block.")

    # ── Calculate final score ─────────────────────────────────────────────────
    yes = sum(1 for c in checks if c["status"] == "YES")
    partial = sum(1 for c in checks if c["status"] == "PARTIAL")
    na = sum(1 for c in checks if c["status"] == "NA")
    denom = len(checks) - na
    score = round((yes + 0.5 * partial) / denom * 100) if denom > 0 else 0

    critical_gaps = [c["finding"] for c in checks if c["status"] == "NO" and c["id"] in (2, 3, 7, 16, 17, 21)]
    quick_fixes = [
        {"issue": c["finding"], "fix": _suggest_fix(c["id"])}
        for c in checks if c["status"] in ("NO", "PARTIAL")
    ]

    return {
        "score_percent": score,
        "checks": checks,
        "critical_gaps": critical_gaps,
        "quick_fixes": quick_fixes,
        "parse_error": None,
        "summary": {
            "yes": yes,
            "no": sum(1 for c in checks if c["status"] == "NO"),
            "partial": partial,
            "na": na,
        },
    }


def _suggest_fix(check_id: int) -> str:
    fixes = {
        1: "Ensure GET/HEAD operations don't have requestBody; use POST/PUT for write operations.",
        2: "Add at least one path entry under the 'paths' key.",
        3: "Add production AND dev/stage server entries under 'servers' with domain-only URLs.",
        4: "Add content: {'application/json': {schema: ...}} to requestBody.",
        5: "Add explicit 'type' to every request parameter and body field schema.",
        6: "Add a 'required' array to the request body schema listing all mandatory fields.",
        7: "Write meaningful, consumer-focused descriptions for each request body property.",
        8: "Add 'example' values to each request body property.",
        9: "Add 'default' values to optional request parameters where server has deterministic defaults.",
        10: "Add 'enum' constraints to categorical/flag parameters (e.g. \"0\"/\"1\" fields).",
        11: "Add 'content: {application/json: ...}' to all response definitions.",
        12: "Add explicit 'type' to all response schema properties.",
        13: "Write meaningful descriptions for response schema properties (purpose, format, values).",
        14: "Add 'example' or 'examples' to at least one response.",
        15: "Add a schema with $ref for 2xx success responses.",
        16: "Add a 4xx error response with schema and examples.",
        17: "Add a 5xx error response with schema and examples.",
        18: "Add 'enum' to categorical response fields (e.g. CODE, STATUS, RESPONSE).",
        19: "Move response schemas to components/schemas and reference via $ref for consistency.",
        20: "Define a security scheme in components/securitySchemes and apply it to operations.",
        21: "Move inline schemas to components/schemas and reference via $ref.",
        22: "Add 'version' to the info block (e.g. '1.0.0').",
    }
    return fixes.get(check_id, "Review and fix this criterion.")
