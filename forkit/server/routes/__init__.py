"""Route modules for the local forkit service."""

from .passports import router as passports_router
from .system import router as system_router

__all__ = ["system_router", "passports_router"]
