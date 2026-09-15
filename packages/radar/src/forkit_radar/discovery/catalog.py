"""Small, versioned recognition catalog; product matches are only candidates.

Product names / exact executable signatures adapted from public AI Footprints,
commit ec7250cf39a185a5817835c50853862e68053318 (MIT). See THIRD_PARTY_NOTICES.
No command parsing, inference, product-name identity hashing or probes are ported.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    bundle: str
    bundle_id: str
    executable: str


APPLICATIONS = (
    Product("chatgpt", "ChatGPT", "ChatGPT.app", "com.openai.chat", "ChatGPT"),
    Product(
        "claude-desktop", "Claude Desktop", "Claude.app", "com.anthropic.claudefordesktop", "Claude"
    ),
    Product("codex", "Codex", "Codex.app", "com.openai.codex", "Codex"),
    Product("cursor", "Cursor", "Cursor.app", "com.todesktop.230313mzl4w4u92", "Cursor"),
    Product("windsurf", "Windsurf", "Windsurf.app", "com.exafunction.windsurf", "Windsurf"),
    Product("ollama", "Ollama", "Ollama.app", "com.electron.ollama", "Ollama"),
)

# Native executable basenames only, case-sensitive. Interpreters, ambiguous
# names (goose/jan/gemini), helpers and generic framework names deliberately abstain.
NATIVE_EXECUTABLES = {
    "codex": ("codex-cli", "Codex CLI"),
    "claude": ("claude-code", "Claude Code"),
    "opencode": ("opencode", "OpenCode"),
    "ollama": ("ollama-runtime", "Ollama Runtime"),
}
PRODUCT_NAMES = {p.key: p.name for p in APPLICATIONS} | dict(NATIVE_EXECUTABLES.values())
PRODUCT_NAMES["chatgpt-or-codex"] = "ChatGPT/Codex desktop (ambiguous)"


def match_bundle(bundle: str, bundle_id: object, executable: object) -> str | None:
    for product in APPLICATIONS:
        if (bundle, bundle_id, executable) == (
            product.bundle,
            product.bundle_id,
            product.executable,
        ):
            return product.key
    # Observed in the real macOS 26.6.2 validation. One bundle location can
    # represent a different product variant; the filename alone cannot decide.
    if (bundle, bundle_id, executable) == ("ChatGPT.app", "com.openai.codex", "ChatGPT"):
        return "codex"
    return None


def match_executable(executable: str) -> tuple[str, str] | None:
    # Full paths are ephemeral classifier inputs, never returned or hashed.
    if not isinstance(executable, str) or not executable.startswith("/"):
        return None
    if len(executable) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in executable):
        return None
    parts = executable.split("/")
    if any(part in {".", ".."} for part in parts):
        return None
    # Inside a bundle, require the exact main executable and bundle name.
    # Never mistake bundled CLI resources or Electron support processes for agents.
    if any(part.endswith(".app") for part in parts):
        for product in APPLICATIONS:
            if parts[-4:] == [product.bundle, "Contents", "MacOS", product.executable]:
                if product.key == "chatgpt":
                    return "chatgpt-or-codex", PRODUCT_NAMES["chatgpt-or-codex"]
                return product.key, product.name
        return None
    return NATIVE_EXECUTABLES.get(parts[-1])
