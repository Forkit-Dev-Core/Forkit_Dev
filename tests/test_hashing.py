"""Tests for the HashEngine — verifies reproducibility across environments."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from forkit_core.hashing import HashEngine


FAKE_HASH = "a" * 64


# ──────────────────────────────────────────────────────────────────────────────
# Primitive hashing
# ──────────────────────────────────────────────────────────────────────────────

class TestPrimitiveHashing:

    def test_hash_bytes_returns_64_char_hex(self):
        h = HashEngine.hash_bytes(b"hello")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_bytes_known_value(self):
        # SHA-256("hello") is a well-known fixed value
        assert HashEngine.hash_bytes(b"hello") == \
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_hash_bytes_deterministic(self):
        assert HashEngine.hash_bytes(b"hello") == HashEngine.hash_bytes(b"hello")

    def test_hash_bytes_different_inputs_differ(self):
        assert HashEngine.hash_bytes(b"hello") != HashEngine.hash_bytes(b"world")

    def test_hash_string_deterministic(self):
        assert HashEngine.hash_string("abc") == HashEngine.hash_string("abc")

    def test_hash_string_known_value(self):
        # SHA-256("abc") known value
        assert HashEngine.hash_string("abc") == \
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    def test_hash_dict_order_independent(self):
        d1 = {"b": 2, "a": 1, "c": 3}
        d2 = {"a": 1, "c": 3, "b": 2}
        assert HashEngine.hash_dict(d1) == HashEngine.hash_dict(d2)

    def test_hash_dict_deterministic(self):
        d = {"name": "llama", "version": "1.0.0"}
        assert HashEngine.hash_dict(d) == HashEngine.hash_dict(d)

    def test_hash_dict_different_values_differ(self):
        assert HashEngine.hash_dict({"a": 1}) != HashEngine.hash_dict({"a": 2})

    def test_hash_dict_nested_order_independent(self):
        d1 = {"creator": {"org": "ForkIt", "name": "Hamza"}}
        d2 = {"creator": {"name": "Hamza", "org": "ForkIt"}}
        assert HashEngine.hash_dict(d1) == HashEngine.hash_dict(d2)


# ──────────────────────────────────────────────────────────────────────────────
# File hashing
# ──────────────────────────────────────────────────────────────────────────────

class TestFileHashing:

    def test_hash_file_returns_64_char_hex(self, tmp_path):
        f = tmp_path / "weights.bin"
        f.write_bytes(b"model weights" * 1000)
        h = HashEngine.hash_file(f)
        assert len(h) == 64

    def test_hash_file_deterministic(self, tmp_path):
        f = tmp_path / "weights.bin"
        f.write_bytes(b"model weights")
        assert HashEngine.hash_file(f) == HashEngine.hash_file(f)

    def test_hash_file_changes_with_content(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert HashEngine.hash_file(f1) != HashEngine.hash_file(f2)

    def test_hash_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            HashEngine.hash_file("/nonexistent/path/weights.safetensors")

    def test_hash_file_large_file(self, tmp_path):
        # 2 MB — exercises chunked reading
        f = tmp_path / "large.bin"
        f.write_bytes(b"x" * 2_097_152)
        h = HashEngine.hash_file(f)
        assert len(h) == 64


# ──────────────────────────────────────────────────────────────────────────────
# Directory hashing
# ──────────────────────────────────────────────────────────────────────────────

class TestDirectoryHashing:

    def test_hash_directory_deterministic(self, tmp_path):
        (tmp_path / "model.safetensors").write_bytes(b"weights")
        (tmp_path / "config.json").write_text('{"arch": "llama"}')
        h1 = HashEngine.hash_directory(tmp_path)
        h2 = HashEngine.hash_directory(tmp_path)
        assert h1 == h2

    def test_hash_directory_changes_with_content(self, tmp_path):
        f = tmp_path / "model.bin"
        f.write_bytes(b"weights v1")
        h1 = HashEngine.hash_directory(tmp_path)
        f.write_bytes(b"weights v2")
        h2 = HashEngine.hash_directory(tmp_path)
        assert h1 != h2

    def test_hash_directory_extension_filter(self, tmp_path):
        (tmp_path / "model.safetensors").write_bytes(b"weights")
        (tmp_path / "README.md").write_text("ignored")
        h_all = HashEngine.hash_directory(tmp_path)
        h_filt = HashEngine.hash_directory(tmp_path, extensions=[".safetensors"])
        # Filtered hash covers fewer files
        assert h_all != h_filt

    def test_hash_directory_not_a_dir(self, tmp_path):
        f = tmp_path / "file.bin"
        f.write_bytes(b"data")
        with pytest.raises(NotADirectoryError):
            HashEngine.hash_directory(f)


# ──────────────────────────────────────────────────────────────────────────────
# Artifact hashing (high-level)
# ──────────────────────────────────────────────────────────────────────────────

class TestArtifactHashing:

    def test_hash_artifact_single_file(self, tmp_path):
        f = tmp_path / "model.gguf"
        f.write_bytes(b"gguf weights")
        h = HashEngine.hash_artifact(f)
        assert h == HashEngine.hash_file(f)

    def test_hash_artifact_directory(self, tmp_path):
        (tmp_path / "model.safetensors").write_bytes(b"weights")
        (tmp_path / "config.json").write_text("{}")
        h = HashEngine.hash_artifact(tmp_path)
        assert len(h) == 64

    def test_hash_artifact_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            HashEngine.hash_artifact("/nonexistent/path")

    def test_hash_model_artifact_directory(self, tmp_path):
        (tmp_path / "model.safetensors").write_bytes(b"weights")
        (tmp_path / "config.json").write_text('{"hidden_size": 4096}')
        (tmp_path / "README.md").write_text("docs")  # should be ignored
        h_model = HashEngine.hash_model_artifact(tmp_path, include_config=True)
        h_no_cfg = HashEngine.hash_model_artifact(tmp_path, include_config=False)
        assert h_model != h_no_cfg  # config inclusion changes the hash

    def test_hash_model_artifact_single_file(self, tmp_path):
        f = tmp_path / "model.safetensors"
        f.write_bytes(b"weights")
        h = HashEngine.hash_model_artifact(f)
        assert h == HashEngine.hash_file(f)


# ──────────────────────────────────────────────────────────────────────────────
# Metadata hashing
# ──────────────────────────────────────────────────────────────────────────────

class TestMetadataHashing:

    def test_hash_metadata_excludes_volatile_fields(self):
        d = {
            "name":       "my-model",
            "version":    "1.0.0",
            "id":         "some-auto-id",           # volatile
            "created_at": "2024-01-01T00:00:00Z",   # volatile
            "updated_at": "2024-06-01T00:00:00Z",   # volatile
        }
        h1 = HashEngine.hash_metadata(d)
        d2 = {**d, "id": "different-id", "updated_at": "2025-01-01T00:00:00Z"}
        h2 = HashEngine.hash_metadata(d2)
        assert h1 == h2  # volatile fields do not affect the hash

    def test_hash_metadata_sensitive_to_content(self):
        d1 = {"name": "model-a", "version": "1.0.0"}
        d2 = {"name": "model-b", "version": "1.0.0"}
        assert HashEngine.hash_metadata(d1) != HashEngine.hash_metadata(d2)

    def test_hash_metadata_order_independent(self):
        d1 = {"version": "1.0.0", "name": "llama"}
        d2 = {"name": "llama", "version": "1.0.0"}
        assert HashEngine.hash_metadata(d1) == HashEngine.hash_metadata(d2)


# ──────────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────────

class TestVerification:

    def test_verify_file_correct(self, tmp_path):
        f = tmp_path / "model.bin"
        f.write_bytes(b"test content")
        expected = HashEngine.hash_file(f)
        assert HashEngine.verify_file(f, expected) is True

    def test_verify_file_wrong_hash(self, tmp_path):
        f = tmp_path / "model.bin"
        f.write_bytes(b"test content")
        assert HashEngine.verify_file(f, "a" * 64) is False

    def test_verify_artifact_file(self, tmp_path):
        f = tmp_path / "model.gguf"
        f.write_bytes(b"weights")
        h = HashEngine.hash_artifact(f)
        assert HashEngine.verify_artifact(f, h) is True

    def test_verify_dict_correct(self):
        d = {"name": "llama", "version": "1.0.0"}
        h = HashEngine.hash_dict(d)
        assert HashEngine.verify_dict(d, h) is True

    def test_verify_dict_wrong_hash(self):
        d = {"name": "llama"}
        assert HashEngine.verify_dict(d, "a" * 64) is False

    def test_verify_metadata_correct(self):
        d = {"name": "llama", "version": "1.0.0", "id": "auto", "created_at": "now"}
        h = HashEngine.hash_metadata(d)
        assert HashEngine.verify_metadata(d, h) is True


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

class TestUtilities:

    def test_short_id_default_12(self):
        assert HashEngine.short_id("a" * 64) == "a" * 12

    def test_short_id_custom_length(self):
        assert HashEngine.short_id("a" * 64, 8) == "a" * 8

    def test_is_valid_hash_true(self):
        assert HashEngine.is_valid_hash("a" * 64) is True
        assert HashEngine.is_valid_hash("0" * 64) is True
        assert HashEngine.is_valid_hash("deadbeef" * 8) is True

    def test_is_valid_hash_false(self):
        assert HashEngine.is_valid_hash("short") is False
        assert HashEngine.is_valid_hash("g" * 64) is False  # 'g' not in hex
        assert HashEngine.is_valid_hash("A" * 64) is False  # uppercase

    def test_hash_system_prompt(self):
        h = HashEngine.hash_system_prompt("You are a helpful assistant.")
        assert len(h) == 64
        assert h == HashEngine.hash_string("You are a helpful assistant.")
