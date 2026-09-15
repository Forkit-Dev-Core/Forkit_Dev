"""Run cumulative Radar checks with installed wheels and a fresh offline environment.

Provision the development lock and runtime wheelhouse separately. This script
does not resolve or download dependencies. Results, logs and built-wheel hashes
are retained even on failure. Run only in a disposable development environment:
the two locally built project wheels replace its installed Core/Radar versions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import time
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "output/radar-foundation")
    args = parser.parse_args()
    wheelhouse = args.wheelhouse.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not wheelhouse.is_dir():
        parser.error("Provision a runtime wheelhouse first; see packages/radar/README.md")
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    artifacts = run_dir / "dist"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SOURCE_DATE_EPOCH"] = "1704067200"
    report = {
        "schema_version": "1.0",
        "step": "session-final",
        "status": "running",
        "platform": platform.platform(),
        "python": sys.version,
        "output": str(run_dir),
        "checks": [],
        "wheel_sha256": {},
        "limitations": [
            "Local checks only; CI matrix execution must be recorded separately",
            "Passive discovery and structural tests do not establish enrolled or authenticated identity",
        ],
    }
    report_path = run_dir / "results.json"

    def run(name, command, cwd=ROOT):
        start = time.monotonic()
        log = run_dir / f"{name}.log"
        with log.open("w") as handle:
            result = subprocess.run(
                command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT
            )
        report["checks"].append(
            {
                "name": name,
                "command": [str(v) for v in command],
                "cwd": str(cwd),
                "exit": result.returncode,
                "seconds": round(time.monotonic() - start, 3),
                "log": log.name,
            }
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: {'PASS' if result.returncode == 0 else 'FAIL'}", flush=True)
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect {log}")

    python = sys.executable
    try:
        run("lint", [python, "-m", "ruff", "check", "."])
        run(
            "build-core",
            [python, "-m", "build", "--no-isolation", "--outdir", str(artifacts), str(ROOT)],
        )
        run(
            "build-radar",
            [
                python,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(artifacts),
                str(ROOT / "packages/radar"),
            ],
        )
        # Local work records contain machine paths and are not package content.
        for archive_path in artifacts.glob("*.tar.gz"):
            with tarfile.open(archive_path) as archive:
                if any(
                    "/docs/radar-audit/" in name
                    or name.endswith(("/FORKIT_RADAR_LOCK.md", "/AGENTS.md"))
                    for name in archive.getnames()
                ):
                    raise RuntimeError("Local audit/instruction records leaked into source archive")
        report["source_archive_boundary"] = "passed"
        wheels = sorted(artifacts.glob("*.whl"))
        expected = {"forkit_core-0.1.0-py3-none-any.whl", "forkit_radar-0.1.0b6-py3-none-any.whl"}
        if {p.name for p in wheels} != expected:
            raise RuntimeError("Unexpected project wheel identity; review package versions")
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as archive:
                names = archive.namelist()
                forbidden = "forkit/" if wheel.name.startswith("forkit_radar") else "forkit_radar/"
                if any(name.startswith(forbidden) for name in names):
                    raise RuntimeError("Project wheel namespace overlap")
            report["wheel_sha256"][wheel.name] = sha256(wheel)
        wheel_requirements = run_dir / "project-wheels.lock"
        wheel_requirements.write_text(
            "forkit-core==0.1.0 --hash=sha256:"
            + report["wheel_sha256"]["forkit_core-0.1.0-py3-none-any.whl"]
            + "\nforkit-radar==0.1.0b6 --hash=sha256:"
            + report["wheel_sha256"]["forkit_radar-0.1.0b6-py3-none-any.whl"]
            + "\n"
        )
        install_projects = [
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--require-hashes",
            "--force-reinstall",
            "--find-links",
            str(artifacts),
            "-r",
            str(wheel_requirements),
        ]
        run("install-project-wheels", [python, *install_projects])
        run("dependency-consistency", [python, "-m", "pip", "check"])
        run("schema-drift", [python, "scripts/generate_radar_schemas.py", "--check"])
        run("beta-page-drift", [python, "scripts/build_radar_beta_pages.py", "--check"])
        run("card-example-drift", [python, "scripts/generate_radar_card_example.py", "--check"])
        run("installer-tests", [python, "-m", "pytest", "-q", "-o", "addopts=", "--junitxml", str(run_dir / "installer-tests.xml"), "scripts/tests"])
        run(
            "core-tests",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "-o",
                "addopts=",
                "--junitxml",
                str(run_dir / "core-tests.xml"),
                "tests",
            ],
        )
        run(
            "radar-tests",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "-c",
                "packages/radar/pyproject.toml",
                "--junitxml",
                str(run_dir / "radar-tests.xml"),
                "packages/radar/tests",
            ],
        )
        rebuild = run_dir / "rebuild"
        run(
            "rebuild-radar",
            [
                python,
                "-m",
                "build",
                "--no-isolation",
                "--wheel",
                "--outdir",
                str(rebuild),
                str(ROOT / "packages/radar"),
            ],
        )
        rebuilt = rebuild / "forkit_radar-0.1.0b6-py3-none-any.whl"
        if sha256(rebuilt) != report["wheel_sha256"][rebuilt.name]:
            raise RuntimeError("Radar wheel rebuild differs under fixed SOURCE_DATE_EPOCH")
        report["reproducible_radar_wheel"] = True
        fresh = run_dir / "fresh-venv"
        venv.EnvBuilder(with_pip=True).create(fresh)
        fresh_python = fresh / "bin/python"
        outside = run_dir / "outside-source"
        outside.mkdir()
        run(
            "offline-runtime-install",
            [
                str(fresh_python),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--only-binary=:all:",
                "--require-hashes",
                "--find-links",
                str(wheelhouse),
                "-r",
                str(ROOT / "requirements/radar-runtime.lock"),
            ],
            outside,
        )
        run("offline-project-install", [str(fresh_python), *install_projects], outside)
        run("offline-dependency-check", [str(fresh_python), "-m", "pip", "check"], outside)
        run(
            "installed-package-smoke",
            [
                str(fresh_python),
                "-I",
                "-c",
                "\n".join(
                    [
                        "import importlib.util, json, sys",
                        "from pathlib import Path",
                        "import forkit, forkit_radar",
                        "from forkit_radar.contracts import read_contract",
                        "from importlib.resources import files",
                        "assert Path(forkit.__file__).is_relative_to(Path(sys.prefix))",
                        "assert Path(forkit_radar.__file__).is_relative_to(Path(sys.prefix))",
                        "assert importlib.util.find_spec('pytest') is None",
                        "assert importlib.util.find_spec('langchain') is None",
                        "assert json.loads(files('forkit_radar').joinpath('schemas/manifest-v1.json').read_text())['additionalProperties'] is False",
                        "print('Installed Core/Radar imports and distributed schema passed outside source tree')",
                    ]
                ),
            ],
            outside,
        )
        run("installed-cli-version", [str(fresh / "bin/forkit-radar"), "--version"], outside)
        run(
            "installed-cli-validation",
            [
                str(fresh / "bin/forkit-radar"),
                "validate",
                "manifest",
                str(ROOT / "packages/radar/tests/fixtures/manifest.json"),
            ],
            outside,
        )
        run(
            "installed-passive-discovery",
            [
                str(fresh_python),
                str(ROOT / "scripts/check_radar_discovery.py"),
                "--output",
                str(run_dir / "live-discovery.json"),
                "--require-process-access",
            ],
            outside,
        )
        run(
            "installed-core-enrollment",
            [
                str(fresh_python),
                str(ROOT / "scripts/check_radar_identity.py"),
                "--output",
                str(run_dir / "installed-identity.json"),
                "--fixture",
                str(ROOT / "packages/radar/tests/fixtures/manifest.json"),
            ],
            outside,
        )
        run(
            "installed-session-receipt",
            [str(fresh_python), str(ROOT / "scripts/check_radar_sessions.py"), "--output", str(run_dir / "installed-session.json")],
            outside,
        )
        run(
            "installed-session-details",
            [str(fresh_python), str(ROOT / "scripts/check_radar_session_details.py"), "--output", str(run_dir / "installed-session-details.json"), "--fixtures", str(ROOT / "packages/radar/tests/fixtures/session")],
            outside,
        )
        run("installed-session-sharing", [str(fresh_python), str(ROOT / "scripts/check_radar_sharing.py"), "--output", str(run_dir / "installed-sharing")], outside)
        run("installed-release-maintenance", [str(fresh_python), str(ROOT / "scripts/check_radar_release.py"), "--output", str(run_dir / "installed-release.json")], outside)
        run("installed-session-evolution", [str(fresh_python), str(ROOT / "scripts/check_radar_evolution.py"), "--output", str(run_dir / "installed-evolution")], outside)
        run("installed-aggregate-reporting", [str(fresh_python), str(ROOT / "scripts/check_radar_reporting.py"), "--output", str(run_dir / "installed-reporting")], outside)
        run("installed-beta-onboarding", [str(fresh_python), str(ROOT / "scripts/check_radar_onboarding.py"), "--output", str(run_dir / "installed-onboarding"), "--guide", str(ROOT / "packages/radar/beta-kit/START_HERE.html")], outside)
        bundle = run_dir / "forkit-session-receipt.zip"
        run("build-offline-bundle", [python, str(ROOT / "scripts/build_radar_bundle.py"), "--project-wheels", str(artifacts), "--wheelhouse", str(wheelhouse), "--output", str(bundle)])
        report["bundle_sha256"] = sha256(bundle)
        with zipfile.ZipFile(bundle) as archive:
            archive.extractall(run_dir / "bundle")
        installer = run_dir / "bundle/forkit-session-receipt/install.py"
        application = run_dir / "bundle-app"
        shell_env_python = str(Path(python).parent)
        original_path = os.environ.get("PATH", "")
        env["PATH"] = shell_env_python + os.pathsep + original_path
        run("offline-bundle-preflight", ["/bin/sh", str(installer.with_name("install.sh")), "--check", "--prefix", str(application), "--bin-dir", str(run_dir / "bundle-bin")], outside)
        run("offline-bundle-install", ["/bin/sh", str(installer.with_name("install.sh")), "--no-capture", "--no-app", "--prefix", str(application), "--bin-dir", str(run_dir / "bundle-bin")], outside)
        run("offline-bundle-sharing", [str(application / "venv/bin/python"), str(ROOT / "scripts/check_radar_sharing.py"), "--output", str(run_dir / "bundle-sharing")], outside)
        run("offline-bundle-evolution", [str(application / "venv/bin/python"), str(ROOT / "scripts/check_radar_evolution.py"), "--output", str(run_dir / "bundle-evolution")], outside)
        run("offline-bundle-reporting", [str(application / "venv/bin/python"), str(ROOT / "scripts/check_radar_reporting.py"), "--output", str(run_dir / "bundle-reporting")], outside)
        run("offline-bundle-onboarding", [str(application / "venv/bin/python"), str(ROOT / "scripts/check_radar_onboarding.py"), "--output", str(run_dir / "bundle-onboarding"), "--guide", str(installer.with_name("START_HERE.html"))], outside)
        report["status"] = "passed"
    except (RuntimeError, OSError) as error:
        report["status"] = "failed"
        report["failure"] = str(error)
        print(error, file=sys.stderr)
    finally:
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        (output / "latest-result.json").write_text(
            json.dumps({"result": str(report_path)}, indent=2) + "\n"
        )
        print(f"Evidence: {report_path}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
