"""Bundled executable lookup stays independent of PATH and repository content."""
import hashlib
import json
import sys

import pytest

from forkit_radar.mac_runtime import bundled_git


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    root = tmp_path / 'app/Resources/runtime'
    (root / 'bin').mkdir(parents=True)
    (root / 'bin/python3.11').write_bytes(b'controlled runtime')
    git = root.parent / 'git/bin/git'
    git.parent.mkdir(parents=True)
    git.write_bytes(b'local checked executable')
    monkeypatch.setattr(sys, 'platform', 'darwin')
    monkeypatch.setattr(sys, 'executable', str(root / 'bin/python3.11'))
    monkeypatch.setenv('PATH', '/untrusted-project-bin')
    (root / 'forkit-runtime.json').write_text(json.dumps({'format': 1,
        'git_sha256': hashlib.sha256(git.read_bytes()).hexdigest()}))
    bundled_git.cache_clear()
    yield root, git
    bundled_git.cache_clear()


def test_bundled_git_uses_only_shipped_fixed_path(bundle):
    _, git = bundle
    assert bundled_git() == str(git)


def test_modified_git_is_refused_without_system_fallback(bundle):
    _, git = bundle
    git.write_bytes(b'changed')
    with pytest.raises(ValueError, match='bundled_git_changed'):
        bundled_git()


def test_external_executable_link_is_refused(bundle):
    root, git = bundle
    target = root.parent / 'outside'
    git.rename(target)
    git.symlink_to(target)
    with pytest.raises((OSError, ValueError)):
        bundled_git()


def test_regular_cli_keeps_existing_system_git_path(bundle):
    root, _ = bundle
    (root / 'forkit-runtime.json').unlink()
    assert bundled_git() is None


def test_runtime_alias_resolves_to_the_same_bundled_git(bundle, monkeypatch):
    root, git = bundle
    alias = root.parent / 'runtime-alias'
    alias.symlink_to(root, target_is_directory=True)
    monkeypatch.setattr(sys, 'executable', str(alias / 'bin/python3.11'))
    assert bundled_git() == str(git)
