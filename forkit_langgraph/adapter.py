"""Minimal LangGraph adapter for building and registering agent passports."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Mapping

from forkit.domain.hashing import HashEngine
from forkit.sdk import ForkitClient
from forkit.schemas import (
    AgentArchitecture,
    AgentPassport,
    AgentTaskType,
    CreatorInfo,
    SystemPromptRecord,
)


class BoundLangGraphRunnable:
    """Lazy registration wrapper around a compiled LangGraph-style runnable."""

    def __init__(
        self,
        runnable: Any,
        *,
        adapter: "LangGraphPassportAdapter",
        registration_kwargs: Mapping[str, Any],
    ) -> None:
        self.runnable = runnable
        self._adapter = adapter
        self._registration_kwargs = dict(registration_kwargs)
        self._passport_id: str | None = None

    @property
    def passport_id(self) -> str | None:
        return self._passport_id

    def ensure_registered(self) -> str:
        """Register the underlying graph once and return the passport ID."""
        if self._passport_id is None:
            self._passport_id = self._adapter.register_graph(
                self.runnable,
                **self._registration_kwargs,
            )
        return self._passport_id

    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        self.ensure_registered()
        return self.runnable.invoke(*args, **kwargs)

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        self.ensure_registered()
        return await self.runnable.ainvoke(*args, **kwargs)

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        self.ensure_registered()
        return self.runnable.stream(*args, **kwargs)

    async def astream(self, *args: Any, **kwargs: Any) -> Any:
        self.ensure_registered()
        return await self.runnable.astream(*args, **kwargs)

    def batch(self, *args: Any, **kwargs: Any) -> Any:
        self.ensure_registered()
        return self.runnable.batch(*args, **kwargs)

    async def abatch(self, *args: Any, **kwargs: Any) -> Any:
        self.ensure_registered()
        return await self.runnable.abatch(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runnable, name)


class LangGraphPassportAdapter:
    """
    Minimal bridge between LangGraph-style configs and forkit agent passports.

    The current skeleton intentionally avoids importing LangGraph at runtime.
    Callers pass a serializable ``graph_spec`` dict, which becomes the stable
    artifact hash for the derived agent passport unless an explicit
    ``artifact_hash`` is provided.
    """

    def __init__(
        self,
        client: ForkitClient | None = None,
        registry_root: str | Path = "~/.forkit/registry",
    ) -> None:
        self.client = client or ForkitClient(registry_root=registry_root)

    def hash_graph(self, graph_spec: Mapping[str, Any]) -> str:
        """Derive a stable hash for a LangGraph-style configuration payload."""
        return HashEngine.hash_config(dict(graph_spec))

    def extract_graph_spec(
        self,
        graph: Any,
        *,
        compile_config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Extract a deterministic graph spec from a LangGraph builder or compiled graph.

        This uses duck typing against the public LangGraph object model:
        compiled graphs expose ``.builder``, while builders expose ``nodes``,
        ``edges`` and optional ``waiting_edges``.
        """
        builder = self._resolve_builder(graph)
        graph_spec: dict[str, Any] = {
            "graph_type": self._describe_value(graph),
            "builder_type": self._describe_value(builder),
            "compiled": builder is not graph,
            "nodes": self._extract_nodes(builder),
            "edges": self._extract_edges(builder),
        }
        schemas = self._extract_schemas(builder)
        if schemas:
            graph_spec["schemas"] = schemas

        graph_name = self._resolve_graph_name(graph) or self._resolve_graph_name(builder)
        if graph_name is not None:
            graph_spec["name"] = graph_name

        if compile_config:
            graph_spec["compile"] = self._normalise_value(dict(compile_config))

        return graph_spec

    def build_agent_passport(
        self,
        *,
        name: str,
        version: str,
        model_id: str,
        creator: dict[str, Any] | CreatorInfo,
        graph_spec: Mapping[str, Any] | None = None,
        task_type: str | AgentTaskType = AgentTaskType.OTHER,
        architecture: str | AgentArchitecture = AgentArchitecture.REACT,
        system_prompt: str | SystemPromptRecord | dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentPassport:
        """Build an AgentPassport from a LangGraph-oriented configuration."""
        creator_payload = self._normalise_creator(creator)
        system_prompt_payload = self._normalise_system_prompt(system_prompt)

        artifact_hash = kwargs.pop("artifact_hash", None)
        metadata_payload = dict(metadata or {})

        if graph_spec is not None:
            graph_hash = self.hash_graph(graph_spec)
            if artifact_hash is None:
                artifact_hash = graph_hash
            langgraph_metadata = dict(metadata_payload.get("langgraph") or {})
            langgraph_metadata["graph_hash"] = graph_hash
            langgraph_metadata["graph_spec"] = self._normalise_value(dict(graph_spec))
            metadata_payload["langgraph"] = langgraph_metadata

        return AgentPassport(
            name=name,
            version=version,
            model_id=model_id,
            task_type=task_type,
            architecture=architecture,
            creator=creator_payload,
            system_prompt=system_prompt_payload,
            artifact_hash=artifact_hash,
            metadata=metadata_payload or None,
            **kwargs,
        )

    def register_agent(self, **kwargs: Any) -> str:
        """Build and persist an AgentPassport derived from LangGraph inputs."""
        passport = self.build_agent_passport(**kwargs)
        return self.client.register_agent(passport)

    def register_graph(
        self,
        graph: Any,
        *,
        name: str,
        version: str,
        model_id: str,
        creator: dict[str, Any] | CreatorInfo,
        graph_spec: Mapping[str, Any] | None = None,
        compile_config: Mapping[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Register a builder or compiled graph using extracted runtime structure."""
        extracted_graph_spec = dict(
            graph_spec or self.extract_graph_spec(graph, compile_config=compile_config)
        )
        metadata_payload = dict(metadata or {})
        runtime_metadata = dict(metadata_payload.get("langgraph_runtime") or {})
        runtime_metadata["compiled"] = bool(extracted_graph_spec.get("compiled"))
        if compile_config:
            runtime_metadata["compile"] = self._normalise_value(dict(compile_config))
        metadata_payload["langgraph_runtime"] = runtime_metadata
        return self.register_agent(
            name=name,
            version=version,
            model_id=model_id,
            creator=creator,
            graph_spec=extracted_graph_spec,
            metadata=metadata_payload,
            **kwargs,
        )

    def compile_and_register(
        self,
        builder: Any,
        *,
        compile_kwargs: Mapping[str, Any] | None = None,
        **registration_kwargs: Any,
    ) -> tuple[Any, str]:
        """Compile a LangGraph builder and immediately register the compiled graph."""
        resolved_compile_kwargs = dict(compile_kwargs or {})
        compiled = builder.compile(**resolved_compile_kwargs)
        passport_id = self.register_graph(
            compiled,
            compile_config=resolved_compile_kwargs,
            **registration_kwargs,
        )
        return compiled, passport_id

    def bind_graph(self, graph: Any, **registration_kwargs: Any) -> BoundLangGraphRunnable:
        """Wrap a graph-like runnable and register it lazily on first execution."""
        return BoundLangGraphRunnable(
            graph,
            adapter=self,
            registration_kwargs=registration_kwargs,
        )

    def compile_and_bind(
        self,
        builder: Any,
        *,
        compile_kwargs: Mapping[str, Any] | None = None,
        **registration_kwargs: Any,
    ) -> BoundLangGraphRunnable:
        """Compile a builder and return a lazy registration wrapper for the result."""
        resolved_compile_kwargs = dict(compile_kwargs or {})
        compiled = builder.compile(**resolved_compile_kwargs)
        return self.bind_graph(
            compiled,
            compile_config=resolved_compile_kwargs,
            **registration_kwargs,
        )

    @staticmethod
    def _normalise_creator(creator: dict[str, Any] | CreatorInfo) -> dict[str, Any]:
        if isinstance(creator, CreatorInfo):
            return creator.to_dict()
        return CreatorInfo.from_dict(creator).to_dict()

    @staticmethod
    def _normalise_system_prompt(
        system_prompt: str | SystemPromptRecord | dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if system_prompt is None:
            return None
        if isinstance(system_prompt, str):
            return SystemPromptRecord(
                hash=HashEngine.hash_system_prompt(system_prompt),
                length_chars=len(system_prompt),
            ).to_dict()
        if isinstance(system_prompt, SystemPromptRecord):
            return system_prompt.to_dict()
        return dict(system_prompt)

    @classmethod
    def _resolve_builder(cls, graph: Any) -> Any:
        return getattr(graph, "builder", graph)

    @classmethod
    def _resolve_graph_name(cls, graph: Any) -> str | None:
        name = getattr(graph, "name", None)
        if isinstance(name, str) and name:
            return name
        get_name = getattr(graph, "get_name", None)
        if callable(get_name):
            try:
                resolved = get_name()
            except TypeError:
                return None
            if isinstance(resolved, str) and resolved:
                return resolved
        return None

    @classmethod
    def _extract_nodes(cls, builder: Any) -> list[str]:
        nodes = getattr(builder, "nodes", {})
        if isinstance(nodes, Mapping):
            return sorted(str(key) for key in nodes.keys())
        return []

    @classmethod
    def _extract_edges(cls, builder: Any) -> list[list[str]]:
        raw_edges = getattr(builder, "_all_edges", None)
        if raw_edges is None:
            edges = set(getattr(builder, "edges", set()) or set())
            waiting_edges = getattr(builder, "waiting_edges", set()) or set()
            for starts, end in waiting_edges:
                for start in starts:
                    edges.add((start, end))
            raw_edges = edges

        normalised = [
            [str(start), str(end)]
            for start, end in raw_edges
        ]
        return sorted(normalised, key=lambda edge: (edge[0], edge[1]))

    @classmethod
    def _extract_schemas(cls, builder: Any) -> dict[str, Any]:
        schemas = {
            "state": cls._describe_value(getattr(builder, "state_schema", None)),
            "input": cls._describe_value(getattr(builder, "input_schema", None)),
            "output": cls._describe_value(getattr(builder, "output_schema", None)),
            "context": cls._describe_value(getattr(builder, "context_schema", None)),
        }
        return {key: value for key, value in schemas.items() if value is not None}

    @classmethod
    def _normalise_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {
                str(key): cls._normalise_value(item)
                for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            }
        if isinstance(value, (list, tuple)):
            return [cls._normalise_value(item) for item in value]
        if isinstance(value, set):
            normalised = [cls._normalise_value(item) for item in value]
            return sorted(normalised, key=cls._sort_key)
        return cls._describe_value(value)

    @classmethod
    def _describe_value(cls, value: Any) -> str | None:
        if value is None:
            return None
        target = value if inspect.isclass(value) or inspect.isfunction(value) else type(value)
        module = getattr(target, "__module__", "")
        qualname = getattr(target, "__qualname__", getattr(target, "__name__", str(target)))
        if module:
            return f"{module}.{qualname}"
        return qualname

    @staticmethod
    def _sort_key(value: Any) -> str:
        if isinstance(value, dict):
            return str(
                sorted(
                    (key, LangGraphPassportAdapter._sort_key(item))
                    for key, item in value.items()
                )
            )
        return repr(value)


LangGraphAdapter = LangGraphPassportAdapter
