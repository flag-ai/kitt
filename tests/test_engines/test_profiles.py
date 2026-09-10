"""Tests for engine configuration profiles."""

import pytest

from kitt.engines.profiles import EngineProfileManager


@pytest.fixture
def profile_mgr(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    (profiles_dir / "llama_cpp-default.yaml").write_text(
        "n_gpu_layers: -1\nn_ctx: 4096\n"
    )
    (profiles_dir / "llama_cpp-high-ctx.yaml").write_text(
        "n_gpu_layers: -1\nn_ctx: 32768\n"
    )
    (profiles_dir / "vllm-default.yaml").write_text("tensor_parallel_size: 1\n")

    return EngineProfileManager(profiles_dir=profiles_dir)


class TestEngineProfileManager:
    def test_list_all_profiles(self, profile_mgr):
        profiles = profile_mgr.list_profiles()
        assert len(profiles) == 3
        assert "llama_cpp-default" in profiles
        assert "llama_cpp-high-ctx" in profiles
        assert "vllm-default" in profiles

    def test_list_by_engine(self, profile_mgr):
        profiles = profile_mgr.list_profiles(engine_name="llama_cpp")
        assert len(profiles) == 2
        assert all(p.startswith("llama_cpp-") for p in profiles)

    def test_load_profile(self, profile_mgr):
        config = profile_mgr.load_profile("llama_cpp-default")
        assert config["n_gpu_layers"] == -1
        assert config["n_ctx"] == 4096

    def test_load_nonexistent(self, profile_mgr):
        with pytest.raises(FileNotFoundError):
            profile_mgr.load_profile("nonexistent")

    def test_merge_profile_with_override(self, profile_mgr):
        user_config = {"n_ctx": 8192, "port": 8081}
        merged = profile_mgr.merge_with_profile(user_config, "llama_cpp-default")

        # User config overrides profile
        assert merged["n_ctx"] == 8192
        # Profile values preserved when not overridden
        assert merged["n_gpu_layers"] == -1
        # User-only values kept
        assert merged["port"] == 8081

    def test_empty_profiles_dir(self, tmp_path):
        mgr = EngineProfileManager(profiles_dir=tmp_path / "nonexistent")
        assert mgr.list_profiles() == []
