"""
Minimal local Forkit passport example.

Run: python examples/minimal_local_passport.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forkit-minimal-") as tmpdir:
        client = ForkitClient(registry_root=tmpdir)
        model_id = client.models.register(
            name="hello-local-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator={"name": "Forkit Demo", "organization": "Forkit OSS"},
            description="Minimal local passport demo.",
            license="Apache-2.0",
            status="active",
        )

        stored = client.get_model(model_id)
        verification = client.verify(model_id)
        stats = client.stats()

        print(
            json.dumps(
                {
                    "model_id": model_id,
                    "passport_type": stored.passport_type,
                    "name": stored.name,
                    "valid": verification["valid"],
                    "models": stats["models"],
                    "agents": stats["agents"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
