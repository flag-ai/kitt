"""Tests for LocalModelService — format metadata extraction from manifest."""

import json

from kitt.web.services.local_model_service import (
    LocalModelService,
    _detect_formats_from_path,
)


class TestReadManifestFormats:
    def test_formats_from_devon_metadata(self, tmp_path):
        """Formats are extracted from Devon manifest metadata."""
        manifest = {
            "huggingface::Qwen/Qwen3.5-7B": {
                "path": str(tmp_path / "Qwen3.5-7B"),
                "source": "huggingface",
                "size_bytes": 15_000_000_000,
                "metadata": {"format": ["safetensors"]},
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        svc = LocalModelService(str(tmp_path))
        models = svc.read_manifest()

        assert len(models) == 1
        assert models[0]["formats"] == ["safetensors"]
        assert models[0]["model_id"] == "Qwen/Qwen3.5-7B"

    def test_formats_fallback_to_filesystem(self, tmp_path):
        """When Devon metadata has no format, detect from filesystem."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "weights.gguf").write_bytes(b"\x00")

        manifest = {
            "local::model": {
                "path": str(model_dir),
                "source": "local",
                "size_bytes": 100,
                # No metadata.format
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        svc = LocalModelService(str(tmp_path))
        models = svc.read_manifest()

        assert len(models) == 1
        assert "gguf" in models[0]["formats"]

    def test_empty_formats_for_nonexistent_path(self, tmp_path):
        """When model path doesn't exist, formats is empty."""
        manifest = {
            "local::missing": {
                "path": str(tmp_path / "nonexistent"),
                "source": "local",
                "size_bytes": 0,
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        svc = LocalModelService(str(tmp_path))
        models = svc.read_manifest()
        assert models[0]["formats"] == []

    def test_formats_from_metadata_override_detection(self, tmp_path):
        """When Devon metadata has format, filesystem detection is skipped."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "weights.gguf").write_bytes(b"\x00")

        manifest = {
            "local::model": {
                "path": str(model_dir),
                "source": "local",
                "size_bytes": 100,
                "metadata": {"format": ["pytorch"]},  # Different from gguf on disk
            }
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        svc = LocalModelService(str(tmp_path))
        models = svc.read_manifest()
        # Should use Devon metadata, not filesystem detection
        assert models[0]["formats"] == ["pytorch"]


class TestDetectFormatsFromPath:
    def test_gguf_file(self, tmp_path):
        gguf = tmp_path / "model.gguf"
        gguf.write_bytes(b"\x00")
        assert _detect_formats_from_path(str(gguf)) == ["gguf"]

    def test_safetensors_dir(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00")
        assert _detect_formats_from_path(str(model_dir)) == ["safetensors"]

    def test_nonexistent_path(self, tmp_path):
        assert _detect_formats_from_path(str(tmp_path / "nope")) == []
