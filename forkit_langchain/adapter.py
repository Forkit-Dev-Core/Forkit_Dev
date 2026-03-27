"""Minimal LangChain adapter for registering runnables and capturing runtime events."""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from forkit.domain.hashing import HashEngine
from forkit.sdk import ForkitClient
from forkit.schemas import (
    AgentArchitecture,
    AgentPassport,
    AgentTaskType,
    CreatorInfo,
    SystemPromptRecord,
)
from forkit_langgraph import LangGraphAdapter

try:
    from langchain_core.callbacks import BaseCallbackHandler
except ImportError as exc:  # pragma: no cover - exercised when optional dep is missing
    BaseCallbackHandler = object  # type: ignore[assignment]
    _LANGCHAIN_IMPORT_ERROR = exc
else:
    _LANGCHAIN_IMPORT_ERROR = None


def _require_langchain() -> None:
    if _LANGCHAIN_IMPORT_ERROR is not None:
        raise RuntimeError(
            "LangChain integration requires the optional dependency. "
            "Install with 'forkit-core[langchain]'."
        ) from _LANGCHAIN_IMPORT_ERROR


class ForkitLangChainCallbackHandler(BaseCallbackHandler):
    """Capture a compact runtime summary from LangChain callback events."""

    def __init__(
        self,
        *,
        framework: str = "langchain",
        passport_id: str | None = None,
    ) -> None:
        _require_langchain()
        super().__init__()
        self.framework = framework
        self.passport_id = passport_id
        self.reset()

    def reset(self) -> None:
        self.counts: dict[str, int] = {}
        self.chain_names: list[str] = []
        self.model_names: list[str] = []
        self.tool_names: list[str] = []
        self.tags: list[str] = []
        self.metadata_keys: list[str] = []
        self.events: list[dict[str, Any]] = []

    def attach_passport(self, passport_id: str) -> None:
        self.passport_id = passport_id

    def summary(self) -> dict[str, Any]:
        return {
            "framework": self.framework,
            "passport_id": self.passport_id,
            "counts": dict(self.counts),
            "chains": list(self.chain_names),
            "models": list(self.model_names),
            "tools": list(self.tool_names),
            "tags": list(self.tags),
            "metadata_keys": list(self.metadata_keys),
            "events": list(self.events),
        }

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "chain_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            tags=tags,
            metadata=metadata,
            input_keys=self._describe_payload(inputs),
        )

    def on_chain_end(
        self,
        outputs: dict[str, Any] | list[Any],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "chain_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            output_keys=self._describe_payload(outputs),
        )

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: list[list[Any]],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "chat_model_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            tags=tags,
            metadata=metadata,
            message_batches=len(messages),
        )

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str],
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "llm_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            tags=tags,
            metadata=metadata,
            prompt_count=len(prompts),
        )

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "tool_start",
            run_id=run_id,
            parent_run_id=parent_run_id,
            serialized=serialized,
            tags=tags,
            metadata=metadata,
            input=input_str,
            input_keys=self._describe_payload(inputs or {}),
        )

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "tool_end",
            run_id=run_id,
            parent_run_id=parent_run_id,
            output_type=self._describe_value(output),
        )

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "agent_action",
            run_id=run_id,
            parent_run_id=parent_run_id,
            action_type=self._describe_value(action),
        )

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        **kwargs: Any,
    ) -> Any:
        self._record(
            "agent_finish",
            run_id=run_id,
            parent_run_id=parent_run_id,
            finish_type=self._describe_value(finish),
        )

    def _record(
        self,
        event: str,
        *,
        run_id: Any,
        parent_run_id: Any | None = None,
        serialized: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **details: Any,
    ) -> None:
        self.counts[event] = self.counts.get(event, 0) + 1

        name = self._resolve_serialized_name(serialized)
        if name is not None:
            if event.startswith("chain_"):
                self._append_unique(self.chain_names, name)
            elif event.endswith("_model_start") or event.startswith("llm_"):
                self._append_unique(self.model_names, name)
            elif event.startswith("tool_"):
                self._append_unique(self.tool_names, name)

        for tag in tags or []:
            self._append_unique(self.tags, tag)

        for key in sorted((metadata or {}).keys()):
            self._append_unique(self.metadata_keys, key)

        event_record: dict[str, Any] = {
            "event": event,
            "run_id": str(run_id),
        }
        if parent_run_id is not None:
            event_record["parent_run_id"] = str(parent_run_id)
        if name is not None:
            event_record["name"] = name
        if tags:
            event_record["tags"] = list(tags)
        if metadata:
            event_record["metadata_keys"] = sorted(metadata.keys())

        for key, value in details.items():
            if value is not None:
                event_record[key] = self._normalise_value(value)

        self.events.append(event_record)

    @classmethod
    def _resolve_serialized_name(cls, serialized: dict[str, Any] | None) -> str | None:
        if not isinstance(serialized, Mapping):
            return None
        name = serialized.get("name")
        if isinstance(name, str) and name:
            return name
        identifier = serialized.get("id")
        if isinstance(identifier, list) and identifier:
            return ".".join(str(part) for part in identifier)
        return None

    @classmethod
    def _describe_payload(cls, payload: Any) -> Any:
        if isinstance(payload, Mapping):
            return sorted(str(key) for key in payload.keys())
        if isinstance(payload, list):
            return [cls._describe_value(item) for item in payload[:5]]
        return cls._describe_value(payload)

    @staticmethod
    def _append_unique(target: list[str], value: str) -> None:
        if value not in target:
            target.append(value)

    @classmethod
    def _normalise_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): cls._normalise_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._normalise_value(item) for item in value]
        if isinstance(value, set):
            return [cls._normalise_value(item) for item in sorted(value, key=cls._sort_key)]
        if isinstance(value, Enum):
            return value.value
        if inspect.isclass(value):
            return cls._describe_value(value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if hasattr(value, "to_dict"):
            try:
                return cls._normalise_value(value.to_dict())
            except TypeError:
                pass
        return cls._describe_value(value)

    @staticmethod
    def _sort_key(value: Any) -> str:
        return repr(value)

    @staticmethod
    def _describe_value(value: Any) -> str:
        if inspect.isclass(value):
            return f"{value.__module__}.{value.__qualname__}"
        value_type = type(value)
        return f"{value_type.__module__}.{value_type.__qualname__}"


class BoundLangChainRunnable:
    """Lazy registration wrapper around a LangChain runnable."""

    def __init__(
        self,
        runnable: Any,
        *,
        adapter: "LangChainPassportAdapter",
        registration_kwargs: Mapping[str, Any],
        callback_handler: ForkitLangChainCallbackHandler | None = None,
    ) -> None:
        _require_langchain()
        self.runnable = runnable
        self._adapter = adapter
        self._registration_kwargs = dict(registration_kwargs)
        self._callback_handler = callback_handler or ForkitLangChainCallbackHandler()
        self._passport_id: str | None = None

    @property
    def callback_handler(self) -> ForkitLangChainCallbackHandler:
        return self._callback_handler

    @property
    def passport_id(self) -> str | None:
        return self._passport_id

    def runtime_summary(self) -> dict[str, Any]:
        return self._callback_handler.summary()

    def ensure_registered(self) -> str:
        """Register the underlying runnable once and return the passport ID."""
        if self._passport_id is None:
            self._passport_id = self._adapter.register_runnable(
                self.runnable,
                **self._registration_kwargs,
            )
            self._callback_handler.attach_passport(self._passport_id)
        return self._passport_id

    def invoke(
        self,
        input: Any,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_config = self._merge_config(config)
        return self.runnable.invoke(input, config=merged_config, **kwargs)

    async def ainvoke(
        self,
        input: Any,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_config = self._merge_config(config)
        return await self.runnable.ainvoke(input, config=merged_config, **kwargs)

    def stream(
        self,
        input: Any,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_config = self._merge_config(config)
        return self.runnable.stream(input, config=merged_config, **kwargs)

    async def astream(
        self,
        input: Any,
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_config = self._merge_config(config)
        return await self.runnable.astream(input, config=merged_config, **kwargs)

    def batch(
        self,
        inputs: list[Any],
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_config = self._merge_config(config)
        return self.runnable.batch(inputs, config=merged_config, **kwargs)

    async def abatch(
        self,
        inputs: list[Any],
        config: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_config = self._merge_config(config)
        return await self.runnable.abatch(inputs, config=merged_config, **kwargs)

    def _merge_config(self, config: Mapping[str, Any] | None) -> dict[str, Any]:
        passport_id = self.ensure_registered()
        return self._adapter.merge_runtime_config(
            config,
            callback_handler=self._callback_handler,
            passport_id=passport_id,
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self.runnable, name)


class LangChainPassportAdapter:
    """Minimal bridge between LangChain-style runnables and forkit agent passports."""

    def __init__(
        self,
        client: ForkitClient | None = None,
        registry_root: str | Path = "~/.forkit/registry",
    ) -> None:
        self.client = client or ForkitClient(registry_root=registry_root)
        self._langgraph = LangGraphAdapter(client=self.client)

    def create_callback_handler(
        self,
        *,
        passport_id: str | None = None,
    ) -> ForkitLangChainCallbackHandler:
        return ForkitLangChainCallbackHandler(passport_id=passport_id)

    def hash_runnable(self, runnable_spec: Mapping[str, Any]) -> str:
        """Derive a stable hash for a LangChain-style runnable payload."""
        return HashEngine.hash_config(dict(runnable_spec))

    def extract_runnable_spec(
        self,
        runnable: Any,
        *,
        tools: Sequence[Any] | None = None,
        runnable_config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Extract a deterministic runnable spec from a LangChain runnable or agent."""
        runnable_spec: dict[str, Any] = {
            "runnable_type": self._describe_value(runnable),
        }

        name = self._resolve_name(runnable)
        if name is not None:
            runnable_spec["name"] = name

        graph_json = self._extract_graph_json(runnable)
        if graph_json is not None:
            runnable_spec["graph"] = graph_json

        langgraph_spec = self._extract_langgraph_spec(runnable)
        if langgraph_spec is not None:
            runnable_spec["langgraph"] = langgraph_spec

        schemas = self._extract_schemas(runnable)
        if schemas:
            runnable_spec["schemas"] = schemas

        tools_spec = self._extract_tools_spec(tools)
        if tools_spec:
            runnable_spec["tools"] = tools_spec

        if runnable_config:
            runnable_spec["config"] = self._normalise_value(dict(runnable_config))

        return runnable_spec

    def build_agent_passport(
        self,
        *,
        name: str,
        version: str,
        model_id: str,
        creator: dict[str, Any] | CreatorInfo,
        runnable_spec: Mapping[str, Any] | None = None,
        task_type: str | AgentTaskType = AgentTaskType.OTHER,
        architecture: str | AgentArchitecture = AgentArchitecture.REACT,
        system_prompt: str | SystemPromptRecord | dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentPassport:
        """Build an AgentPassport from a LangChain-oriented configuration."""
        creator_payload = self._normalise_creator(creator)
        system_prompt_payload = self._normalise_system_prompt(system_prompt)

        artifact_hash = kwargs.pop("artifact_hash", None)
        metadata_payload = dict(metadata or {})

        if runnable_spec is not None:
            runnable_hash = self.hash_runnable(runnable_spec)
            if artifact_hash is None:
                artifact_hash = runnable_hash
            langchain_metadata = dict(metadata_payload.get("langchain") or {})
            langchain_metadata["runnable_hash"] = runnable_hash
            langchain_metadata["runnable_spec"] = self._normalise_value(dict(runnable_spec))
            metadata_payload["langchain"] = langchain_metadata

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

    def register_runnable(
        self,
        runnable: Any,
        *,
        name: str,
        version: str,
        model_id: str,
        creator: dict[str, Any] | CreatorInfo,
        runnable_spec: Mapping[str, Any] | None = None,
        tools: Sequence[Any] | None = None,
        runnable_config: Mapping[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Register a LangChain runnable or agent using extracted runtime structure."""
        resolved_runnable_spec = dict(
            runnable_spec
            or self.extract_runnable_spec(
                runnable,
                tools=tools,
                runnable_config=runnable_config,
            )
        )
        metadata_payload = dict(metadata or {})
        runtime_metadata = dict(metadata_payload.get("langchain_runtime") or {})
        runtime_metadata["bound_type"] = self._describe_value(runnable)
        if tools:
            runtime_metadata["tool_names"] = [
                tool_spec["name"]
                for tool_spec in self._extract_tools_spec(tools)
                if "name" in tool_spec
            ]
        if runnable_config:
            runtime_metadata["config"] = self._normalise_value(dict(runnable_config))
        metadata_payload["langchain_runtime"] = runtime_metadata

        passport = self.build_agent_passport(
            name=name,
            version=version,
            model_id=model_id,
            creator=creator,
            runnable_spec=resolved_runnable_spec,
            metadata=metadata_payload,
            **kwargs,
        )
        return self.client.register_agent(passport)

    def bind_runnable(
        self,
        runnable: Any,
        *,
        callback_handler: ForkitLangChainCallbackHandler | None = None,
        **registration_kwargs: Any,
    ) -> BoundLangChainRunnable:
        """Wrap a runnable and register it lazily on first execution."""
        return BoundLangChainRunnable(
            runnable,
            adapter=self,
            registration_kwargs=registration_kwargs,
            callback_handler=callback_handler,
        )

    def create_agent(self, **kwargs: Any) -> Any:
        """Create a LangChain agent via the public factory."""
        _require_langchain()
        from langchain.agents import create_agent

        return create_agent(**kwargs)

    def create_and_register(
        self,
        *,
        model: Any,
        tools: Sequence[Any] | None = None,
        system_prompt: Any | None = None,
        create_kwargs: Mapping[str, Any] | None = None,
        runnable_config: Mapping[str, Any] | None = None,
        **registration_kwargs: Any,
    ) -> tuple[Any, str]:
        """Create a LangChain agent and immediately register it."""
        resolved_create_kwargs = dict(create_kwargs or {})
        agent = self.create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            **resolved_create_kwargs,
        )
        resolved_registration_kwargs = dict(registration_kwargs)
        resolved_registration_kwargs.setdefault(
            "name",
            self._resolve_name(agent) or resolved_create_kwargs.get("name") or "langchain-agent",
        )
        if system_prompt is not None:
            resolved_registration_kwargs.setdefault("system_prompt", system_prompt)
        passport_id = self.register_runnable(
            agent,
            tools=tools,
            runnable_config=runnable_config,
            **resolved_registration_kwargs,
        )
        return agent, passport_id

    def create_and_bind(
        self,
        *,
        model: Any,
        tools: Sequence[Any] | None = None,
        system_prompt: Any | None = None,
        create_kwargs: Mapping[str, Any] | None = None,
        callback_handler: ForkitLangChainCallbackHandler | None = None,
        **registration_kwargs: Any,
    ) -> BoundLangChainRunnable:
        """Create a LangChain agent and return a lazy registration wrapper."""
        resolved_create_kwargs = dict(create_kwargs or {})
        agent = self.create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            **resolved_create_kwargs,
        )
        resolved_registration_kwargs = dict(registration_kwargs)
        resolved_registration_kwargs.setdefault(
            "name",
            self._resolve_name(agent) or resolved_create_kwargs.get("name") or "langchain-agent",
        )
        if system_prompt is not None:
            resolved_registration_kwargs.setdefault("system_prompt", system_prompt)
        if tools is not None:
            resolved_registration_kwargs.setdefault("tools", list(tools))
        return self.bind_runnable(
            agent,
            callback_handler=callback_handler,
            **resolved_registration_kwargs,
        )

    def merge_runtime_config(
        self,
        config: Mapping[str, Any] | None,
        *,
        callback_handler: ForkitLangChainCallbackHandler | None = None,
        passport_id: str | None = None,
    ) -> dict[str, Any]:
        """Attach forkit runtime metadata and callback capture to a LangChain config."""
        resolved = dict(config or {})

        metadata = dict(resolved.get("metadata") or {})
        metadata.setdefault("forkit_framework", "langchain")
        if passport_id is not None:
            metadata.setdefault("forkit_passport_id", passport_id)
        resolved["metadata"] = metadata

        tags = list(resolved.get("tags") or [])
        if "forkit" not in tags:
            tags.append("forkit")
        resolved["tags"] = tags

        if callback_handler is not None:
            callbacks = resolved.get("callbacks")
            if callbacks is None:
                resolved["callbacks"] = [callback_handler]
            elif isinstance(callbacks, list):
                if callback_handler not in callbacks:
                    resolved["callbacks"] = [*callbacks, callback_handler]
            elif isinstance(callbacks, tuple):
                resolved["callbacks"] = [*callbacks, callback_handler]
            elif hasattr(callbacks, "copy") and hasattr(callbacks, "add_handler"):
                copied_callbacks = callbacks.copy()
                copied_callbacks.add_handler(callback_handler, inherit=True)
                resolved["callbacks"] = copied_callbacks
            else:
                resolved["callbacks"] = [callbacks, callback_handler]

        return resolved

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
        return SystemPromptRecord.from_dict(system_prompt).to_dict()

    def _extract_graph_json(self, runnable: Any) -> dict[str, Any] | None:
        if not hasattr(runnable, "get_graph"):
            return None
        try:
            graph = runnable.get_graph()
        except Exception:
            return None
        if hasattr(graph, "to_json"):
            try:
                return self._normalise_value(graph.to_json())
            except Exception:
                return None
        return None

    def _extract_langgraph_spec(self, runnable: Any) -> dict[str, Any] | None:
        if not any(hasattr(runnable, attr) for attr in ("builder", "nodes", "edges")):
            return None
        try:
            return self._langgraph.extract_graph_spec(runnable)
        except Exception:
            return None

    def _extract_schemas(self, runnable: Any) -> dict[str, str]:
        schema_sources = [runnable]
        if hasattr(runnable, "builder"):
            schema_sources.append(runnable.builder)

        schemas: dict[str, str] = {}
        for source in schema_sources:
            for field in ("input_schema", "output_schema", "state_schema", "context_schema"):
                if field in schemas:
                    continue
                value = getattr(source, field, None)
                if value is None:
                    continue
                if callable(value) and not inspect.isclass(value):
                    try:
                        value = value()
                    except TypeError:
                        continue
                if value is not None:
                    schemas[field] = self._describe_value(value)
        return schemas

    def _extract_tools_spec(self, tools: Sequence[Any] | None) -> list[dict[str, Any]]:
        if not tools:
            return []

        tool_specs: list[dict[str, Any]] = []
        for tool in tools:
            if isinstance(tool, Mapping):
                tool_spec = {
                    "tool_type": "mapping",
                    "keys": sorted(str(key) for key in tool.keys()),
                }
                for field in ("name", "description"):
                    value = tool.get(field)
                    if isinstance(value, str) and value:
                        tool_spec[field] = value
                tool_specs.append(tool_spec)
                continue

            tool_spec: dict[str, Any] = {
                "name": self._resolve_tool_name(tool),
                "tool_type": self._describe_value(tool),
            }
            description = getattr(tool, "description", None) or inspect.getdoc(tool)
            if isinstance(description, str) and description:
                tool_spec["description"] = description.strip()
            args_schema = getattr(tool, "args_schema", None)
            if args_schema is not None:
                tool_spec["args_schema"] = self._describe_value(args_schema)
            if hasattr(tool, "return_direct"):
                tool_spec["return_direct"] = bool(getattr(tool, "return_direct"))
            tool_specs.append(tool_spec)

        return tool_specs

    @staticmethod
    def _resolve_name(runnable: Any) -> str | None:
        if hasattr(runnable, "get_name"):
            try:
                name = runnable.get_name()
            except TypeError:
                name = None
            if isinstance(name, str) and name:
                return name
        name = getattr(runnable, "name", None)
        if isinstance(name, str) and name:
            return name
        return None

    @staticmethod
    def _resolve_tool_name(tool: Any) -> str:
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            return name
        name = getattr(tool, "__name__", None)
        if isinstance(name, str) and name:
            return name
        if inspect.isclass(tool):
            return tool.__name__
        return type(tool).__name__

    @classmethod
    def _normalise_value(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): cls._normalise_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._normalise_value(item) for item in value]
        if isinstance(value, set):
            return [cls._normalise_value(item) for item in sorted(value, key=cls._sort_key)]
        if isinstance(value, Enum):
            return value.value
        if inspect.isclass(value):
            return cls._describe_value(value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if hasattr(value, "to_json"):
            try:
                return cls._normalise_value(value.to_json())
            except Exception:
                pass
        if hasattr(value, "to_dict"):
            try:
                return cls._normalise_value(value.to_dict())
            except TypeError:
                pass
        return cls._describe_value(value)

    @staticmethod
    def _sort_key(value: Any) -> str:
        return repr(value)

    @staticmethod
    def _describe_value(value: Any) -> str:
        if inspect.isclass(value):
            return f"{value.__module__}.{value.__qualname__}"
        value_type = type(value)
        return f"{value_type.__module__}.{value_type.__qualname__}"


LangChainAdapter = LangChainPassportAdapter
