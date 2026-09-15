"""Mac subprocess actions reuse real Core identities and local Git receipts."""

import base64
import hashlib
import json
import re
import subprocess
from pathlib import Path

import pytest

from forkit_radar.capture import automatic as auto
from forkit_radar.desktop import perform
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.associations import associations, projects, selection_for
from forkit_radar.sessions.storage import SessionStore


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    monkeypatch.setattr(auto, "detected", lambda _: {"codex"})
    project = home / "project"
    project.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
    (project / "app.py").write_text("value = 1\n")
    root = home / ".forkit-radar"
    perform("onboard", root, {})
    return root, project


def event(root, project, name, identity="first"):
    auto.automatic_receive(
        "codex",
        root,
        auto.encode(
            {
                "cwd": str(project),
                "hook_event_name": name,
                "session_id": identity,
                "source": "startup",
            }
        ),
    )


def first_receipt(root, project):
    event(root, project, "SessionStart")
    (project / "app.py").write_text("value = 2\n")
    event(root, project, "SessionEnd")
    return projects(SessionStore(root))[0]["project_id"]


def test_history_render_does_not_block_capture_or_setup(workspace, monkeypatch):
    from forkit_radar.capture import setup_files
    from forkit_radar.sessions import summary

    root, project = workspace
    first_receipt(root, project)
    event(root, project, "SessionStart", "during-render")
    (project / "app.py").write_text("value = 3\n")
    verify = summary.verify

    def with_concurrent_end(db):
        stream = iter(verify(db))
        first = next(stream)
        # Both the live SQLite and setup locks must be available while the
        # immutable history copy is checked and rendered.
        with setup_files.locked(root):
            assert auto.state(root)["agents"]["codex"]["enabled"]
        event(root, project, "SessionEnd", "during-render")
        yield first
        yield from stream

    monkeypatch.setattr(summary, "verify", with_concurrent_end)
    response = perform("render", root, {})
    assert Path(response["file"]).is_file()
    assert not SessionStore(root).active() and len(SessionStore(root).history()) == 2


def metadata(project_id):
    return {
        "project_id": project_id,
        "name": "Support agent",
        "version": "1.0.0",
        "creator": "Local developer",
        "model_name": "Declared coding model",
        "model_version": "1.0.0",
    }


def test_onboard_preserves_pause_and_does_not_create_account(workspace):
    root, _ = workspace
    perform("pause", root, {})
    raw = (root / auto.STATE).read_bytes()
    perform("onboard", root, {})
    assert (root / auto.STATE).read_bytes() == raw
    assert not auto.state(root)["agents"]["codex"]["enabled"]
    assert not (root / "sessions.sqlite3").exists()


def test_core_passport_is_selected_only_for_future_sessions(workspace):
    root, project = workspace
    project_id = first_receipt(root, project)
    before = SessionStore(root).receipt()
    created = perform("create-passport", root, metadata(project_id))
    assert selection_for(root, project).passport_id == created["passport_id"]
    event(root, project, "SessionStart", "second")
    with pytest.raises(ContractError, match="finish_session"):
        perform("clear-passport", root, {"project_id": project_id})
    (project / "app.py").write_text("value = 3\n")
    # A damaged later choice must not prevent finishing the stored baseline.
    (root / "session-associations.json").write_bytes(b"{")
    event(root, project, "SessionEnd", "second")
    receipt = SessionStore(root).receipt()
    assert receipt.passport_id == created["passport_id"]
    assert receipt.passport_after.version == "1.0.0"
    assert before.passport_id is None and not SessionStore(root).active()
    with pytest.raises(ValueError):
        event(root, project, "SessionStart", "third")


def test_replaced_project_cannot_inherit_or_create_identity(workspace):
    root, project = workspace
    project_id = first_receipt(root, project)
    project.rename(project.with_name("moved"))
    project.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
    with pytest.raises(ContractError, match="project_replaced"):
        perform("create-passport", root, metadata(project_id))
    assert not (root / "registry").exists()
    assert selection_for(root, project).passport_id is None


def test_active_project_does_not_create_unused_identity(workspace):
    root, project = workspace
    event(root, project, "SessionStart")
    project_id = projects(SessionStore(root))[0]["project_id"]
    with pytest.raises(ContractError, match="finish_session"):
        perform("create-passport", root, metadata(project_id))
    assert not (root / "registry").exists()


def test_invalid_passport_version_is_actionable_before_identity_write(workspace):
    root, project = workspace
    data = metadata(first_receipt(root, project))
    for key in ("version", "model_version"):
        with pytest.raises(ContractError, match="passport_version_format"):
            perform("create-passport", root, {**data, key: "1"})
        assert not (root / "registry").exists()


