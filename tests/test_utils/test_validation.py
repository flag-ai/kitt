"""Tests for model format detection and validation utilities."""

from kitt.utils.validation import (
    detect_model_format,
    validate_model_format,
    validate_model_path,
)


class TestDetectModelFormat:
    def test_gguf_file(self, tmp_path):
        gguf = tmp_path / "model.gguf"
        gguf.write_bytes(b"\x00" * 100)
        assert detect_model_format(str(gguf)) == "gguf"

    def test_safetensors_dir(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)
        assert detect_model_format(str(model_dir)) == "safetensors"

    def test_pytorch_dir(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "pytorch_model.bin").write_bytes(b"\x00" * 100)
        assert detect_model_format(str(model_dir)) == "pytorch"

    def test_pytorch_model_bin(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.bin").write_bytes(b"\x00" * 100)
        assert detect_model_format(str(model_dir)) == "pytorch"

    def test_gguf_in_dir(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "weights.gguf").write_bytes(b"\x00" * 100)
        assert detect_model_format(str(model_dir)) == "gguf"

    def test_safetensors_takes_priority_over_pytorch(self, tmp_path):
        """When both safetensors and pytorch exist, safetensors wins."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)
        (model_dir / "pytorch_model.bin").write_bytes(b"\x00" * 100)
        assert detect_model_format(str(model_dir)) == "safetensors"

    def test_unknown_format(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")
        assert detect_model_format(str(model_dir)) is None

    def test_empty_dir(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        assert detect_model_format(str(model_dir)) is None

    def test_nonexistent_path(self, tmp_path):
        assert detect_model_format(str(tmp_path / "nonexistent")) is None

    def test_non_gguf_file(self, tmp_path):
        f = tmp_path / "model.txt"
        f.write_text("not a model")
        assert detect_model_format(str(f)) is None


class TestValidateModelFormat:
    def test_compatible_gguf(self, tmp_path):
        gguf = tmp_path / "model.gguf"
        gguf.write_bytes(b"\x00" * 100)
        assert validate_model_format(str(gguf), ["gguf"]) is None

    def test_incompatible_safetensors_to_gguf(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)
        error = validate_model_format(str(model_dir), ["gguf"])
        assert error is not None
        assert "safetensors" in error
        assert "gguf" in error

    def test_compatible_safetensors(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "model.safetensors").write_bytes(b"\x00" * 100)
        assert validate_model_format(str(model_dir), ["safetensors", "pytorch"]) is None

    def test_unknown_format_passes(self, tmp_path):
        """Unknown format should not block — let the engine try."""
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        (model_dir / "config.json").write_text("{}")
        assert validate_model_format(str(model_dir), ["safetensors"]) is None


class TestValidateModelPath:
    def test_existing_path(self, tmp_path):
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        assert validate_model_path(str(model_dir)) is None

    def test_missing_path(self, tmp_path):
        error = validate_model_path(str(tmp_path / "nonexistent"))
        assert error is not None
        assert "does not exist" in error
