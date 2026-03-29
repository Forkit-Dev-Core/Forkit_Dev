"""
GitHub CI validation quickstart smoke example.

Run: python examples/github_ci_quickstart.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forkit-ci-") as tmpdir:
        passport_path = Path(tmpdir) / "forkit-passport.json"

        generate = _run(
            [
                sys.executable,
                "scripts/generate_passport_template.py",
                "--passport-type",
                "model",
                "--name",
                "ci-demo-model",
                "--version",
                "1.0.0",
                "--creator-name",
                "Forkit Demo",
                "--creator-organization",
                "Forkit OSS",
                "--output",
                str(passport_path),
            ]
        )
        validate = _run(
            [
                sys.executable,
                "scripts/validate_passport.py",
                "--path",
                str(passport_path),
            ]
        )
        summary_lines = [line for line in validate.stdout.splitlines() if line.startswith("Forkit passport")]

        print(
            json.dumps(
                {
                    "generated": "Forkit passport template generated" in generate.stdout,
                    "validated": "Forkit passport is valid" in validate.stdout,
                    "passport_path": passport_path.name,
                    "validator_summary": summary_lines[0] if summary_lines else "",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