def test_native_render_is_private_and_has_no_terminal_instructions(workspace):
    root, project = workspace
    first_receipt(root, project)
    result = perform("render", root, {})
    html = Path(result["file"]).read_text()
    assert '<body data-native="true">' in html
    assert "forkit-radar setup" not in html and "Use Capture in the toolbar" in html
    assert Path(result["file"]).stat().st_mode & 0o077 == 0
    assert "No account. No uploads." in html
    for script in re.findall(r"<script>(.*?)</script>", html, re.S):
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        assert "sha256-" + digest in html


def test_local_selection_clear_keeps_existing_identity_and_receipt(workspace):
    root, project = workspace
    project_id = first_receipt(root, project)
    created = perform("create-passport", root, metadata(project_id))
    registry_file = root / "registry/agents" / (created["passport_id"] + ".json")
    raw = registry_file.read_bytes()
    perform("clear-passport", root, {"project_id": project_id})
    assert not associations(root)["projects"]
    assert registry_file.read_bytes() == raw and len(SessionStore(root).history()) == 1
    assert json.loads(raw)["name"] == "Support agent"


def test_existing_picker_checks_raw_identity_and_model_without_registry_writes(workspace):
    root, project = workspace
    project_id = first_receipt(root, project)
    created = perform("create-passport", root, metadata(project_id))
    registry = root / "registry"
    bad = registry / "agents" / ("a" * 64 + ".json")
    bad.write_text("{}")
    bad.chmod(0o600)
    before = {str(p): p.read_bytes() for p in registry.rglob("*") if p.is_file()}
    result = perform("passport-options", root, {"registry": None})
    assert result["passports"] == [
        {
            "registry": str(registry),
            "id": created["passport_id"],
            "name": "Support agent",
            "version": "1.0.0",
        }
    ]
    assert result["skipped"] == 1
    assert {str(p): p.read_bytes() for p in registry.rglob("*") if p.is_file()} == before
    perform("clear-passport", root, {"project_id": project_id})
    choice = result["passports"][0]
    perform(
        "select-passport",
        root,
        {"project_id": project_id, "registry": choice["registry"], "passport_id": choice["id"]},
    )
    assert selection_for(root, project).passport_id == created["passport_id"]
    (registry / "models" / (created["model_id"] + ".json")).unlink()
    assert not perform("passport-options", root, {"registry": str(registry)})["passports"]
    alias = root / "registry-alias"
    alias.symlink_to(registry, target_is_directory=True)
    with pytest.raises(ContractError, match="local_registry_unavailable"):
        perform("passport-options", root, {"registry": str(alias)})


def test_optional_counts_require_first_result_and_new_consent(workspace, monkeypatch):
    from unittest.mock import patch

    from forkit_radar.reporting.usage_storage import UsageStore

    root, project = workspace
    monkeypatch.setenv('FORKIT_USAGE_STORE', str(root / 'test-usage'))
    data = {'endpoint': 'https://counts.example.org/api/v1/radar', 'consent': 'usage-v3'}
    assert perform('usage-status', root, {})['has_receipt'] is False
    with patch.object(UsageStore, 'enable') as enable:
        with pytest.raises(ContractError, match='first_receipt'):
            perform('usage-enable', root, data)
        enable.assert_not_called()
        first_receipt(root, project)
        with pytest.raises(ContractError, match='first_receipt'):
            perform('usage-enable', root, {**data, 'consent': 'usage-v2'})
        assert perform('usage-enable', root, data) == {'saved': True, 'sent': False}
        enable.assert_called_once_with(data['endpoint'], consent='usage-v3')
    assert not (root / 'test-usage').exists()


def test_native_render_never_counts_as_a_view_and_disable_stops_intent(workspace, monkeypatch):
    from unittest.mock import patch

    from forkit_radar.reporting.usage_storage import UsageStore

    root, project = workspace
    monkeypatch.setenv('FORKIT_USAGE_STORE', str(root / 'test-usage'))
    first_receipt(root, project)
    usage = UsageStore(root / 'test-usage')
    usage.enable('http://127.0.0.1:8766/api/v1/radar', consent='usage-v3', validation=True, allow_local=True)
    with patch('forkit_radar.reporting.usage_worker.kick') as worker:
        perform('render', root, {})
        assert usage.preview().days[-1].viewed == 0
        worker.assert_not_called()
        perform('engagement', root, {'action': 'history'})
        assert usage.preview().days[-1].viewed == usage.preview().days[-1].history_viewed == 1
        perform('usage-disable', root, {})
        worker.reset_mock()
        perform('engagement', root, {'action': 'card'})
        worker.assert_not_called()
    with pytest.raises(ContractError, match='invalid_engagement'):
        perform('engagement', root, {'action': 'private/path'})
