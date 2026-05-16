"""Claude API client via LiteLLM proxy — v2 with improved prompts."""
import os
import time
import json
import anthropic
from typing import Optional

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "https://imllm.intermesh.net")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-6")

_client: Optional[anthropic.Anthropic] = None


def get_client(api_key: str = "", base_url: str = "") -> anthropic.Anthropic:
    global _client
    key = api_key or LITELLM_API_KEY
    url = base_url or LITELLM_BASE_URL
    if not key:
        raise ValueError("No LLM API key provided. Set LITELLM_API_KEY in .env or send via header.")
    if _client is None or api_key:
        _client = anthropic.Anthropic(api_key=key, base_url=url)
    return _client


def call_claude(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 4000,
    api_key: str = "",
    retries: int = 1,
) -> str:
    client = get_client(api_key)
    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except Exception as e:
            if attempt < retries:
                time.sleep(10)
                continue
            raise


# ── Prompt templates (v3 — aggressive quality, no lazy TODOs) ────────────────

_API_DOC_SYSTEM = """You are an expert API documentation engineer. You generate production-grade OpenAPI 3.0 YAML
specifications that score 80%+ on a strict 22-criterion compliance evaluation.

Your output must be ONLY valid YAML — no markdown fences, no explanatory text before or after.
After the YAML, add exactly two metadata lines starting with CONFIDENCE: and MISSING:.

ABSOLUTE RULES — VIOLATION OF ANY WILL FAIL THE EVALUATION:

1. NEVER write "TODO" in any value field. If you cannot determine something from the source code,
   make a reasonable inference based on the handler name, variable names, Go/PHP conventions,
   and HTTP semantics. Mark inferred values with a YAML comment `# inferred` at the end of the line.

2. The `info.description` MUST be a multi-line block scalar (`|`) of AT LEAST 30 lines.
   It must contain ALL of these sections (use "Not determinable from source" only as last resort):
   - Opening paragraph summarizing the API purpose
   - "This is a [Read/Write] API."
   - "It accepts HTTP [GET/POST/PUT/DELETE] requests."
   - **Access Control** paragraph
   - **Key input parameters** as a bulleted list (every param with name, purpose, type)
   - **Output Keys Description** — bullet list explaining each response field
   - **Key Behavior** — step-by-step processing logic as bullet points

3. Response schemas MUST have concrete typed properties — NEVER use `additionalProperties: true`
   or a bare `type: object` without properties. Study the handler source code for:
   - JSON marshal struct tags (Go: `json:"field_name"`)
   - Response writer calls (c.JSON, w.Write, json.NewEncoder, echo.JSON, etc.)
   - Return statements, error messages, success messages
   - If you truly cannot find response fields, infer a standard response with at minimum:
     status (string), message (string), data (object with described sub-fields).

4. Every response status code MUST have at least 2 named examples under `examples:`.
   - 200: at least 2 examples (success, success with different data)
   - 4xx: at least 3 examples (different validation failures extracted from if-checks in code)
   - 5xx: at least 1 example (downstream failure)
   Examples MUST include realistic values derived from the handler's string literals and constants.

5. Use `$ref` references to `components/schemas` for ALL response schemas — never inline.

6. Every request parameter/property MUST have: `description` (>15 chars), `type`, `example`.
   Optional fields MUST also have `default`. Flag fields MUST have `enum`.

7. `components/securitySchemes` MUST be present. If auth is IP-based, use:
   ```
   securitySchemes:
     ipWhitelist:
       type: apiKey
       in: header
       name: X-Forwarded-For
       description: Access governed by server-side IP whitelisting.
   ```
   If auth is unclear, define a reasonable scheme and add `# inferred` comment.

8. `tags:` section MUST be present with a meaningful tag name and description.

9. `servers:` MUST have at least one entry with an actual URL — infer from code imports,
   config files, or domain patterns. Never use just "TODO" as a URL.

10. The output MUST be at least 200 lines of YAML. Skeleton docs are unacceptable."""

