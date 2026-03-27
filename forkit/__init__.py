"""
forkit-core
───────────
Open-source AI model and agent identity infrastructure.

  forkit.domain    — pure Python: identity, hashing, lineage, integrity
  forkit.schemas   — ModelPassport, AgentPassport (dataclass; Pydantic v2 optional)
  forkit.registry  — local JSON + SQLite registry
  forkit.sdk       — Python SDK (ForkitClient)
  forkit.cli       — command-line interface

Quick start::

    from forkit.schemas import ModelPassport, AgentPassport, TaskType, Architecture
    from forkit.domain  import HashEngine

    passport = ModelPassport(
        name         = "llama-3-8b-base",
        version      = "1.0.0",
        task_type    = TaskType.TEXT_GENERATION,
        architecture = Architecture.DECODER_ONLY,
        creator      = {"name": "Meta", "organization": "Meta AI"},
    )
    print(passport.id)      # deterministic 64-char SHA-256 ID
    print(passport.short_id())  # first 12 chars
"""

__version__ = "0.1.0"

# ── Domain (always available — zero dependencies) ──────────────────────────────
from .domain import (
    HashEngine,
    hash_engine,
    LineageGraph,
    LineageNode,
    LineageEdge,
    NodeType,
    EdgeType,
    verify_passport_id,
    compute_metadata_hash,
)

# ── Schemas (dataclass by default; Pydantic v2 when installed) ────────────────
from .schemas import (
    ModelPassport,
    AgentPassport,
    BasePassport,
    CreatorInfo,
    PassportStatus,
    LicenseType,
    TaskType,
    Architecture,
    Modality,
    AgentTaskType,
    AgentArchitecture,
    AgentRole,
    MemoryType,
    ModelCapabilities,
    AgentCapabilities,
    TrainingDataRef,
    ToolRef,
    SystemPromptRecord,
    _PYDANTIC_AVAILABLE,
)

# ── Registry and SDK (graceful — no hard failure if registry deps missing) ────
try:
    from .registry import LocalRegistry
    from .sdk import ForkitClient
    from .sync import RemoteSyncBridge
except Exception:
    LocalRegistry = None   # type: ignore[assignment,misc]
    ForkitClient  = None   # type: ignore[assignment,misc]
    RemoteSyncBridge = None  # type: ignore[assignment,misc]

# ── Local service (optional FastAPI dependency) ───────────────────────────────
try:
    from .server import ServerSettings, create_app
except Exception:
    ServerSettings = None  # type: ignore[assignment,misc]
    create_app = None      # type: ignore[assignment,misc]

__all__ = [
    "__version__",
    # Domain
    "HashEngine", "hash_engine",
    "LineageGraph", "LineageNode", "LineageEdge", "NodeType", "EdgeType",
    "verify_passport_id", "compute_metadata_hash",
    # Schemas
    "ModelPassport", "AgentPassport", "BasePassport",
    "CreatorInfo", "PassportStatus", "LicenseType",
    "TaskType", "Architecture", "Modality",
    "AgentTaskType", "AgentArchitecture", "AgentRole", "MemoryType",
    "ModelCapabilities", "AgentCapabilities",
    "TrainingDataRef", "ToolRef", "SystemPromptRecord",
    "_PYDANTIC_AVAILABLE",
    # Registry / SDK
    "LocalRegistry", "ForkitClient",
    "RemoteSyncBridge",
    # Local service
    "ServerSettings", "create_app",
]
