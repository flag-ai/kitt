"""Tests for compression utilities."""

from kitt.utils.compression import ResultCompression


class TestResultCompression:
    def test_save_and_load_roundtrip(self, tmp_path):
        outputs = [
            {"prompt": "hello", "output": "world", "score": 0.9},
            {"prompt": "foo", "output": "bar", "score": 0.8},
        ]

        base_path = tmp_path / "results"
        files = ResultCompression.save_outputs(outputs, base_path)

        assert len(files) == 1
        assert files[0].exists()
        assert str(files[0]).endswith(".jsonl.gz")

        loaded = list(ResultCompression.load_outputs(base_path))
        assert len(loaded) == 2
        assert loaded[0]["prompt"] == "hello"
        assert loaded[1]["prompt"] == "foo"

    def test_chunking(self, tmp_path):
        """Test that large outputs get split into chunks."""
        # Create outputs that exceed 1 byte chunk size
        outputs = [{"data": "x" * 1000} for _ in range(100)]

        base_path = tmp_path / "chunked"
        # Very small chunk size to force chunking
        files = ResultCompression.save_outputs(outputs, base_path, chunk_size_mb=0.001)

        assert len(files) > 1

        loaded = list(ResultCompression.load_outputs(base_path))
        assert len(loaded) == 100

    def test_empty_outputs(self, tmp_path):
        base_path = tmp_path / "empty"
        files = ResultCompression.save_outputs([], base_path)
        assert files == []

    def test_save_and_load_single(self, tmp_path):
        data = {"key": "value", "number": 42}
        path = tmp_path / "single.json"

        saved_path = ResultCompression.save_single(data, path)
        assert saved_path.exists()

        loaded = ResultCompression.load_single(saved_path)
        assert loaded["key"] == "value"
        assert loaded["number"] == 42
