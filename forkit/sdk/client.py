"""
forkit.sdk.client
─────────────────
Canonical Python SDK for forkit-core.

`forkit.*` is the primary public namespace. The legacy `forkit_core.*` package
is kept as a compatibility shim and re-exports the classes defined here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..domain.hashing import HashEngine
from ..domain.lineage import LineageGraph, LineageNode, NodeType
from ..registry.local import LocalRegistry
from ..schemas import (
    AgentArchitecture,
    AgentPassport,
    AgentTaskType,
    CreatorInfo,
    ModelPassport,
    SystemPromptRecord,
    TaskType,
)
from ..sync import RemoteSyncBridge


class ModelClient:
    """Fluent interface for model passport operations."""

    def __init__(self, registry: LocalRegistry):
        self._registry = registry

    def register(
        self,
        name: str,
        version: str,
        architecture: str,
        creator: dict[str, Any] | CreatorInfo,
        task_type: str | TaskType = TaskType.TEXT_GENERATION,
        **kwargs: Any,
    ) -> str:
        if isinstance(creator, dict):
            creator = CreatorInfo.from_dict(creator).to_dict()
        elif isinstance(creator, CreatorInfo):
            creator = creator.to_dict()
        passport = ModelPassport(
            name=name,
            version=version,
            task_type=task_type,
            architecture=architecture,
            creator=creator,
            **kwargs,
        )
        return self._registry.register_model(passport)

    def register_passport(self, passport: ModelPassport) -> str:
        return self._registry.register_model(passport)

    def get(self, passport_id: str) -> ModelPassport | None:
        return self._registry.get_model(passport_id)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        return self._registry.list(passport_type="model", status=status)

    def delete(self, passport_id: str) -> bool:
        return self._registry.delete(passport_id)

    def hash_artifact(self, path: str | Path) -> str:
        return HashEngine.hash_artifact(path)

    def hash_config(self, config: dict[str, Any]) -> str:
        return HashEngine.hash_config(config)


class AgentClient:
    """Fluent interface for agent passport operations."""

    def __init__(self, registry: LocalRegistry):
        self._registry = registry

    def register(
        self,
        name: str,
        version: str,
        model_id: str,
        creator: dict[str, Any] | CreatorInfo,
        task_type: str | AgentTaskType = AgentTaskType.OTHER,
        architecture: str | AgentArchitecture = AgentArchitecture.REACT,
        system_prompt: str | SystemPromptRecord | None = None,
        **kwargs: Any,
    ) -> str:
        if isinstance(creator, dict):
            creator = CreatorInfo.from_dict(creator).to_dict()
        elif isinstance(creator, CreatorInfo):
            creator = creator.to_dict()

        if isinstance(system_prompt, str):
            system_prompt = SystemPromptRecord(
                hash=HashEngine.hash_system_prompt(system_prompt),
                length_chars=len(system_prompt),
            )
        if isinstance(system_prompt, SystemPromptRecord):
            system_prompt = system_prompt.to_dict()

        passport = AgentPassport(
            name=name,
            version=version,
            model_id=model_id,
            task_type=task_type,
            architecture=architecture,
            creator=creator,
            system_prompt=system_prompt,
            **kwargs,
        )
        return self._registry.register_agent(passport)

    def register_passport(self, passport: AgentPassport) -> str:
        return self._registry.register_agent(passport)

    def get(self, passport_id: str) -> AgentPassport | None:
        return self._registry.get_agent(passport_id)

    def list(self, status: str | None = None) -> list[dict[str, Any]]:
        return self._registry.list(passport_type="agent", status=status)

    def delete(self, passport_id: str) -> bool:
        return self._registry.delete(passport_id)

    def hash_config(self, config: dict[str, Any]) -> str:
        return HashEngine.hash_config(config)

    def hash_system_prompt(self, prompt_text: str) -> str:
        return HashEngine.hash_system_prompt(prompt_text)


class LineageClient:
    """Read-only access to lineage data with JSON-safe outputs."""

    def __init__(self, registry: LocalRegistry):
        self._registry = registry

    @property
    def graph(self) -> LineageGraph:
        return self._registry.lineage

    def ancestors(self, passport_id: str) -> list[dict[str, Any]]:
        return [node.to_dict() for node in self.graph.ancestors(passport_id)]

    def descendants(self, passport_id: str) -> list[dict[str, Any]]:
        return [node.to_dict() for node in self.graph.descendants(passport_id)]

    def models(self) -> list[dict[str, Any]]:
        return [node.to_dict() for node in self.graph.nodes_by_type(NodeType.MODEL)]

    def agents(self) -> list[dict[str, Any]]:
        return [node.to_dict() for node in self.graph.nodes_by_type(NodeType.AGENT)]

    def to_dict(self) -> dict[str, Any]:
        return self.graph.to_dict()


class SyncClient:
    """Cursor-based export and remote push helpers for the local outbox."""

    def __init__(self, registry: LocalRegistry):
        self._registry = registry
        self._bridge = RemoteSyncBridge(registry)

    def export(
        self,
        *,
        after: int = 0,
        limit: int = 100,
        passport_type: str | None = None,
    ) -> dict[str, Any]:
        return self._registry.export_changes(
            after=after,
            limit=limit,
            passport_type=passport_type,
        )

    def push(
        self,
        endpoint: str,
        *,
        target: str | None = None,
        after: int | None = None,
        limit: int = 100,
        passport_type: str | None = None,
        timeout: float = 30.0,
        token: str | None = None,
        source: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._bridge.push(
            endpoint,
            target=target,
            after=after,
            limit=limit,
            passport_type=passport_type,
            timeout=timeout,
            token=token,
            source=source,
            headers=headers,
        )

    def cursor(self, target: str) -> int:
        return self._registry.get_sync_cursor(target)

    def status(self) -> dict[str, Any]:
        return self._bridge.status()


class ForkitClient:
    """
    Top-level SDK client for the local forkit registry.

    Supports both the fluent style:

        client.models.register(...)

    and the direct-passport style:

        client.register_model(ModelPassport(...))
    """

    def __init__(self, registry_root: str | Path = "~/.forkit/registry") -> None:
        self._registry = LocalRegistry(root=registry_root)
        self._hash = HashEngine()
        self.models = ModelClient(self._registry)
        self.agents = AgentClient(self._registry)
        self.lineage = LineageClient(self._registry)
        self.sync = SyncClient(self._registry)

    def register_model(self, passport: ModelPassport) -> str:
        return self.models.register_passport(passport)

    def register_agent(self, passport: AgentPassport) -> str:
        return self.agents.register_passport(passport)

    def get(self, passport_id: str) -> ModelPassport | AgentPassport | None:
        return self._registry.get(passport_id)

    def get_model(self, passport_id: str) -> ModelPassport | None:
        return self._registry.get_model(passport_id)

    def get_agent(self, passport_id: str) -> AgentPassport | None:
        return self._registry.get_agent(passport_id)

    def list(
        self,
        passport_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._registry.list(passport_type=passport_type, status=status)

    def search(self, query: str) -> list[dict[str, Any]]:
        return self._registry.search(query)

    def stats(self) -> dict[str, Any]:
        return self._registry.stats()

    def ancestors(self, passport_id: str) -> list[LineageNode]:
        return self._registry.lineage.ancestors(passport_id)

    def descendants(self, passport_id: str) -> list[LineageNode]:
        return self._registry.lineage.descendants(passport_id)

    def verify(self, passport_id: str) -> dict[str, Any]:
        return self._registry.verify_passport(passport_id)

    def hash_artifact(self, path: str | Path) -> str:
        return self._hash.hash_artifact(path)

    def hash_config(self, config: dict[str, Any]) -> str:
        return self._hash.hash_config(config)

    # ── Maintenance ────────────────────────────────────────────────────────────

    def rebuild_index(self) -> int:
        return self._registry.rebuild_index()

    def delete(self, passport_id: str) -> bool:
        return self._registry.delete(passport_id)

    @property
    def registry(self) -> LocalRegistry:
        return self._registry
