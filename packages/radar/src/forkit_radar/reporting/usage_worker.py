"""Short lived, bounded reporter. No service, scheduler, shell, or remote code."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from .client import request
from .usage_contracts import UsageContribution
from .usage_storage import UsageStore, root

INTERVAL = 86_400
DEADLINE = 7
WORKER = "forkit_radar.reporting.usage_worker"


def deliver(store, *, now=None, transport=request):
    clock = int(time.time() if now is None else now)
    # Reserve before network I/O, so crashes and concurrent commands cannot
    # create extra attempts. A lost ACK retries the same immutable snapshot.
    with store._connect(write=True) as db:
        p = store._profile(db)
        if p["state"] != "enabled" or (os.environ.get("CI") and p["audience"] != "validation"):
            return False
        if p["last_attempt"] and clock - p["last_attempt"] < INTERVAL:
            return False
        if p["pending"] is None or p["attempts"] >= 3:
            p["sequence"] += 1
            p["pending"] = store.contribution(db, p["sequence"]).model_dump(mode="json")
            p["attempts"] = 0
        p.update(last_attempt=clock, attempts=p["attempts"] + 1, last_result="pending")
        store._save(db, p)
        reserved = p["sequence"]
    # Recheck consent under the write lock; disable/withdraw serialize with
    # an in-flight attempt. No queued PUT may start after disable completes.
    with store._connect(write=True) as db:
        p = store._profile(db)
        if p["state"] != "enabled" or p["pending"] is None or p["sequence"] != reserved:
            return False
        packet = UsageContribution.model_validate(p["pending"])
        try:
            transport(p, "PUT", packet, route="installations", timeout=3, schema_version="2.0")
        except (OSError, ValueError):
            p["last_result"] = "unconfirmed"
        else:
            p.update(pending=None, last_sent_sequence=reserved, last_result="confirmed", attempts=0)
        store._save(db, p)
        return p["last_result"] == "confirmed"


def begin_withdrawal(store):
    with store._connect(write=True) as db:
        p = store._profile(db)
        p.update(state="withdrawing", pending=None, last_result="withdrawal_pending")
        store._save(db, p)


def withdraw(store, *, transport=request):
    with store._connect(write=True) as db:
        p = store._profile(db)
        if p["state"] != "withdrawing":
            return False
        transport(p, "DELETE", route="installations", timeout=3, schema_version="2.0")
        p.update(state="withdrawn", pending=None, last_result="withdrawn")
        store._save(db, p)
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM seen_passports")
        return True


def supervise(operation="deliver"):
    # The process deadline includes DNS, TLS and response body handling.
    # subprocess.run kills and reaps a timed-out child; no retry loop lives on.
    try:
        return subprocess.run(
            [sys.executable, "-I", "-m", WORKER, "--child", operation],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=DEADLINE,
            check=False,
        ).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 2


def kick(store=None):
    store = store or UsageStore(root())
    status = store.status()
    if status["state"] != "enabled":
        return
    with store._connect() as db:
        p = store._profile(db)
        if p["last_attempt"] and int(time.time()) - p["last_attempt"] < INTERVAL:
            return
    subprocess.Popen(
        [sys.executable, "-I", "-m", WORKER],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,
    )


if __name__ == "__main__":
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--child":
            result = (withdraw if sys.argv[2] == "withdraw" else deliver)(UsageStore(root()))
            raise SystemExit(0 if result else 2)
        raise SystemExit(supervise())
    except (OSError, ValueError):
        raise SystemExit(2) from None