_API_DOC_USER = """Generate a comprehensive OpenAPI 3.0 YAML specification for this API endpoint.
You MUST study the handler source code line by line and extract EVERY:
- Request parameter (from query params, path params, form fields, JSON body fields)
- Validation check (every if/else that returns an error)
- Response code and message (every c.JSON, w.Write, http.Error, return statement)
- Error string literal (these become your response examples)
- Queue/DB/Redis interaction (these become your Key Behavior bullet points)
- Struct field with json tags (these become your response schema properties)

SERVICE METADATA:
- Service Name: {service_name}
- Language: {language}
- Framework: {framework}

ENDPOINT METADATA:
- HTTP Method: {method}
- Path: {path}
- Handler Function: {handler_name}
- Source File: {file} (line {line})
- Inline Comments: {comments}
- Detected Parameters: {params}
- Detected Returns: {returns}

HANDLER SOURCE CODE — THIS IS YOUR PRIMARY SOURCE OF TRUTH.
Read every line. Extract every parameter, validation, and response from it:
```
{handler_source}
```

EXISTING DOC FRAGMENT (if any — use as reference but improve):
{existing_doc_fragment}

EXAMPLE OF EXPECTED OUTPUT QUALITY — your output must match this level of detail and length:
```yaml
openapi: 3.0.0
info:
  title: CentraliseSMSService
  version: 1.0.0
  description: |
    This POST service sends an SMS to IndiaMART users through the centralized notification system.
    It validates each request against the process registry by performing a `process` lookup, IP whitelist
    check, and daily send threshold check, then dispatches the payload to the appropriate RabbitMQ queue
    for downstream SMS delivery.

    This is a Write API.
    It accepts HTTP POST requests.
    All input params are case sensitive.

    **Access Control:** This API does not use token-based authentication. Access is governed by
    IP whitelisting — each `process` has a configured list of allowed server IPs.

    The key input parameters are:
    - **process**: Registered process name used to validate the caller. (string)
    - **mobile**: Mobile number of the recipient. (string)
    - **sms_content**: Content of the SMS message. (string)

    **Output Keys Description:**
    - `CODE` : Response code
    - `RESPONSE` : Success/Failure status
    - `MESSAGE` : Message regarding request processing
    - `ERROR` : Error detail from the service

    **Key Behavior:**
    - Looks up `process` in the process registry and validates the caller's IP.
    - Checks the daily send count against the process threshold.
    - Routes to the appropriate RabbitMQ queue based on routing flags.

tags:
  - name: Central SMS Service
    description: Operations for sending transactional and bulk SMS.

servers:
  - url: http://dev-cnotify.indiamart.com
    description: Development Server

paths:
  /sms:
    post:
      tags: [Central SMS Service]
      summary: Send an SMS via the centralized notification system.
      description: |
        Validates the request, then enqueues the SMS payload.
      security: []
      requestBody:
        required: true
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              required: [process, mobile, sms_content]
              properties:
                process:
                  description: Registered process name for validation.
                  type: string
                  example: "AppTrack service"
                mobile:
                  description: Mobile number of the recipient.
                  type: string
                  example: "8743039748"
                sent_via_bulk:
                  description: Set to "1" to route to bulk SMS queue.
                  type: string
                  enum: ["0", "1"]
                  default: "0"
                  example: "1"
      responses:
        "200":
          description: SMS accepted and queued successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SmsResponse'
              examples:
                standard_success:
                  summary: SMS queued (transactional)
                  value:
                    CODE: "200"
                    RESPONSE: "Success"
                    MESSAGE: "SMS SENT SUCCESSFULLY"
                    ERROR: ""
        "401":
          description: Validation failure.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SmsResponse'
              examples:
                process_missing:
                  summary: process not provided
                  value:
                    CODE: "401"
                    RESPONSE: "FAILURE"
                    MESSAGE: "PROCESS IS MISSING"
                    ERROR: ""
                threshold_exceeded:
                  summary: Daily send count exceeded
                  value:
                    CODE: "401"
                    RESPONSE: "FAILURE"
                    MESSAGE: "THRESHOLD LIMIT EXCEEDED"
                    PROCESS_NAME: "AppTrack service"
                    ERROR: ""

components:
  securitySchemes:
    ipWhitelist:
      type: apiKey
      in: header
      name: X-Forwarded-For
      description: Access governed by IP whitelisting.
  schemas:
    SmsResponse:
      type: object
      properties:
        CODE:
          description: Response code indicating outcome.
          type: string
          enum: ["200", "401", "501"]
          example: "200"
        RESPONSE:
          description: Success or failure status.
          type: string
          enum: ["Success", "FAILURE"]
          example: "Success"
        MESSAGE:
          description: Human-readable outcome description.
          type: string
          example: "SMS SENT SUCCESSFULLY"
        ERROR:
          description: Technical error detail. Empty for success.
          type: string
          example: ""
```

YOUR OUTPUT MUST MATCH OR EXCEED THE ABOVE LEVEL OF DETAIL.
- info.description must be 30+ lines
- Every validation branch in the source code = one response example
- Every string literal in error responses = an example value
- Response schema properties must be concrete (never additionalProperties:true)

QUALITY CHECKLIST (your output WILL be scored against all 22):
Q1: HTTP methods match operation semantics
Q2: Endpoints clearly listed with full paths
Q3: Server URLs present (infer dev/prod from code patterns)
Q4: Request content types explicitly specified
Q5: Data types for ALL inputs
Q6: Required status on all request params
Q7: Meaningful descriptions (>15 chars, not just field name)
Q8: Example values on all params
Q9: Default values for optional params
Q10: ENUM on categorical/flag params
Q11: Response content types specified
Q12: Response schema properties have explicit types
Q13: Response properties have meaningful descriptions
Q14: Response examples present (2+ per status code)
Q15: 2xx response schema documented
Q16: 4xx response schema documented
Q17: 5xx response schema documented
Q18: ENUM on categorical response fields
Q19: Consistent response structure via shared $ref
Q20: Security scheme defined
Q21: Schemas in components, reused via $ref
Q22: Version info present

After the YAML, write exactly:
CONFIDENCE: <float 0.0-1.0>
MISSING: <comma-separated list of items that could not be inferred>"""


