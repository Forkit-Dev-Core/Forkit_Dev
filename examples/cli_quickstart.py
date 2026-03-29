"""
CLI quickstart smoke example.

Run: python examples/cli_quickstart.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import yaml
    from typer.testing import CliRunner
except ImportError:
    print(
        "CLI quickstart requires the optional CLI dependencies.\n"
        "Install with:\n"
        "  pip install -e '.[cli]'",
        file=sys.stderr,
    )
    raise SystemExit(1)

from forkit.cli.main import app


def main() -> None:
    runner = CliRunner()

    with tempfile.TemporaryDirectory(prefix="forkit-cli-") as tmpdir:
        workspace = Path(tmpdir)
        registry_root = workspace / "registry"
        model_yaml = workspace / "register_model.yaml"
        model_yaml.write_text(
            yaml.safe_dump(
                {
                    "name": "cli-demo-model",
                    "version": "1.0.0",
                    "creator": {"name": "Forkit Demo", "organization": "Forkit OSS"},
                    "description": "CLI registration example.",
                    "license": "Apache-2.0",
                    "status": "active",
                    "task_type": "text-generation",
                    "architecture": "transformer",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        register_result = runner.invoke(
            app,
            ["register", "model", str(model_yaml), "--registry-root", str(registry_root)],
        )
        if register_result.exit_code != 0:
            raise SystemExit(register_result.exit_code)

        model_id = register_result.stdout.strip().split(": ", maxsplit=1)[1]
        list_result = runner.invoke(
            app,
            ["list", "--registry-root", str(registry_root)],
        )
        verify_result = runner.invoke(
            app,
            ["verify", model_id, "--registry-root", str(registry_root)],
        )
        stats_result = runner.invoke(
            app,
            ["stats", "--registry-root", str(registry_root)],
        )

        if list_result.exit_code != 0:
            raise SystemExit(list_result.exit_code)
        if verify_result.exit_code != 0:
            raise SystemExit(verify_result.exit_code)
        if stats_result.exit_code != 0:
            raise SystemExit(stats_result.exit_code)

        verification = json.loads(verify_result.stdout)
        stats = json.loads(stats_result.stdout)

        print(
            json.dumps(
                {
                    "registered_model_id": model_id,
                    "list_contains_model": "cli-demo-model" in list_result.stdout,
                    "verify_valid": verification["valid"],
                    "stats": {"models": stats["models"], "agents": stats["agents"]},
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
