"""Tests for dataset manager."""

import json
from pathlib import Path

import pytest

from kitt.benchmarks.dataset_manager import DatasetManager


@pytest.fixture
def data_dir(tmp_path):
    """Create a temporary directory with test data files."""
    return tmp_path


class TestLoadFromDirectory:
    def test_load_txt(self, data_dir):
        txt_file = data_dir / "prompts.txt"
        txt_file.write_text("prompt one\nprompt two\nprompt three\n")

        prompts = DatasetManager.load_from_directory(data_dir)
        assert prompts == ["prompt one", "prompt two", "prompt three"]

    def test_load_jsonl(self, data_dir):
        jsonl_file = data_dir / "prompts.jsonl"
        lines = [
            json.dumps({"prompt": "hello"}),
            json.dumps({"prompt": "world"}),
        ]
        jsonl_file.write_text("\n".join(lines))

        prompts = DatasetManager.load_from_directory(data_dir)
        assert prompts == ["hello", "world"]

    def test_load_json_list(self, data_dir):
        json_file = data_dir / "prompts.json"
        json_file.write_text(json.dumps(["alpha", "beta", "gamma"]))

        prompts = DatasetManager.load_from_directory(data_dir)
        assert prompts == ["alpha", "beta", "gamma"]

    def test_load_json_objects(self, data_dir):
        json_file = data_dir / "prompts.json"
        data = [
            {"text": "first"},
            {"text": "second"},
        ]
        json_file.write_text(json.dumps(data))

        prompts = DatasetManager.load_from_directory(data_dir)
        assert prompts == ["first", "second"]

    def test_sample_size_limit(self, data_dir):
        txt_file = data_dir / "prompts.txt"
        txt_file.write_text("a\nb\nc\nd\ne\n")

        prompts = DatasetManager.load_from_directory(data_dir, sample_size=3)
        assert len(prompts) == 3

    def test_single_file(self, data_dir):
        txt_file = data_dir / "prompts.txt"
        txt_file.write_text("one\ntwo\n")

        prompts = DatasetManager.load_from_directory(txt_file)
        assert prompts == ["one", "two"]

    def test_nonexistent_path(self):
        with pytest.raises(FileNotFoundError):
            DatasetManager.load_from_directory(Path("/nonexistent/path"))

    def test_empty_lines_skipped(self, data_dir):
        txt_file = data_dir / "prompts.txt"
        txt_file.write_text("hello\n\n\nworld\n\n")

        prompts = DatasetManager.load_from_directory(data_dir)
        assert prompts == ["hello", "world"]

    def test_jsonl_string_values(self, data_dir):
        jsonl_file = data_dir / "prompts.jsonl"
        lines = [json.dumps("direct string"), json.dumps("another one")]
        jsonl_file.write_text("\n".join(lines))

        prompts = DatasetManager.load_from_directory(data_dir)
        assert prompts == ["direct string", "another one"]
