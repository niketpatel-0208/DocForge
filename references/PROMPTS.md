# LLM Prompt Reference

## System prompt (API doc generation)

The system prompt instructs Claude to output only valid YAML with no markdown fences,
followed by two metadata lines: `CONFIDENCE:` and `MISSING:`.

Key rules enforced in the system prompt:

1. **Never write TODO** — infer from context, mark with `# inferred` comment
2. **`info.description` must be 30+ lines** covering: purpose, read/write type,
   HTTP method, access control, key input parameters, output keys, key behavior steps
3. **Response schemas must have concrete typed properties** — never `additionalProperties: true`
4. **Every response status code must have 2+ named examples** derived from the
   source code's string literals and error messages
5. **All schemas in `components/schemas`** referenced via `$ref` — never inlined
6. **Security scheme must be defined** even if IP-based (use `apiKey` in header)
7. **Output minimum 200 lines of YAML** — skeleton docs are rejected

## User prompt structure

The user prompt is assembled with:

```
SERVICE METADATA:
  service_name, language, framework

ENDPOINT METADATA:
  method, path, handler_name, file, line, comments, params, returns

FULL SOURCE CODE (labelled sections):
  === ROUTE REGISTRATION FILE: path ===
  <source>
  === CONTROLLER/HANDLER FILE: path ===
  <source>
  === MODEL/STRUCT FILE: path ===
  <source>

EXISTING DOC FRAGMENT (if any)
```

Max source context: **30,000 characters**
Max output tokens: **12,000**

## Field extraction rules (explicitly in prompt)

| Tag / pattern | Extraction rule |
|---|---|
| `json:"field_name"` | Use `field_name` as the API field name |
| `binding:"required"` | Mark field as `required: true` |
| `validate:"required"` | Mark field as `required: true` |
| `json:",omitempty"` | Mark field as optional |
| No binding tag | Mark field as optional |
| `enum` or comment with values | Generate `enum:` list |

## Response example extraction rules

For every `if` / `else if` block that returns an error:
- Extract the literal error string
- Create a named example with that exact string as the `message` or equivalent field
- Assign the appropriate HTTP status code

For success responses:
- Extract the JSON fields written by the handler (`c.JSON`, `json.Marshal`, etc.)
- Create at least 2 named success examples with realistic values

## Output format

```yaml
openapi: 3.0.0
info:
  ...
tags:
  ...
servers:
  ...
paths:
  ...
components:
  securitySchemes:
    ...
  schemas:
    ...
```

Followed by (not part of YAML):
```
CONFIDENCE: 0.0-1.0
MISSING: comma-separated list of fields that could not be inferred