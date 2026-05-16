"""Infrastructure file parser — extracts deployment context from Dockerfile, K8s, Terraform, Makefile, shell."""
import re
from dataclasses import dataclass, field

INFRA_FILE_PATTERNS = [
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "deployment.yaml", "deployment.yml", "service.yaml", "service.yml",
    "ingress.yaml", "ingress.yml", "configmap.yaml", "configmap.yml",
    "Makefile", "makefile",
]
INFRA_EXTENSIONS = {".tf", ".sh", ".yaml", ".yml", ".env.example", ".env.sample"}


@dataclass
class InfraContext:
    has_dockerfile: bool = False
    has_k8s: bool = False
    has_terraform: bool = False
    has_makefile: bool = False
    has_shell_scripts: bool = False
    env_vars: list[str] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    health_check: str = ""
    deploy_commands: list[str] = field(default_factory=list)
    k8s_resources: list[str] = field(default_factory=list)
    terraform_resources: list[str] = field(default_factory=list)
    base_image: str = ""
    files_analysed: list[str] = field(default_factory=list)


def _parse_dockerfile(source: str, ctx: InfraContext):
    ctx.has_dockerfile = True
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("FROM "):
            ctx.base_image = s[5:].strip()
        elif s.startswith("EXPOSE "):
            ctx.ports.append(s[7:].strip())
        elif s.startswith("ENV "):
            parts = s[4:].split("=", 1)
            if parts:
                ctx.env_vars.append(parts[0].strip())
        elif "HEALTHCHECK" in s:
            ctx.health_check = s


def _parse_k8s(source: str, ctx: InfraContext):
    ctx.has_k8s = True
    for line in source.splitlines():
        s = line.strip()
        if s.startswith("kind:"):
            kind = s[5:].strip()
            if kind not in ctx.k8s_resources:
                ctx.k8s_resources.append(kind)
        m = re.search(r"containerPort:\s*(\d+)", s)
        if m and m.group(1) not in ctx.ports:
            ctx.ports.append(m.group(1))
        m = re.search(r"- name:\s*(\w+)", s)
        if m and "env" in source[:source.find(line)].lower()[-200:]:
            ctx.env_vars.append(m.group(1))


def _parse_makefile(source: str, ctx: InfraContext):
    ctx.has_makefile = True
    for line in source.splitlines():
        s = line.strip()
        if re.match(r"^[a-zA-Z][\w-]*:", s) and "=" not in s:
            target = s.rstrip(":").strip()
            if target and target not in ctx.deploy_commands:
                ctx.deploy_commands.append(target)


def _parse_terraform(source: str, ctx: InfraContext):
    ctx.has_terraform = True
    for m in re.finditer(r'resource\s+"([^"]+)"', source):
        res = m.group(1)
        if res not in ctx.terraform_resources:
            ctx.terraform_resources.append(res)


def _parse_shell(source: str, ctx: InfraContext):
    ctx.has_shell_scripts = True


def parse_infra_files(files: dict[str, str]) -> InfraContext:
    ctx = InfraContext()
    for filename, source in files.items():
        basename = filename.split("/")[-1].split("\\")[-1]
        ext = "." + filename.rsplit(".", 1)[-1] if "." in basename else ""

        is_infra = (
            basename in INFRA_FILE_PATTERNS
            or basename.startswith("Dockerfile")
            or ext in INFRA_EXTENSIONS
        )
        if not is_infra:
            continue

        ctx.files_analysed.append(filename)

        if basename.startswith("Dockerfile"):
            _parse_dockerfile(source, ctx)
        elif basename in ("deployment.yaml", "deployment.yml", "service.yaml", "service.yml",
                          "ingress.yaml", "ingress.yml", "configmap.yaml", "configmap.yml",
                          "docker-compose.yml", "docker-compose.yaml"):
            _parse_k8s(source, ctx)
        elif ext == ".yaml" or ext == ".yml":
            _parse_k8s(source, ctx)
        elif basename in ("Makefile", "makefile"):
            _parse_makefile(source, ctx)
        elif ext == ".tf":
            _parse_terraform(source, ctx)
        elif ext == ".sh":
            _parse_shell(source, ctx)

    return ctx
