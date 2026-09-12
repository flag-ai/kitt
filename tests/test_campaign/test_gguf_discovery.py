"""Tests for GGUF quant discovery."""

import sys
from unittest.mock import MagicMock, patch

from kitt.campaign.gguf_discovery import (
    GGUFQuantInfo,
    discover_gguf_quants,
    discover_ollama_tags,
    extract_quant_name,
    filter_quants,
    find_model_path,
)

# huggingface_hub may not be installed; create a stub so @patch targets resolve
if "huggingface_hub" not in sys.modules:
    _hf_stub = MagicMock()
    sys.modules["huggingface_hub"] = _hf_stub


class TestExtractQuantName:
    def test_standard_quants(self):
        assert extract_quant_name("Model-Q4_K_M.gguf") == "Q4_K_M"
        assert extract_quant_name("Model-Q5_K_S.gguf") == "Q5_K_S"
        assert extract_quant_name("Model-Q8_0.gguf") == "Q8_0"
        assert extract_quant_name("Model-Q2_K.gguf") == "Q2_K"

    def test_lowercase_quants(self):
        assert extract_quant_name("qwen2.5-7b-q4_k_m.gguf") == "q4_k_m"

    def test_iq_quants(self):
        assert extract_quant_name("Model-IQ3_M.gguf") == "IQ3_M"
        assert extract_quant_name("Model-IQ4_XS.gguf") == "IQ4_XS"
        assert extract_quant_name("Model-IQ1_S.gguf") == "IQ1_S"
        assert extract_quant_name("Model-IQ2_XXS.gguf") == "IQ2_XXS"
        assert extract_quant_name("Model-IQ3_XXS.gguf") == "IQ3_XXS"

    def test_repacking_variants(self):
        """Q4_0_4_4, Q4_0_4_8, Q4_0_8_8 are distinct quant formats."""
        assert extract_quant_name("Model-Q4_0_4_4.gguf") == "Q4_0_4_4"
        assert extract_quant_name("Model-Q4_0_4_8.gguf") == "Q4_0_4_8"
        assert extract_quant_name("Model-Q4_0_8_8.gguf") == "Q4_0_8_8"

    def test_fp_bf_quants(self):
        assert extract_quant_name("Model-FP16.gguf") == "FP16"
        assert extract_quant_name("Model-BF16.gguf") == "BF16"
        assert extract_quant_name("Model-F32.gguf") == "F32"

    def test_strips_directory(self):
        """Should extract from filename only, not directory path."""
        assert extract_quant_name("Q4_K_M/model-Q4_K_M-00001.gguf") == "Q4_K_M"
        assert extract_quant_name("subdir/Model-IQ3_M.gguf") == "IQ3_M"

    def test_no_match_returns_stem(self):
        assert extract_quant_name("model.gguf") == "model"


class TestDiscoverGGUFQuants:
    @patch("huggingface_hub.list_repo_files")
    def test_single_file_quants(self, mock_list):
        mock_list.return_value = [
            "Model-Q4_K_M.gguf",
            "Model-Q5_K_S.gguf",
            "Model-Q8_0.gguf",
        ]
        quants = discover_gguf_quants("test/repo")
        assert len(quants) == 3
        names = {q.quant_name for q in quants}
        assert names == {"Q4_K_M", "Q5_K_S", "Q8_0"}

    @patch("huggingface_hub.list_repo_files")
    def test_sharded_files(self, mock_list):
        mock_list.return_value = [
            "Model-Q4_K_M-00001-of-00002.gguf",
            "Model-Q4_K_M-00002-of-00002.gguf",
            "Model-Q5_K_S.gguf",
        ]
        quants = discover_gguf_quants("test/repo")
        assert len(quants) == 2

        sharded = next(q for q in quants if q.quant_name == "Q4_K_M")
        assert len(sharded.files) == 2
        assert sharded.is_sharded

        single = next(q for q in quants if q.quant_name == "Q5_K_S")
        assert len(single.files) == 1
        assert not single.is_sharded

    @patch("huggingface_hub.list_repo_files")
    def test_subdirectory_shards_70b(self, mock_list):
        """70B models store shards in subdirectories like Q4_K_M/."""
        mock_list.return_value = [
            "Q4_K_M/Llama-3.3-70B-Q4_K_M-00001-of-00005.gguf",
            "Q4_K_M/Llama-3.3-70B-Q4_K_M-00002-of-00005.gguf",
            "Q4_K_M/Llama-3.3-70B-Q4_K_M-00003-of-00005.gguf",
            "Q4_K_M/Llama-3.3-70B-Q4_K_M-00004-of-00005.gguf",
            "Q4_K_M/Llama-3.3-70B-Q4_K_M-00005-of-00005.gguf",
            "IQ3_M/Llama-3.3-70B-IQ3_M-00001-of-00003.gguf",
            "IQ3_M/Llama-3.3-70B-IQ3_M-00002-of-00003.gguf",
            "IQ3_M/Llama-3.3-70B-IQ3_M-00003-of-00003.gguf",
        ]
        quants = discover_gguf_quants("test/70b-repo")
        assert len(quants) == 2

        q4 = next(q for q in quants if q.quant_name == "Q4_K_M")
        assert len(q4.files) == 5
        assert "Q4_K_M/*.gguf" in q4.include_pattern

        iq3 = next(q for q in quants if q.quant_name == "IQ3_M")
        assert len(iq3.files) == 3

    @patch("huggingface_hub.list_repo_files")
    def test_iq_quant_discovery(self, mock_list):
        mock_list.return_value = [
            "Model-IQ1_S.gguf",
            "Model-IQ2_XXS.gguf",
            "Model-IQ3_M.gguf",
            "Model-IQ4_XS.gguf",
        ]
        quants = discover_gguf_quants("test/repo")
        assert len(quants) == 4
        names = {q.quant_name for q in quants}
        assert "IQ3_M" in names
        assert "IQ4_XS" in names

    @patch("huggingface_hub.list_repo_files")
    def test_empty_repo(self, mock_list):
        mock_list.return_value = ["README.md", "config.json"]
        assert discover_gguf_quants("test/repo") == []

    @patch("huggingface_hub.list_repo_files", side_effect=Exception("API error"))
    def test_api_error(self, mock_list):
        assert discover_gguf_quants("test/repo") == []


