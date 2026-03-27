"""Thin OpenClaw adapter for deriving agent passports from local config and plugins."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from forkit.domain.hashing import HashEngine
from forkit.sdk import ForkitClient
from forkit.schemas import (
    AgentArchitecture,
    AgentCapabilities,
    AgentPassport,
    AgentTaskType,
    CreatorInfo,
    SystemPromptRecord,
    ToolRef,
)


class OpenClawPassportAdapter:
    """
    Build Forkit agent passports from OpenClaw gateway config and plugin manifests.

    The adapter stays intentionally thin: it inspects local files and serializable
    configuration, then derives a stable artifact hash from the resulting spec.
    """

    _REGISTER_PATTERNS = {
        "tools": re.compile(r"registerTool\s*\(\s*\{(.*?)\}\s*(?:,\s*\{(.*?)\})?\s*\)", re.S),
        "commands": re.compile(r"registerCommand\s*\(\s*\{(.*?)\}\s*(?:,\s*\{(.*?)\})?\s*\)", re.S),
        "channels": re.compile(r"registerChannel\s*\(\s*\{(.*?)\}\s*(?:,\s*\{(.*?)\})?\s*\)", re.S),
        "providers": re.compile(r"registerProvider\s*\(\s*\{(.*?)\}\s*(?:,\s*\{(.*?)\})?\s*\)", re.S),
        "hooks": re.compile(r"registerHook\s*\(\s*\{(.*?)\}\s*(?:,\s*\{(.*?)\})?\s*\)", re.S),
    }

    def __init__(
        self,
        client: ForkitClient | None = None,
        registry_root: str | Path = "~/.forkit/registry",
    ) -> None:
        self.client = client or ForkitClient(registry_root=registry_root)

    def hash_agent_spec(self, agent_spec: Mapping[str, Any]) -> str:
        """Derive a stable hash for an OpenClaw agent spec."""
        return HashEngine.hash_config(dict(agent_spec))

    def extract_plugin_spec(self, plugin_root: str | Path) -> dict[str, Any]:
        """Extract a deterministic spec from an OpenClaw plugin directory."""
        root = Path(plugin_root)
        manifest_path = root / "openclaw.plugin.json"
        package_path = root / "package.json"
        manifest = self._read_json_file(manifest_path)
        package = self._read_json_file(package_path)

        manifest_openclaw = self._as_mapping(manifest.get("openclaw"))
        package_openclaw = self._as_mapping(package.get("openclaw"))

        extensions = self._extract_extensions(
            root,
            manifest_openclaw.get("extensions"),
            package_openclaw.get("extensions"),
        )

        return self._compact(
            {
                "root": root.name,
                "name": manifest.get("name") or package.get("name") or root.name,
                "version": manifest.get("version") or package.get("version"),
                "manifest_present": manifest_path.is_file(),
                "package_present": package_path.is_file(),
                "plugin_entry": self._extract_plugin_entry(extensions),
                "extensions": extensions,
                "hooks": self._extract_hook_specs(root / "hooks"),
                "bootstrap_files": sorted(
                    file_name
                    for file_name in ("BOOT.md", "AGENTS.md", "TOOLS.md")
                    if (root / file_name).is_file()
                ),
            }
        )

    def extract_gateway_spec(
        self,
        config: Mapping[str, Any] | str | Path,
        *,
        plugin_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
    ) -> dict[str, Any]:
        """Extract a deterministic OpenClaw gateway spec from config and plugin roots."""
        config_payload, config_name = self._load_config(config)
        plugin_specs = [
            self.extract_plugin_spec(root)
            for root in (plugin_roots or [])
        ]

        agents_block = self._as_mapping(config_payload.get("agents"))
        defaults_block = self._as_mapping(agents_block.get("defaults"))
        entries_block = self._as_mapping(agents_block.get("entries"))
        plugins_block = self._as_mapping(config_payload.get("plugins"))
        plugin_entries = self._as_mapping(plugins_block.get("entries"))
        tools_block = self._as_mapping(config_payload.get("tools"))
        hooks_block = self._as_mapping(config_payload.get("hooks"))
        internal_hooks = self._as_mapping(hooks_block.get("internal"))

        return self._compact(
            {
                "framework": "openclaw",
                "config_file": config_name,
                "agent_defaults": self._extract_agent_defaults(defaults_block),
                "agents": [
                    self._extract_agent_entry(name, self._as_mapping(entry))
                    for name, entry in sorted(entries_block.items(), key=lambda item: str(item[0]))
                ],
                "channels": sorted(
                    str(name)
                    for name in self._as_mapping(config_payload.get("channels")).keys()
                ),
                "tools": {
                    "allow": self._sorted_strings(tools_block.get("allow")),
                    "deny": self._sorted_strings(tools_block.get("deny")),
                },
                "plugins": plugin_specs,
                "plugin_entries": [
                    self._compact(
                        {
                            "name": str(name),
                            "package": self._as_mapping(entry).get("package"),
                            "enabled": self._as_mapping(entry).get("enabled"),
                            "config_keys": sorted(str(key) for key in self._as_mapping(self._as_mapping(entry).get("config")).keys()),
                        }
                    )
                    for name, entry in sorted(plugin_entries.items(), key=lambda item: str(item[0]))
                ],
                "hooks": self._compact(
                    {
                        "internal_enabled": bool(internal_hooks.get("enabled")),
                        "internal_entries": sorted(str(key) for key in self._as_mapping(internal_hooks.get("entries")).keys()),
                    }
                ),
            }
        )

    def build_agent_passport(
        self,
        *,
        name: str,
        version: str,
        model_id: str,
        creator: dict[str, Any] | CreatorInfo,
        agent_spec: Mapping[str, Any],
        task_type: str | AgentTaskType = AgentTaskType.OTHER,
        architecture: str | AgentArchitecture | None = None,
        system_prompt: str | SystemPromptRecord | dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AgentPassport:
        """Build an AgentPassport from an OpenClaw-oriented spec."""
        creator_payload = self._normalise_creator(creator)
        system_prompt_payload = self._normalise_system_prompt(system_prompt)
        agent_spec_payload = self._normalise_value(dict(agent_spec))
        artifact_hash = kwargs.pop("artifact_hash", None) or self.hash_agent_spec(agent_spec_payload)

        tool_refs = kwargs.pop("tools", None)
        if tool_refs is None:
            tool_refs = self._extract_tool_refs(agent_spec_payload)

        capabilities = kwargs.pop("capabilities", {})
        if isinstance(capabilities, AgentCapabilities):
            capabilities = capabilities.to_dict()
        capabilities_payload = {
            **self._as_mapping(capabilities),
            "supports_tool_use": bool(tool_refs),
            "supports_multi_turn": True,
        }

        metadata_payload = dict(metadata or {})
        metadata_payload["openclaw"] = {
            "agent_hash": artifact_hash,
            "agent_spec": agent_spec_payload,
        }

        resolved_architecture = architecture or self._infer_architecture(agent_spec_payload, tool_refs)

        return AgentPassport(
            name=name,
            version=version,
            model_id=model_id,
            task_type=task_type,
            architecture=resolved_architecture,
            creator=creator_payload,
            system_prompt=system_prompt_payload,
            artifact_hash=artifact_hash,
            capabilities=capabilities_payload,
            tools=tool_refs,
            metadata=metadata_payload,
            **kwargs,
        )

    def register_agent(self, **kwargs: Any) -> str:
        """Build and persist an AgentPassport derived from OpenClaw inputs."""
        passport = self.build_agent_passport(**kwargs)
        return self.client.register_agent(passport)

    def register_gateway(
        self,
        config: Mapping[str, Any] | str | Path,
        *,
        plugin_roots: list[str | Path] | tuple[str | Path, ...] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Register an OpenClaw gateway config and optional plugins as one agent passport."""
        agent_spec = self.extract_gateway_spec(config, plugin_roots=plugin_roots)
        metadata_payload = dict(metadata or {})
        metadata_payload.setdefault("integration", {})["framework"] = "openclaw"
        return self.register_agent(
            agent_spec=agent_spec,
            metadata=metadata_payload,
            **kwargs,
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
        return SystemPromptRecord.from_dict(system_prompt).to_dict()

    @staticmethod
    def _as_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return {str(key): item for key, item in value.items()}
        return {}

    @classmethod
    def _read_json_file(cls, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        text = path.read_text(encoding="utf-8")
        return cls._parse_json5_like(text, source=path)

    @classmethod
    def _load_config(
        cls,
        config: Mapping[str, Any] | str | Path,
    ) -> tuple[dict[str, Any], str | None]:
        if isinstance(config, Mapping):
            return cls._normalise_value(dict(config)), None
        path = Path(config)
        payload = cls._read_json_file(path)
        return payload, path.name

    @classmethod
    def _extract_extensions(cls, root: Path, *values: Any) -> list[dict[str, Any]]:
        raw_entries: list[str] = []
        for value in values:
            if isinstance(value, list):
                raw_entries.extend(str(item) for item in value if isinstance(item, (str, Path)))

        unique_entries = sorted(set(raw_entries))
        return [
            cls._compact(
                {
                    "path": entry,
                    "exists": (root / entry).is_file(),
                    "registers": cls._extract_extension_registrations(root / entry),
                }
            )
            for entry in unique_entries
        ]

    @classmethod
    def _extract_plugin_entry(cls, extensions: list[dict[str, Any]]) -> dict[str, Any] | None:
        for extension in extensions:
            if not isinstance(extension, Mapping):
                continue
            registers = cls._as_mapping(extension.get("registers"))
            plugin_entry = cls._as_mapping(registers.get("plugin"))
            if plugin_entry:
                return plugin_entry
        return None

    @classmethod
    def _extract_extension_registrations(cls, path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        source = path.read_text(encoding="utf-8")
        registrations: dict[str, Any] = {}
        plugin_entry = cls._extract_object_signature(source, "definePluginEntry")
        if plugin_entry:
            registrations["plugin"] = plugin_entry

        for key, pattern in cls._REGISTER_PATTERNS.items():
            items: list[dict[str, Any]] = []
            for match in pattern.finditer(source):
                block = match.group(1)
                options = match.group(2) if match.lastindex and match.lastindex > 1 else None
                item = cls._extract_registered_item(block, optional_block=options)
                if item:
                    items.append(item)
            if items:
                registrations[key] = items

        return registrations or None

    @classmethod
    def _extract_object_signature(cls, source: str, function_name: str) -> dict[str, Any] | None:
        pattern = re.compile(rf"{re.escape(function_name)}\s*\(\s*\{{(.*?)\}}\s*\)", re.S)
        match = pattern.search(source)
        if not match:
            return None
        block = match.group(1)
        return cls._compact(
            {
                "id": cls._extract_string_property(block, "id"),
                "name": cls._extract_string_property(block, "name"),
                "description": cls._extract_string_property(block, "description"),
            }
        )

    @classmethod
    def _extract_registered_item(
        cls,
        block: str,
        *,
        optional_block: str | None = None,
    ) -> dict[str, Any] | None:
        name = cls._extract_string_property(block, "name") or cls._extract_string_property(block, "id")
        if not name:
            return None
        return cls._compact(
            {
                "name": name,
                "description": cls._extract_string_property(block, "description"),
                "optional": True if optional_block and re.search(r"\boptional\s*:\s*true\b", optional_block) else None,
            }
        )

    @staticmethod
    def _extract_string_property(block: str, field: str) -> str | None:
        pattern = re.compile(rf"\b{re.escape(field)}\s*:\s*([\"'])(.*?)\1", re.S)
        match = pattern.search(block)
        if not match:
            return None
        value = match.group(2).strip()
        return value or None

    @classmethod
    def _extract_hook_specs(cls, hooks_root: Path) -> list[dict[str, Any]]:
        if not hooks_root.is_dir():
            return []

        hook_specs: list[dict[str, Any]] = []
        for hook_md in sorted(hooks_root.glob("*/HOOK.md")):
            parsed = cls._parse_frontmatter(hook_md.read_text(encoding="utf-8"))
            openclaw_meta = cls._as_mapping(parsed.get("metadata")).get("openclaw")
            openclaw_payload = cls._as_mapping(openclaw_meta)
            hook_specs.append(
                cls._compact(
                    {
                        "name": parsed.get("name") or hook_md.parent.name,
                        "description": parsed.get("description"),
                        "events": cls._sorted_strings(openclaw_payload.get("events")),
                        "files": sorted(
                            item.name
                            for item in hook_md.parent.iterdir()
                            if item.is_file()
                        ),
                    }
                )
            )
        return hook_specs

    @classmethod
    def _parse_frontmatter(cls, text: str) -> dict[str, Any]:
        match = re.match(r"^---\s*\n(.*?)\n\s*---(?:\s*\n|$)", text, re.S)
        if match is None:
            return {}
        frontmatter = match.group(1)

        payload: dict[str, Any] = {}
        for line in frontmatter.splitlines():
            if ":" not in line:
                continue
            key, raw_value = line.split(":", 1)
            key = key.strip()
            value = raw_value.strip()
            if not key:
                continue
            if value.startswith("{") or value.startswith("["):
                try:
                    payload[key] = json.loads(value)
                    continue
                except json.JSONDecodeError:
                    pass
            payload[key] = cls._strip_quotes(value)
        return payload

    @staticmethod
    def _strip_quotes(value: str) -> str:
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    @classmethod
    def _extract_agent_defaults(cls, defaults: Mapping[str, Any]) -> dict[str, Any]:
        return cls._compact(
            {
                "workspace": defaults.get("workspace"),
                "model": defaults.get("model"),
                "heartbeat": cls._as_mapping(defaults.get("heartbeat")).get("every"),
            }
        )

    @classmethod
    def _extract_agent_entry(cls, name: str, entry: Mapping[str, Any]) -> dict[str, Any]:
        tools_block = cls._as_mapping(entry.get("tools"))
        plugins_block = cls._as_mapping(entry.get("plugins"))
        return cls._compact(
            {
                "name": name,
                "model": entry.get("model"),
                "workspace": entry.get("workspace"),
                "tool_allow": cls._sorted_strings(tools_block.get("allow")),
                "plugin_allow": cls._sorted_strings(plugins_block.get("allow")),
            }
        )

    @classmethod
    def _extract_tool_refs(cls, agent_spec: Mapping[str, Any]) -> list[dict[str, Any]]:
        tool_specs: dict[str, dict[str, Any]] = {}

        for plugin in cls._normalise_value(agent_spec.get("plugins", [])) or []:
            if not isinstance(plugin, Mapping):
                continue
            for extension in cls._normalise_value(plugin.get("extensions", [])) or []:
                if not isinstance(extension, Mapping):
                    continue
                registrations = cls._as_mapping(extension.get("registers"))
                for tool in cls._normalise_value(registrations.get("tools", [])) or []:
                    if not isinstance(tool, Mapping):
                        continue
                    name = tool.get("name")
                    if not isinstance(name, str) or not name:
                        continue
                    tool_specs[name] = cls._compact(
                        {
                            "name": name,
                            "description": tool.get("description"),
                        }
                    )

        tools_block = cls._as_mapping(agent_spec.get("tools"))
        for name in cls._sorted_strings(tools_block.get("allow")):
            tool_specs.setdefault(name, {"name": name})

        return [ToolRef.from_dict(tool).to_dict() for _, tool in sorted(tool_specs.items())]

    @classmethod
    def _infer_architecture(
        cls,
        agent_spec: Mapping[str, Any],
        tool_refs: list[dict[str, Any]],
    ) -> AgentArchitecture:
        agents = agent_spec.get("agents")
        if isinstance(agents, list) and len(agents) > 1:
            return AgentArchitecture.MULTI_AGENT
        if tool_refs:
            return AgentArchitecture.TOOL_USE
        return AgentArchitecture.CUSTOM

    @classmethod
    def _sorted_strings(cls, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return sorted(str(item) for item in value if isinstance(item, (str, int, float)))

    @classmethod
    def _normalise_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {
                str(key): cls._normalise_value(item)
                for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            }
        if isinstance(value, Path):
            return value.name
        if isinstance(value, tuple):
            return [cls._normalise_value(item) for item in value]
        if isinstance(value, list):
            return [cls._normalise_value(item) for item in value]
        if isinstance(value, set):
            normalised = [cls._normalise_value(item) for item in value]
            return sorted(normalised, key=repr)
        return repr(value)

    @classmethod
    def _compact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                cleaned = cls._compact(item)
                if cleaned not in (None, "", [], {}):
                    result[str(key)] = cleaned
            return result
        if isinstance(value, list):
            result = [cls._compact(item) for item in value]
            return [item for item in result if item not in (None, "", [], {})]
        return value

    @classmethod
    def _parse_json5_like(cls, text: str, *, source: Path | None = None) -> dict[str, Any]:
        cleaned = cls._strip_json_comments(text)
        cleaned = re.sub(r"([{\[,]\s*)([A-Za-z_][A-Za-z0-9_.-]*)(\s*:)", r'\1"\2"\3', cleaned)
        cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            path_label = source.as_posix() if source is not None else "<config>"
            raise ValueError(
                f"Could not parse OpenClaw config at {path_label}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("OpenClaw config must resolve to one top-level object.")
        return cls._normalise_value(payload)

    @staticmethod
    def _strip_json_comments(text: str) -> str:
        result: list[str] = []
        index = 0
        in_string = False
        quote_char = ""

        while index < len(text):
            char = text[index]
            next_char = text[index + 1] if index + 1 < len(text) else ""

            if in_string:
                result.append(char)
                if char == "\\":
                    if next_char:
                        result.append(next_char)
                        index += 2
                        continue
                elif char == quote_char:
                    in_string = False
                    quote_char = ""
                index += 1
                continue

            if char in {'"', "'"}:
                in_string = True
                quote_char = char
                result.append(char)
                index += 1
                continue

            if char == "/" and next_char == "/":
                index += 2
                while index < len(text) and text[index] != "\n":
                    index += 1
                continue

            if char == "/" and next_char == "*":
                index += 2
                while index + 1 < len(text) and not (text[index] == "*" and text[index + 1] == "/"):
                    index += 1
                index += 2
                continue

            result.append(char)
            index += 1

        return "".join(result)


OpenClawAdapter = OpenClawPassportAdapter