_SOP_SYSTEM = """You are a technical writer generating internal SOPs from infrastructure and deployment
files. You only state what you can verify from the provided files. You never invent
procedures. If a step requires information not present in the files, you write
[NEEDS HUMAN INPUT: description of what is needed] in that section."""

_SOP_USER = """Generate a structured SOP document for this service based on the following files.
Infer appropriate sections from what you can see in the files. Common sections include:
Overview, Prerequisites, Deployment Steps, Rollback Procedure, Health Checks,
Environment Variables, Contact / Escalation — but only include sections that have
verifiable content in the provided files.

Service: {service_name}
Files analysed:
{files_with_contents}

Start the document with:
# {service_name} — Operations SOP
# DRAFT — Generated by DocForge. Review and verify before use.
# Source files: {file_list}
# Generated: {timestamp}

After the document, on a new line write:
CONFIDENCE: 0.0-1.0
SECTIONS_INFERRED: comma-separated list of section names included
NEEDS_HUMAN_INPUT: comma-separated list of gaps that require manual completion"""

_PRESCORE_SYSTEM = """You are an API documentation compliance checker. Evaluate the provided OpenAPI YAML
against each criterion. Output JSON only."""

_PRESCORE_USER = """Evaluate this OpenAPI spec:
{yaml_content}

For each criterion below, output YES, NO, PARTIAL, or NA with a one-sentence finding.

Criteria:
1. HTTP methods match operation semantics (read vs write)
2. Endpoint paths are clearly defined
3. Production server URL is present (not localhost, not TODO)
4. Staging/dev server URL is present
5. Auth model is unambiguous (no security:[] with active scheme)
6. Request body content type is explicit
7. Response schemas use shared components
8. All parameters have explicit types
9. At least one response includes an example
10. Optional parameters have defaults or documented omission behavior
11. At least one 4xx error response is documented
12. At least one 5xx error response is documented

Output format:
{{
  "checks": [{{"id": 1, "status": "YES|NO|PARTIAL|NA", "finding": "..."}}, ...],
  "score_percent": 0-100,
  "critical_gaps": ["..."],
  "quick_fixes": [{{"issue": "...", "fix": "..."}}]
}}"""


def generate_api_doc(
    endpoint: dict,
    api_key: str = "",
    handler_source: str = "",
) -> tuple[str, float, list[str]]:
    """Generate OpenAPI doc with enhanced prompts and full handler source context."""
    user = _API_DOC_USER.format(
        service_name=endpoint.get("service_name", ""),
        language=endpoint.get("language", ""),
        framework=endpoint.get("framework", "unknown"),
        method=endpoint.get("method", ""),
        path=endpoint.get("path", ""),
        handler_name=endpoint.get("handler_name", ""),
        file=endpoint.get("file", ""),
        line=endpoint.get("line", ""),
        comments="\n".join(endpoint.get("comments", [])),
        params=str(endpoint.get("params", [])),
        returns=str(endpoint.get("returns", [])),
        handler_source=handler_source[:20000] if handler_source else "(source not available — infer from metadata above)",
        existing_doc_fragment=endpoint.get("existing_doc_fragment", ""),
    )
    raw = call_claude(_API_DOC_SYSTEM, user, max_tokens=8000, api_key=api_key, retries=1)
    yaml_text, confidence, missing = _parse_api_doc_output(raw)
    return yaml_text, confidence, missing


def _parse_api_doc_output(raw: str) -> tuple[str, float, list[str]]:
    confidence = 0.5
    missing: list[str] = []
    lines = raw.splitlines()
    yaml_lines = []
    for line in lines:
        if line.startswith("CONFIDENCE:"):
            try:
                confidence = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("MISSING:"):
            missing = [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]
        else:
            yaml_lines.append(line)

    # Strip any markdown fences that slipped through
    text = "\n".join(yaml_lines).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]

    return text.strip(), confidence, missing


def generate_sop(
    service_name: str,
    files_with_contents: str,
    file_list: str,
    timestamp: str,
    api_key: str = "",
) -> str:
    user = _SOP_USER.format(
        service_name=service_name,
        files_with_contents=files_with_contents,
        file_list=file_list,
        timestamp=timestamp,
    )
    return call_claude(_SOP_SYSTEM, user, max_tokens=2000, api_key=api_key, retries=1)


def pre_score_doc(yaml_content: str, api_key: str = "") -> dict:
    user = _PRESCORE_USER.format(yaml_content=yaml_content)
    raw = call_claude(_PRESCORE_SYSTEM, user, max_tokens=800, api_key=api_key, retries=1)
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(clean)
    except Exception:
        return {
            "raw": raw,
            "score_percent": 0,
            "checks": [],
            "critical_gaps": [],
            "quick_fixes": [],
            "parse_error": True,
        }
