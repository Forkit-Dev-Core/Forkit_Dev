"""Compatibility shim for legacy `forkit_core.schemas` imports."""

from forkit.schemas import (
    AgentArchitecture,
    AgentCapabilities,
    AgentPassport,
    AgentRole,
    AgentTaskType,
    Architecture,
    BasePassport,
    CreatorInfo,
    LicenseType,
    MemoryType,
    ModelCapabilities,
    ModelPassport,
    Modality,
    PassportStatus,
    SystemPromptRecord,
    TaskType,
    ToolRef,
    TrainingDataRef,
    _PYDANTIC_AVAILABLE,
)

__all__ = [
    "_PYDANTIC_AVAILABLE",
    # Base
    "BasePassport",
    "CreatorInfo",
    "LicenseType",
    "PassportStatus",
    # Model
    "ModelPassport",
    "ModelCapabilities",
    "TrainingDataRef",
    "Architecture",
    "Modality",
    "TaskType",
    # Agent
    "AgentPassport",
    "AgentCapabilities",
    "AgentRole",
    "AgentTaskType",
    "AgentArchitecture",
    "MemoryType",
    "SystemPromptRecord",
    "ToolRef",
]
