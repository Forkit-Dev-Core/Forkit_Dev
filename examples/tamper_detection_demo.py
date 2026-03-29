"""
Tamper detection demo for a stored Forkit passport.

Run: python examples/tamper_detection_demo.py
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
    with tempfile.TemporaryDirectory(prefix="forkit-tamper-") as tmpdir:
        client = ForkitClient(registry_root=tmpdir)
        model_id = client.models.register(
            name="tamper-demo-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator={"name": "Forkit Demo", "organization": "Forkit OSS"},
            status="active",
        )

        before = client.verify(model_id)

        passport_path = Path(tmpdir) / "models" / f"{model_id}.json"
        payload = json.loads(passport_path.read_text(encoding="utf-8"))
        payload["name"] = "tampered-name"
        passport_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        after = client.verify(model_id)

        print(
            json.dumps(
                {
                    "stored_id": model_id,
                    "valid_before": before["valid"],
                    "valid_after": after["valid"],
                    "reason_after": after["reason"],
                    "derived_after": after["derived_id"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
