"""Local-only MCP server for Forkit Dev Core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from .. import __version__
from ..domain.hashing import HashEngine
from ..sdk import ForkitClient
from ..schemas import AgentPassport, ModelPassport

PassportType = Literal["model", "agent"]
LineageDirection = Literal["ancestors", "descendants", "both"]
PassportStatus = Literal["draft", "active", "deprecated", "revoked"]


class ForkitMCPService:
    """Thin local service layer behind the MCP tool surface."""

    def __init__(self, registry_root: str | Path = "~/.forkit/registry") -> None:
        self.client = ForkitClient(registry_root=registry_root)

    @property
    def registry_root(self) -> str:
        return str(self.client.registry.root)

    def get_passport(self, passport_id: str) -> dict[str, Any]:
        """Return a stored passport by deterministic ID."""
        passport = self.client.get(passport_id)
        if passport is None:
            raise ValueError(f"Passport not found: {passport_id}")
        return passport.to_dict()

    def verify_passport(self, passport_id: str) -> dict[str, Any]:
        """Verify the stored passport content against its deterministic ID."""
        result = self.client.verify(passport_id)
        if result.get("reason") == "not_found":
            raise ValueError(f"Passport not found: {passport_id}")
        return result

    def get_lineage(
        self,
        passport_id: str,
        direction: LineageDirection = "both",
    ) -> dict[str, Any]:
        """Return lineage data for a stored passport."""
        passport = self.client.get(passport_id)
        if passport is None:
            raise ValueError(f"Passport not found: {passport_id}")

        graph = self.client.registry.lineage
        node = graph.get_node(passport_id)
        ancestors = self.client.lineage.ancestors(passport_id) if direction in ("ancestors", "both") else []
        descendants = (
            self.client.lineage.descendants(passport_id) if direction in ("descendants", "both") else []
        )

        return {
            "node": node.to_dict() if node is not None else passport.to_dict(),
            "direction": direction,
            "ancestors": ancestors,
            "descendants": descendants,
        }

    def search_registry(
        self,
        query: str = "",
        passport_type: PassportType | None = None,
        status: PassportStatus | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search or list the local registry without any hosted dependency."""
        if limit < 1:
            raise ValueError("'limit' must be greater than or equal to 1.")

        if query:
            rows = self.client.search(query)
        else:
            rows = self.client.list(passport_type=passport_type, status=status)

        results: list[dict[str, Any]] = []
        for row in rows:
            if passport_type is not None and row.get("passport_type") != passport_type:
                continue
            if status is not None and row.get("status") != status:
                continue
            results.append(_normalise_registry_row(row))

        return {
            "query": query,
            "passport_type": passport_type,
            "status": status,
            "total_matches": len(results),
            "returned": min(limit, len(results)),
            "results": results[:limit],
            "registry_root": self.registry_root,
        }

    def create_draft_passport(
        self,
        passport_type: PassportType,
        name: str,
        version: str,
        creator_name: str,
        creator_organization: str | None = None,
        task_type: str | None = None,
        architecture: str | None = None,
        model_id: str | None = None,
        description: str | None = None,
        license: str = "Apache-2.0",
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Create a draft passport locally without registering it."""
        creator = {
            "name": creator_name,
            "organization": creator_organization,
        }

        if passport_type == "model":
            payload = {
                "passport_type": "model",
                "name": name,
                "version": version,
                "creator": creator,
                "description": description or "Draft ModelPassport created from the local MCP server.",
                "license": license,
                "status": "draft",
                "task_type": task_type or "text-generation",
                "architecture": architecture or "transformer",
            }
            passport = ModelPassport.from_dict(payload)
        else:
            if not model_id:
                raise ValueError("'model_id' is required when creating an agent draft passport.")

            payload = {
                "passport_type": "agent",
                "name": name,
                "version": version,
                "creator": creator,
                "description": description or "Draft AgentPassport created from the local MCP server.",
                "license": license,
                "status": "draft",
                "model_id": model_id,
                "task_type": task_type or "other",
                "architecture": architecture or "ReAct",
                "role": "assistant",
            }
            if system_prompt:
                payload["system_prompt"] = {
                    "hash": HashEngine.hash_system_prompt(system_prompt),
                    "length_chars": len(system_prompt),
                }
            passport = AgentPassport.from_dict(payload)

        payload["id"] = passport.id
        return payload


def _normalise_registry_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    tags = payload.get("tags")
    if isinstance(tags, str):
        try:
            payload["tags"] = json.loads(tags)
        except json.JSONDecodeError:
            payload["tags"] = [tags]
    return payload


def build_mcp_server(registry_root: str | Path = "~/.forkit/registry") -> Any:
    """Build the FastMCP server with local-only Forkit tools."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "MCP support requires the optional 'mcp' dependency. "
            "Install with: pip install 'forkit-core[mcp]'"
        ) from exc

    service = ForkitMCPService(registry_root=registry_root)
    server = FastMCP("Forkit Dev Core", json_response=True)

    @server.tool()
    def get_passport(passport_id: str) -> dict[str, Any]:
        """Return a locally stored Forkit passport by deterministic ID."""
        return service.get_passport(passport_id)

    @server.tool()
    def verify_passport(passport_id: str) -> dict[str, Any]:
        """Verify a stored passport against Forkit's deterministic identity contract."""
        return service.verify_passport(passport_id)

    @server.tool()
    def get_lineage(
        passport_id: str,
        direction: LineageDirection = "both",
    ) -> dict[str, Any]:
        """Return ancestors and descendants for a stored passport."""
        return service.get_lineage(passport_id, direction=direction)

    @server.tool()
    def search_registry(
        query: str = "",
        passport_type: PassportType | None = None,
        status: PassportStatus | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search the local registry by name or creator, or list entries when query is blank."""
        return service.search_registry(
            query=query,
            passport_type=passport_type,
            status=status,
            limit=limit,
        )

    @server.tool()
    def create_draft_passport(
        passport_type: PassportType,
        name: str,
        version: str,
        creator_name: str,
        creator_organization: str | None = None,
        task_type: str | None = None,
        architecture: str | None = None,
        model_id: str | None = None,
        description: str | None = None,
        license: str = "Apache-2.0",
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Create a deterministic draft model or agent passport without storing it."""
        return service.create_draft_passport(
            passport_type=passport_type,
            name=name,
            version=version,
            creator_name=creator_name,
            creator_organization=creator_organization,
            task_type=task_type,
            architecture=architecture,
            model_id=model_id,
            description=description,
            license=license,
            system_prompt=system_prompt,
        )

    return server


def serve_stdio(registry_root: str | Path = "~/.forkit/registry") -> None:
    """Run the local Forkit MCP server over stdio."""
    build_mcp_server(registry_root=registry_root).run()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve the local Forkit Dev Core MCP server over stdio."
    )
    parser.add_argument(
        "--registry-root",
        default="~/.forkit/registry",
        help="Registry root path. Defaults to ~/.forkit/registry.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    serve_stdio(registry_root=Path(args.registry_root).expanduser().resolve())


if __name__ == "__main__":
    main()
