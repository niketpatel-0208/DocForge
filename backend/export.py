"""Export helpers — package YAML + metadata for download or copy."""
import json
import zipfile
import io
from datetime import datetime, timezone


def package_yaml(service_name: str, yaml_content: str, score: dict, metadata: dict) -> bytes:
    """Create a zip bundle with the YAML and a JSON metadata file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{service_name}-openapi.yaml", yaml_content)
        meta = {
            "service": service_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pre_score": score.get("score_percent", 0),
            "critical_gaps": score.get("critical_gaps", []),
            **metadata,
        }
        zf.writestr("docforge-metadata.json", json.dumps(meta, indent=2))
    buf.seek(0)
    return buf.read()


def package_sop(service_name: str, sop_content: str, metadata: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{service_name}-sop.md", sop_content)
        meta = {
            "service": service_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
        zf.writestr("docforge-metadata.json", json.dumps(meta, indent=2))
    buf.seek(0)
    return buf.read()
