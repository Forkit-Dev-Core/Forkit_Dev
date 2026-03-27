"""
forkit.cli.main
───────────────
Command-line interface for forkit-core.

Commands
────────
  forkit register model <yaml-file>
  forkit register agent <yaml-file>
  forkit sync push <endpoint>
  forkit serve
  forkit inspect <id>
  forkit list [--type model|agent] [--status active|draft|deprecated|revoked]
  forkit search <query>
  forkit lineage <id>
  forkit verify <id>
  forkit stats

Requires: typer (pip install typer)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

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

app     = typer.Typer(name="forkit", help="forkit-core — AI model/agent identity CLI")
reg_app = typer.Typer(help="Register a passport from a YAML file")
sync_app = typer.Typer(help="Push local outbox changes to a remote endpoint")
app.add_typer(reg_app, name="register")
app.add_typer(sync_app, name="sync")

_REGISTRY_ROOT = Path.home() / ".forkit" / "registry"


def _registry() -> LocalRegistry:
    return LocalRegistry(root=_REGISTRY_ROOT)


# ── register ──────────────────────────────────────────────────────────────────

@reg_app.command("model")
def register_model(yaml_file: Path = typer.Argument(..., help="YAML file with ModelPassport fields")):
    """Register a model passport from a YAML file."""
    data = yaml.safe_load(yaml_file.read_text())
    passport = ModelPassport.from_dict(data)
    pid = _registry().register_model(passport)
    typer.echo(f"Registered model: {pid}")


@reg_app.command("agent")
def register_agent(yaml_file: Path = typer.Argument(..., help="YAML file with AgentPassport fields")):
    """Register an agent passport from a YAML file."""
    data = yaml.safe_load(yaml_file.read_text())
    passport = AgentPassport.from_dict(data)
    pid = _registry().register_agent(passport)
    typer.echo(f"Registered agent: {pid}")


# ── inspect ───────────────────────────────────────────────────────────────────

@app.command()
def inspect(passport_id: str = typer.Argument(..., help="Full or partial passport ID")):
    """Print a passport as formatted JSON."""
    reg = _registry()
    p = reg.get(passport_id)
    if p is None:
        typer.echo(f"Not found: {passport_id}", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(p.to_dict(), indent=2, default=str))


# ── list ──────────────────────────────────────────────────────────────────────

@app.command("list")
def list_passports(
    type:   Optional[str] = typer.Option(None, "--type",   "-t", help="model | agent"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="active | draft | deprecated | revoked"),
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
def search(query: str = typer.Argument(..., help="Search term (name / creator)")):
    """Search passports by name or creator."""
    rows = _registry().search(query)
    if not rows:
        typer.echo("No results.")
        return
    for r in rows:
        typer.echo(f"[{r['passport_type']:5}] {r['id'][:16]}... {r['name']} v{r['version']}")


# ── lineage ───────────────────────────────────────────────────────────────────

@app.command()
def lineage(passport_id: str = typer.Argument(..., help="Passport ID")):
    """Show ancestors and descendants for a passport."""
    reg  = _registry()
    anc  = reg.lineage.ancestors(passport_id)
    desc = reg.lineage.descendants(passport_id)
    typer.echo(f"\nAncestors of {passport_id[:16]}...:")
    for n in anc:
        typer.echo(f"  [{n.node_type}] {n.name} v{n.version}  {n.id[:16]}...")
    typer.echo(f"\nDescendants:")
    for n in desc:
        typer.echo(f"  [{n.node_type}] {n.name} v{n.version}  {n.id[:16]}...")


# ── verify ────────────────────────────────────────────────────────────────────

@app.command()
def verify(passport_id: str = typer.Argument(..., help="Passport ID to verify")):
    """Re-derive a passport ID and check it matches the stored value."""
    result = _registry().verify_passport(passport_id)
    typer.echo(json.dumps(result, indent=2))
    if not result.get("valid"):
        raise typer.Exit(1)


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
    endpoint: str = typer.Argument(..., help="Remote POST endpoint for sync batches"),
    target: Optional[str] = typer.Option(None, "--target", help="Stable local name for this sync target"),
    after: Optional[int] = typer.Option(None, "--after", help="Override the saved cursor and start after this value"),
    limit: int = typer.Option(100, "--limit", min=1, max=1000, help="Maximum number of changes per batch"),
    passport_type: Optional[str] = typer.Option(None, "--type", "-t", help="model | agent"),
    timeout: float = typer.Option(30.0, "--timeout", min=1.0, help="HTTP timeout in seconds"),
    token: Optional[str] = typer.Option(None, "--token", envvar="FORKIT_SYNC_TOKEN", help="Optional bearer token"),
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


# ── serve ─────────────────────────────────────────────────────────────────────

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host"),
    port: int = typer.Option(8000, "--port", help="Bind port"),
    registry_root: Path = typer.Option(_REGISTRY_ROOT, "--registry-root", help="Registry root path"),
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
        raise typer.Exit(1)

    try:
        from ..server import ServerSettings, create_app
    except ImportError:
        typer.echo(
            "Server support is not available in this environment.\n"
            "Install with:\n"
            "  pip install 'forkit-core[server]'",
            err=True,
        )
        raise typer.Exit(1)

    settings = ServerSettings(
        registry_root=registry_root.expanduser().resolve(),
        host=host,
        port=port,
    )
    typer.echo(
        f"Serving forkit local service on http://{settings.host}:{settings.port}\n"
        f"Registry root: {settings.registry_root}"
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
