"""
forkit.cli.main
───────────────
Command-line interface for forkit-core.

Commands
────────
  forkit register model <yaml-file>
  forkit register agent <yaml-file>
  forkit hosted-proof <id>
  forkit sync push <endpoint>
  forkit sync pull <endpoint>
  forkit serve
  forkit inspect <id>
  forkit list [--type model|agent] [--status active|draft|deprecated|revoked]
  forkit search <query>
  forkit lineage <id>
  forkit verify <id>
  forkit stats

Requires: typer (pip install typer)

The sync commands are generic self-host or custom-endpoint primitives. They do
not implement a hosted Forkit publish or claim workflow.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import typer
    import yaml
except ImportError:
    print(
        "CLI requires 'typer' and 'pyyaml'.  Install with:\n"
        "  pip install typer pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

from ..registry.local import LocalRegistry
from ..schemas import AgentPassport, ModelPassport
from ..sync import RemoteSyncBridge

app     = typer.Typer(name="forkit", help="forkit-core — AI model and agent passport CLI")
reg_app = typer.Typer(help="Register a passport from a YAML file")
sync_app = typer.Typer(help="Push and pull generic sync batches")
app.add_typer(reg_app, name="register")
app.add_typer(sync_app, name="sync")

_REGISTRY_ROOT = Path.home() / ".forkit" / "registry"
_MODEL_YAML_ARGUMENT = typer.Argument(..., help="YAML file with ModelPassport fields")
_AGENT_YAML_ARGUMENT = typer.Argument(..., help="YAML file with AgentPassport fields")
_INSPECT_ID_ARGUMENT = typer.Argument(..., help="Full or partial passport ID")
_SEARCH_QUERY_ARGUMENT = typer.Argument(..., help="Search term (name / creator)")
_LINEAGE_ID_ARGUMENT = typer.Argument(..., help="Passport ID")
_VERIFY_ID_ARGUMENT = typer.Argument(..., help="Passport ID to verify")
_HOSTED_PROOF_ID_ARGUMENT = typer.Argument(..., help="Passport ID to prepare for hosted Forkit import")
_SYNC_PUSH_ENDPOINT_ARGUMENT = typer.Argument(..., help="Remote POST endpoint for sync batches")
_SYNC_PULL_ENDPOINT_ARGUMENT = typer.Argument(
    ...,
    help="Remote GET endpoint that serves exported change batches",
)
_LIST_TYPE_OPTION = typer.Option(None, "--type", "-t", help="model | agent")
_LIST_STATUS_OPTION = typer.Option(
    None,
    "--status",
    "-s",
    help="active | draft | deprecated | revoked",
)
_SYNC_TARGET_OPTION = typer.Option(None, "--target", help="Stable local name for this sync target")
_SYNC_SOURCE_OPTION = typer.Option(None, "--source", help="Stable local name for this remote source")
_SYNC_AFTER_OPTION = typer.Option(
    None,
    "--after",
    help="Override the saved cursor and start after this value",
)
_SYNC_LIMIT_OPTION = typer.Option(
    100,
    "--limit",
    min=1,
    max=1000,
    help="Maximum number of changes per batch",
)
_SYNC_TYPE_OPTION = typer.Option(None, "--type", "-t", help="model | agent")
_SYNC_TIMEOUT_OPTION = typer.Option(30.0, "--timeout", min=1.0, help="HTTP timeout in seconds")
_SYNC_TOKEN_OPTION = typer.Option(
    None,
    "--token",
    envvar="FORKIT_SYNC_TOKEN",
    help="Optional bearer token",
)
_SERVE_HOST_OPTION = typer.Option("127.0.0.1", "--host", help="Bind host")
_SERVE_PORT_OPTION = typer.Option(8000, "--port", help="Bind port")
_SERVE_REGISTRY_ROOT_OPTION = typer.Option(
    _REGISTRY_ROOT,
    "--registry-root",
    help="Registry root path",
)


def _registry() -> LocalRegistry:
    return LocalRegistry(root=_REGISTRY_ROOT)


def _normalize_host(value: str | None) -> str:
    return str(value or "").strip().lower().removeprefix("www.")


def _build_hosted_proof_url(source_url: str | None) -> str | None:
    if not source_url:
        return None

    try:
        parsed = urlparse(source_url)
    except Exception:
        return None

    host = _normalize_host(parsed.hostname)
    path_parts = [part for part in parsed.path.removesuffix(".git").split("/") if part]
    if len(path_parts) < 2:
        return None

    if host == "github.com":
        owner, repo = path_parts[0], path_parts[1]
        return f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/.well-known/forkit-verify.txt"

    if host == "huggingface.co":
        owner, repo = path_parts[0], path_parts[1]
        return f"https://huggingface.co/{owner}/{repo}/resolve/main/.well-known/forkit-verify.txt"

    if host == "gitlab.com":
        owner, repo = path_parts[0], path_parts[1]
        return f"https://gitlab.com/{owner}/{repo}/-/raw/main/.well-known/forkit-verify.txt"

    return None


# ── register ──────────────────────────────────────────────────────────────────

@reg_app.command("model")
def register_model(yaml_file: Path = _MODEL_YAML_ARGUMENT):
    """Register a model passport from a YAML file."""
    data = yaml.safe_load(yaml_file.read_text())
    passport = ModelPassport.from_dict(data)
    pid = _registry().register_model(passport)
    typer.echo(f"Registered model: {pid}")


@reg_app.command("agent")
def register_agent(yaml_file: Path = _AGENT_YAML_ARGUMENT):
    """Register an agent passport from a YAML file."""
    data = yaml.safe_load(yaml_file.read_text())
    passport = AgentPassport.from_dict(data)
    pid = _registry().register_agent(passport)
    typer.echo(f"Registered agent: {pid}")


# ── inspect ───────────────────────────────────────────────────────────────────

@app.command()
def inspect(passport_id: str = _INSPECT_ID_ARGUMENT):
    """Print a passport as formatted JSON."""
    reg = _registry()
    try:
        resolved_id = reg.resolve_id(passport_id)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1) from None

    if resolved_id is None:
        typer.echo(f"Not found: {passport_id}", err=True)
        raise typer.Exit(1)
    p = reg.get(resolved_id)
    if p is None:
        typer.echo(f"Not found: {passport_id}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(p.to_dict(), indent=2, default=str))


# ── list ──────────────────────────────────────────────────────────────────────

@app.command("list")
def list_passports(
    type: str | None = _LIST_TYPE_OPTION,
    status: str | None = _LIST_STATUS_OPTION,
):
    """List passports in the registry."""
    rows = _registry().list(passport_type=type, status=status)
    if not rows:
        typer.echo("No passports found.")
        return
    for r in rows:
        typer.echo(f"[{r['passport_type']:5}] {r['id'][:16]}... {r['name']} v{r['version']}  ({r['status']})")


# ── search ────────────────────────────────────────────────────────────────────

@app.command()
def search(query: str = _SEARCH_QUERY_ARGUMENT):
    """Search passports by name or creator."""
    rows = _registry().search(query)
    if not rows:
        typer.echo("No results.")
        return
    for r in rows:
        typer.echo(f"[{r['passport_type']:5}] {r['id'][:16]}... {r['name']} v{r['version']}")


# ── lineage ───────────────────────────────────────────────────────────────────

@app.command()
def lineage(passport_id: str = _LINEAGE_ID_ARGUMENT):
    """Show ancestors and descendants for a passport."""
    reg  = _registry()
    anc  = reg.lineage.ancestors(passport_id)
    desc = reg.lineage.descendants(passport_id)
    typer.echo(f"\nAncestors of {passport_id[:16]}...:")
    for n in anc:
        typer.echo(f"  [{n.node_type}] {n.name} v{n.version}  {n.id[:16]}...")
    typer.echo("\nDescendants:")
    for n in desc:
        typer.echo(f"  [{n.node_type}] {n.name} v{n.version}  {n.id[:16]}...")


# ── verify ────────────────────────────────────────────────────────────────────

@app.command()
def verify(passport_id: str = _VERIFY_ID_ARGUMENT):
    """Re-derive a passport ID and check it matches the stored value."""
    result = _registry().verify_passport(passport_id)
    typer.echo(json.dumps(result, indent=2))
    if not result.get("valid"):
        raise typer.Exit(1)


@app.command("hosted-proof")
def hosted_proof(passport_id: str = _HOSTED_PROOF_ID_ARGUMENT):
    """Print the proof file details required before importing this passport into hosted Forkit."""
    reg = _registry()
    passport = reg.get(passport_id)
    if passport is None:
        typer.echo(f"Not found: {passport_id}", err=True)
        raise typer.Exit(1)

    payload = passport.to_dict()
    canonical_passport_id = str(payload.get("id") or "").strip().lower()
    source_url = str(payload.get("source_url") or payload.get("sourceUrl") or "").strip() or None
    verify_url = _build_hosted_proof_url(source_url)

    if not source_url:
        typer.echo(
            json.dumps(
                {
                    "passport_id": canonical_passport_id,
                    "ready": False,
                    "reason": "This passport does not declare a source URL. Hosted import proof requires a GitHub, Hugging Face, or GitLab source URL.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    if not verify_url:
        typer.echo(
            json.dumps(
                {
                    "passport_id": canonical_passport_id,
                    "source_url": source_url,
                    "ready": False,
                    "reason": "Hosted import proof currently supports GitHub, Hugging Face, and GitLab source URLs only.",
                },
                indent=2,
            )
        )
        raise typer.Exit(1)

    typer.echo(
        json.dumps(
            {
                "passport_id": canonical_passport_id,
                "source_url": source_url,
                "verify_url": verify_url,
                "file_path": "/.well-known/forkit-verify.txt",
                "proof_line": f"forkit-passport-id={canonical_passport_id}",
                "ready": True,
            },
            indent=2,
        )
    )


# ── stats ─────────────────────────────────────────────────────────────────────

@app.command()
def stats():
    """Print registry statistics."""
    s = _registry().stats()
    typer.echo(json.dumps(s, indent=2))


# ── sync ──────────────────────────────────────────────────────────────────────

@sync_app.command("status")
def sync_status():
    """Print saved sync cursors keyed by target."""
    typer.echo(json.dumps(_registry().get_sync_state(), indent=2))


@sync_app.command("push")
def sync_push(
    endpoint: str = _SYNC_PUSH_ENDPOINT_ARGUMENT,
    target: str | None = _SYNC_TARGET_OPTION,
    after: int | None = _SYNC_AFTER_OPTION,
    limit: int = _SYNC_LIMIT_OPTION,
    passport_type: str | None = _SYNC_TYPE_OPTION,
    timeout: float = _SYNC_TIMEOUT_OPTION,
    token: str | None = _SYNC_TOKEN_OPTION,
):
    """Push local outbox changes to a remote endpoint and persist the acknowledged cursor."""
    bridge = RemoteSyncBridge(_registry())
    result = bridge.push(
        endpoint,
        target=target,
        after=after,
        limit=limit,
        passport_type=passport_type,
        timeout=timeout,
        token=token,
    )
    typer.echo(json.dumps(result, indent=2))


@sync_app.command("pull")
def sync_pull(
    endpoint: str = _SYNC_PULL_ENDPOINT_ARGUMENT,
    source: str | None = _SYNC_SOURCE_OPTION,
    after: int | None = _SYNC_AFTER_OPTION,
    limit: int = _SYNC_LIMIT_OPTION,
    passport_type: str | None = _SYNC_TYPE_OPTION,
    timeout: float = _SYNC_TIMEOUT_OPTION,
    token: str | None = _SYNC_TOKEN_OPTION,
):
    """Pull remote export batches into the local registry without re-appending them to the outbox."""
    bridge = RemoteSyncBridge(_registry())
    result = bridge.pull(
        endpoint,
        source=source,
        after=after,
        limit=limit,
        passport_type=passport_type,
        timeout=timeout,
        token=token,
    )
    typer.echo(json.dumps(result, indent=2))


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    host: str = _SERVE_HOST_OPTION,
    port: int = _SERVE_PORT_OPTION,
    registry_root: Path = _SERVE_REGISTRY_ROOT_OPTION,
):
    """Run the local HTTP service over the registry."""
    try:
        import uvicorn
    except ImportError:
        typer.echo(
            "Server support requires FastAPI and Uvicorn.\n"
            "Install with:\n"
            "  pip install 'forkit-core[server]'",
            err=True,
        )
        raise typer.Exit(1) from None

    try:
        from ..server import ServerSettings, create_app
    except ImportError:
        typer.echo(
            "Server support is not available in this environment.\n"
            "Install with:\n"
            "  pip install 'forkit-core[server]'",
            err=True,
        )
        raise typer.Exit(1) from None

    settings = ServerSettings(
        registry_root=registry_root.expanduser().resolve(),
        host=host,
        port=port,
    )
    warning_lines: list[str] = []
    if settings.host not in {"127.0.0.1", "localhost"}:
        warning_lines.append(
            "Warning: non-loopback host configured. Keep this service behind a trusted network boundary."
        )
    if settings.sync_bearer_token is None:
        warning_lines.append(
            "Warning: FORKIT_SYNC_BEARER_TOKEN is not set. If you expose /sync/passports outside localhost, add a bearer token first."
        )

    typer.echo(
        "\n".join(
            [
                f"Serving forkit local service on http://{settings.host}:{settings.port}",
                "Service metadata avoids exposing local filesystem paths by default.",
                *warning_lines,
            ]
        )
    )
    uvicorn.run(
        create_app(settings=settings),
        host=settings.host,
        port=settings.port,
    )


# ── entrypoint ────────────────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