class TestDiscoverOllamaTags:
    def test_fallback_on_failure(self):
        """When network fails, returns just the base tag."""
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            tags = discover_ollama_tags("llama3.1:8b")
        assert tags == ["llama3.1:8b"]

    @patch("urllib.request.urlopen")
    def test_parses_html_tags(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"""
            <a href="/library/testmodel:7b-instruct-q4_0">7b-instruct-q4_0</a>
            <a href="/library/testmodel:7b-instruct-q5_K_M">7b-instruct-q5_K_M</a>
            <a href="/library/testmodel:14b-q4_0">14b-q4_0</a>
        """
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        tags = discover_ollama_tags("testmodel:7b")
        assert len(tags) >= 1
        # Should include 7b tags
        assert any("7b" in t for t in tags)


class TestFindModelPath:
    def test_safetensors_directory(self, tmp_path):
        model_dir = tmp_path / "huggingface" / "meta-llama" / "Llama-8B"
        model_dir.mkdir(parents=True)
        (model_dir / "config.json").touch()

        result = find_model_path("meta-llama/Llama-8B", storage_root=tmp_path)
        assert result == str(model_dir)

    def test_gguf_file(self, tmp_path):
        model_dir = tmp_path / "huggingface" / "test" / "repo"
        model_dir.mkdir(parents=True)
        gguf = model_dir / "Model-Q4_K_M.gguf"
        gguf.touch()

        result = find_model_path(
            "test/repo", "Model-Q4_K_M.gguf", storage_root=tmp_path
        )
        assert result == str(gguf)

    def test_gguf_in_subdirectory(self, tmp_path):
        """Full relative path should find files in subdirectories."""
        model_dir = tmp_path / "huggingface" / "test" / "repo" / "Q4_K_M"
        model_dir.mkdir(parents=True)
        gguf = model_dir / "Model-Q4_K_M-00001-of-00002.gguf"
        gguf.touch()

        result = find_model_path(
            "test/repo",
            "Q4_K_M/Model-Q4_K_M-00001-of-00002.gguf",
            storage_root=tmp_path,
        )
        assert result == str(gguf)

    def test_not_found(self, tmp_path):
        assert find_model_path("nonexistent/repo", storage_root=tmp_path) is None

    def test_gguf_not_found(self, tmp_path):
        model_dir = tmp_path / "huggingface" / "test" / "repo"
        model_dir.mkdir(parents=True)

        result = find_model_path("test/repo", "nonexistent.gguf", storage_root=tmp_path)
        assert result is None

    def test_sharded_selects_first_shard(self, tmp_path):
        """When multiple shards exist, should return the first shard (-00001-)."""
        model_dir = tmp_path / "huggingface" / "test" / "repo" / "f32"
        model_dir.mkdir(parents=True)
        shard1 = model_dir / "phi-4-f32-00001-of-00002.gguf"
        shard2 = model_dir / "phi-4-f32-00002-of-00002.gguf"
        shard1.touch()
        shard2.touch()

        # Searching for the include pattern should find the first shard
        result = find_model_path(
            "test/repo",
            "f32/phi-4-f32-00001-of-00002.gguf",
            storage_root=tmp_path,
        )
        assert result == str(shard1)

    def test_sharded_fallback_finds_first_shard(self, tmp_path):
        """When exact file not found, fallback should find first shard by quant."""
        model_dir = tmp_path / "huggingface" / "test" / "repo"
        model_dir.mkdir(parents=True)
        shard1 = model_dir / "model-f32-00001-of-00002.gguf"
        shard2 = model_dir / "model-f32-00002-of-00002.gguf"
        shard1.touch()
        shard2.touch()

        # Pass a non-existent filename that contains the quant name
        result = find_model_path(
            "test/repo",
            "model-f32.gguf",
            storage_root=tmp_path,
        )
        # Should find the first shard via _find_first_shard fallback
        assert result == str(shard1)


class TestFilterQuants:
    def test_skip_patterns(self):
        quants = [
            GGUFQuantInfo(quant_name="Q4_K_M", files=["a.gguf"]),
            GGUFQuantInfo(quant_name="IQ1_S", files=["b.gguf"]),
            GGUFQuantInfo(quant_name="IQ2_XXS", files=["c.gguf"]),
            GGUFQuantInfo(quant_name="Q8_0", files=["d.gguf"]),
        ]
        filtered = filter_quants(quants, skip_patterns=["IQ1_*", "IQ2_*"])
        names = [q.quant_name for q in filtered]
        assert names == ["Q4_K_M", "Q8_0"]

    def test_include_only(self):
        quants = [
            GGUFQuantInfo(quant_name="Q4_K_M", files=["a.gguf"]),
            GGUFQuantInfo(quant_name="Q5_K_S", files=["b.gguf"]),
            GGUFQuantInfo(quant_name="Q8_0", files=["c.gguf"]),
        ]
        filtered = filter_quants(quants, include_only=["Q4_*", "Q8_*"])
        names = [q.quant_name for q in filtered]
        assert names == ["Q4_K_M", "Q8_0"]

    def test_no_filters(self):
        quants = [GGUFQuantInfo(quant_name="Q4_K_M", files=["a.gguf"])]
        assert filter_quants(quants) == quants
