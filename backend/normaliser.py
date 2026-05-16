"""Normaliser — converts parser output into a language-agnostic context packet for Claude."""
from dataclasses import dataclass, asdict
from typing import Any
from go_parser import RouteInfo
from php_parser import PHPRouteInfo
from infra_parser import InfraContext


@dataclass
class EndpointContext:
    service_name: str
    language: str
    method: str
    path: str
    handler_name: str
    file: str
    line: int
    comments: list[str]
    params: list[dict]
    returns: list[dict]
    framework: str
    existing_doc_fragment: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContextPacket:
    service_name: str
    language: str
    framework: str
    endpoints: list[EndpointContext]
    infra: dict
    file_list: list[str]
    last_commit_date: str = ""
    project_id: str = ""

    def to_dict(self) -> dict:
        return {
            "service_name": self.service_name,
            "language": self.language,
            "framework": self.framework,
            "endpoints": [e.to_dict() for e in self.endpoints],
            "infra": self.infra,
            "file_list": self.file_list,
            "last_commit_date": self.last_commit_date,
            "project_id": self.project_id,
        }


def normalise_go_routes(routes: list[RouteInfo], service_name: str) -> list[EndpointContext]:
    return [
        EndpointContext(
            service_name=service_name,
            language="go",
            method=r.method,
            path=r.path,
            handler_name=r.handler,
            file=r.file,
            line=r.line,
            comments=r.comments,
            params=r.params,
            returns=r.returns,
            framework=r.framework,
        )
        for r in routes
    ]


def normalise_php_routes(routes: list[PHPRouteInfo], service_name: str) -> list[EndpointContext]:
    return [
        EndpointContext(
            service_name=service_name,
            language="php",
            method=r.method,
            path=r.path,
            handler_name=r.handler,
            file=r.file,
            line=r.line,
            comments=r.comments,
            params=[],
            returns=[],
            framework=r.framework,
        )
        for r in routes
    ]


def build_context_packet(
    service_name: str,
    go_routes: list[RouteInfo] = None,
    php_routes: list[PHPRouteInfo] = None,
    infra_ctx: InfraContext = None,
    file_list: list[str] = None,
    last_commit_date: str = "",
    project_id: str = "",
) -> ContextPacket:
    endpoints: list[EndpointContext] = []
    language = "unknown"
    framework = "unknown"

    if go_routes:
        endpoints.extend(normalise_go_routes(go_routes, service_name))
        language = "go"
        if go_routes:
            framework = go_routes[0].framework

    if php_routes:
        endpoints.extend(normalise_php_routes(php_routes, service_name))
        if language == "unknown":
            language = "php"
            if php_routes:
                framework = php_routes[0].framework

    infra_dict = {}
    if infra_ctx:
        from dataclasses import asdict
        infra_dict = asdict(infra_ctx)

    return ContextPacket(
        service_name=service_name,
        language=language,
        framework=framework,
        endpoints=endpoints,
        infra=infra_dict,
        file_list=file_list or [],
        last_commit_date=last_commit_date,
        project_id=str(project_id),
    )
