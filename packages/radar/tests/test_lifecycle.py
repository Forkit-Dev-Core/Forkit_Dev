"""Real process locks and durable interrupted-maintenance boundaries."""
import os
import select
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from forkit_radar.jsonio import ContractError
from forkit_radar.lifecycle import guard
from forkit_radar.sessions.storage import SessionStore

PROGRAM = '''
import sys
from pathlib import Path
from forkit_radar.lifecycle import guard
try:
    with guard(Path(sys.argv[1]), exclusive=sys.argv[2] == 'exclusive'):
        print('acquired', flush=True)
        if len(sys.argv) > 3: sys.stdin.read()
except ValueError as error:
    print(str(error))
    raise SystemExit(1)
'''


def child(root, mode):
    return subprocess.run([sys.executable, '-I', '-B', '-c', PROGRAM, str(root), mode],
                          capture_output=True, text=True, timeout=5)


def test_independent_capture_processes_share_but_maintenance_refuses(tmp_path):
    root = tmp_path / 'store'
    with guard(root):
        assert child(root, 'shared').stdout.strip() == 'acquired'
        result = child(root, 'exclusive')
        assert result.returncode == 1 and result.stdout.strip() == 'local_capture_busy_retry'
    assert child(root, 'exclusive').returncode == 0


def test_first_capture_lock_creation_is_safe_under_contention(tmp_path):
    # This exercises the actual APFS create/open boundary, not a mocked lock.
    for batch in range(50):
        root = tmp_path / str(batch)
        barrier = threading.Barrier(4)

        def capture(_, root=root, barrier=barrier):
            barrier.wait(timeout=5)
            with guard(root):
                return True

        with ThreadPoolExecutor(max_workers=4) as pool:
            assert all(pool.map(capture, range(4)))


def test_exclusive_change_blocks_other_processes_and_capture_reentry(tmp_path):
    root = tmp_path / 'store'
    with guard(root, exclusive=True):
        with guard(root, exclusive=True):
            pass  # Installer's nested repair/setup steps reuse this thread's lock.
        for mode in ('shared', 'exclusive'):
            assert child(root, mode).stdout.strip() == 'local_capture_busy_retry'
        with pytest.raises(ContractError, match='local_capture_busy_retry'):
            with guard(root):
                pytest.fail('capture entered an in-flight maintenance operation')


def test_process_death_releases_lock_but_not_recovery_journal(tmp_path):
    root = tmp_path / 'store'
    process = subprocess.Popen([sys.executable, '-I', '-B', '-c', PROGRAM, str(root), 'exclusive', 'wait'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert select.select([process.stdout], [], [], 5)[0]
        assert process.stdout.readline().strip() == b'acquired'
        journal = root / 'mac-install-transaction.json'
        journal.write_bytes(b'{}')
        journal.chmod(0o600)
        assert child(root, 'shared').stdout.strip() == 'local_capture_busy_retry'
        process.kill()
        process.communicate(timeout=5)
        assert child(root, 'shared').stdout.strip() == 'mac_update_recovery_required'
        assert child(root, 'exclusive').returncode == 0  # Explicit repair can proceed.
        journal.unlink()
        assert child(root, 'shared').returncode == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


@pytest.mark.parametrize('name', ['mac-install-transaction.json', 'mac-removal.json'])
def test_interrupted_change_preserves_active_baseline_until_repair(tmp_path, name):
    root = tmp_path / 'store'
    project = tmp_path / 'project'
    project.mkdir()
    subprocess.run(['/usr/bin/git', 'init', '-q', str(project)], check=True)
    (project / 'app.py').write_text('before\n')
    store = SessionStore(root)
    started, _ = store.start(project, tool='codex')
    before = (root / 'sessions.sqlite3').read_bytes()
    journal = root / name
    journal.write_bytes(b'{}')
    journal.chmod(0o600)
    with pytest.raises(ContractError, match='mac_update_recovery_required'):
        store.finish(started.session_id)
    assert (root / 'sessions.sqlite3').read_bytes() == before
    assert len(store.active()) == 1
    journal.unlink()
    recovered = store.finish(started.session_id, outcome='recovered')
    assert recovered.elapsed_ms is None and recovered.comparison == 'partial'


@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'writable'])
def test_lock_file_cannot_redirect_or_bypass_serialization(tmp_path, unsafe):
    root = tmp_path / 'store'
    root.mkdir(mode=0o700)
    target = tmp_path / 'keep'
    target.write_bytes(b'untouched')
    target.chmod(0o600)
    lock = root / 'lifecycle.lock'
    if unsafe == 'symlink':
        lock.symlink_to(target)
    elif unsafe == 'hardlink':
        os.link(target, lock)
    else:
        lock.write_bytes(b'')
        lock.chmod(0o666)
    with pytest.raises((OSError, ContractError)):
        with guard(root):
            pytest.fail('unsafe lock accepted')
    assert target.read_bytes() == b'untouched'
