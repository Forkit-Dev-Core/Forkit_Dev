"""Compatibility shim for the local forkit service namespace."""

from forkit.server import ServerSettings, create_app

__all__ = ["create_app", "ServerSettings"]
