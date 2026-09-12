"""Tests for hardware- and platform-aware Docker image selection."""

from unittest.mock import patch

from kitt.engines.image_resolver import (
    clear_cache,
    get_build_recipe,
    get_engine_compatibility,
    get_supported_engines,
    has_hardware_overrides,
    is_kitt_managed_image,
    resolve_image,
)


class TestResolveImage:
    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    def test_no_gpu_returns_default(self, mock_cc, mock_arch):
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "vllm/vllm-openai:latest"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(8, 9))
    def test_ada_lovelace_returns_default(self, mock_cc, mock_arch):
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "vllm/vllm-openai:latest"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(9, 0))
    def test_hopper_returns_default(self, mock_cc, mock_arch):
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "vllm/vllm-openai:latest"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(10, 0))
    def test_blackwell_b200_returns_ngc(self, mock_cc, mock_arch):
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 0))
    def test_blackwell_rtx5090_returns_ngc(self, mock_cc, mock_arch):
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="arm64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_blackwell_gb10_returns_ngc(self, mock_cc, mock_arch):
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="arm64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_blackwell_gb10_llama_cpp_returns_arm64_build(self, mock_cc, mock_arch):
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "kitt/llama-cpp:arm64"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(10, 0))
    def test_blackwell_b200_llama_cpp_returns_spark_build(self, mock_cc, mock_arch):
        """x86_64 Blackwell falls through arm64 override to wildcard spark build."""
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "kitt/llama-cpp:spark"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(8, 9))
    def test_ada_lovelace_llama_cpp_returns_default(self, mock_cc, mock_arch):
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "ghcr.io/ggml-org/llama.cpp:server-cuda"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_unknown_engine_returns_default(self, mock_cc, mock_arch):
        result = resolve_image("unknown_engine", "some/image:latest")
        assert result == "some/image:latest"


class TestClearCache:
    def test_clear_allows_redetection(self):
        """After clear, the next call re-detects compute capability."""
        with (
            patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1)),
            patch("kitt.engines.image_resolver._detect_arch", return_value="amd64"),
        ):
            result1 = resolve_image("vllm", "vllm/vllm-openai:latest")
            assert result1 == "nvcr.io/nvidia/vllm:26.01-py3"

        clear_cache()

        with (
            patch("kitt.engines.image_resolver._detect_cc", return_value=None),
            patch("kitt.engines.image_resolver._detect_arch", return_value="amd64"),
        ):
            result2 = resolve_image("vllm", "vllm/vllm-openai:latest")
            assert result2 == "vllm/vllm-openai:latest"


class TestGetSupportedEngines:
    def test_returns_all_registered_engines(self):
        """All engines in _IMAGE_OVERRIDES should be returned."""
        engines = get_supported_engines()
        assert "vllm" in engines
        assert "llama_cpp" in engines
        assert "ollama" in engines

    def test_returns_list(self):
        engines = get_supported_engines()
        assert isinstance(engines, list)


class TestHasHardwareOverrides:
    def test_vllm_has_overrides(self):
        """vLLM has Blackwell overrides."""
        assert has_hardware_overrides("vllm") is True

    def test_llama_cpp_has_overrides(self):
        """llama.cpp has Blackwell overrides for ARM64+CUDA."""
        assert has_hardware_overrides("llama_cpp") is True

    def test_ollama_no_overrides(self):
        """Ollama currently has no hardware-specific overrides."""
        assert has_hardware_overrides("ollama") is False

    def test_unknown_engine_no_overrides(self):
        """Unknown engines have no overrides."""
        assert has_hardware_overrides("nonexistent_engine") is False


class TestBuildRecipe:
    def test_llama_cpp_spark_recipe_exists(self):
        recipe = get_build_recipe("kitt/llama-cpp:spark")
        assert recipe is not None
        assert recipe.dockerfile == "docker/llama_cpp/Dockerfile.spark"
        assert recipe.target == "server"
        assert recipe.experimental is False

    def test_llama_cpp_arm64_recipe_exists(self):
        recipe = get_build_recipe("kitt/llama-cpp:arm64")
        assert recipe is not None
        assert recipe.dockerfile == "docker/llama_cpp/Dockerfile.arm64"
        assert recipe.target == "server"
        assert recipe.experimental is False

    def test_registry_image_has_no_recipe(self):
        assert get_build_recipe("vllm/vllm-openai:latest") is None
        assert get_build_recipe("nvcr.io/nvidia/vllm:26.01-py3") is None

    def test_dockerfile_path_is_absolute(self):
        recipe = get_build_recipe("kitt/llama-cpp:spark")
        assert recipe.dockerfile_path.is_absolute()
        assert recipe.dockerfile_path.name == "Dockerfile.spark"

    def test_arm64_dockerfile_path_is_absolute(self):
        recipe = get_build_recipe("kitt/llama-cpp:arm64")
        assert recipe.dockerfile_path.is_absolute()
        assert recipe.dockerfile_path.name == "Dockerfile.arm64"


class TestIsKittManagedImage:
    def test_kitt_managed_images(self):
        assert is_kitt_managed_image("kitt/llama-cpp:spark") is True
        assert is_kitt_managed_image("kitt/llama-cpp:arm64") is True

    def test_registry_images(self):
        assert is_kitt_managed_image("vllm/vllm-openai:latest") is False
        assert is_kitt_managed_image("nvcr.io/nvidia/vllm:26.01-py3") is False
        assert is_kitt_managed_image("ollama/ollama:latest") is False


class TestFutureHardwareCompatibility:
    """Tests to ensure graceful handling of future/unknown hardware."""

    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(15, 0))
    def test_future_gpu_falls_back_to_highest_override(self, mock_cc, mock_arch):
        """A future GPU (cc 15.0) should match the highest available override."""
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        # Should match (10, 0) override since 15.0 >= 10.0
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(15, 0))
    def test_future_gpu_llama_cpp_uses_kitt_managed(self, mock_cc, mock_arch):
        """A future x86_64 GPU should match llama.cpp spark build (wildcard arch)."""
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "kitt/llama-cpp:spark"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(7, 5))
    def test_older_gpu_returns_default(self, mock_cc, mock_arch):
        """Older GPUs (Turing) return default image."""
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "vllm/vllm-openai:latest"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(8, 6))
    def test_ampere_returns_default(self, mock_cc, mock_arch):
        """Ampere GPUs (RTX 30 series) return default image."""
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "vllm/vllm-openai:latest"


class TestUserConfigOverrides:
    """Tests for user-configurable image overrides via ~/.kitt/engines.yaml."""

    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch(
        "kitt.engines.image_resolver._load_user_overrides",
        return_value={"vllm": "vllm/vllm-openai:latest"},
    )
    def test_user_config_overrides_hardware(self, mock_user, mock_cc, mock_arch):
        """User config takes priority over hardware-aware overrides."""
        result = resolve_image("vllm", "default/image:latest")
        assert result == "vllm/vllm-openai:latest"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    @patch(
        "kitt.engines.image_resolver._load_user_overrides",
        return_value={},
    )
    def test_empty_user_config_falls_through(self, mock_user, mock_cc, mock_arch):
        """Empty user config falls through to hardware overrides."""
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.image_resolver._load_user_overrides",
        return_value={"llama_cpp": "custom/llama:v1"},
    )
    def test_user_config_without_gpu(self, mock_user, mock_cc, mock_arch):
        """User config works even without GPU detection."""
        result = resolve_image("llama_cpp", "default/llama:latest")
        assert result == "custom/llama:v1"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=None)
    @patch(
        "kitt.engines.image_resolver._load_user_overrides",
        return_value={"vllm": "custom/vllm:v2"},
    )
    def test_user_config_only_affects_specified_engine(
        self, mock_user, mock_cc, mock_arch
    ):
        """User config for vllm doesn't affect llama_cpp."""
        result = resolve_image("llama_cpp", "default/llama:latest")
        assert result == "default/llama:latest"


class TestArchAwareResolution:
    """Tests for platform-aware (CPU architecture) image selection."""

    def setup_method(self):
        clear_cache()

    def teardown_method(self):
        clear_cache()

    @patch("kitt.engines.image_resolver._detect_arch", return_value="arm64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_arm64_blackwell_llama_cpp_returns_arm64_image(self, mock_cc, mock_arch):
        """ARM64 + Blackwell selects the arm64-specific llama.cpp image."""
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "kitt/llama-cpp:arm64"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="amd64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_amd64_blackwell_llama_cpp_returns_spark_image(self, mock_cc, mock_arch):
        """x86_64 + Blackwell skips arm64 override, falls to wildcard spark build."""
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "kitt/llama-cpp:spark"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="arm64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(8, 9))
    def test_arm64_non_blackwell_returns_default(self, mock_cc, mock_arch):
        """ARM64 + non-Blackwell (Ada Lovelace) returns default — no cc match."""
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        assert result == "ghcr.io/ggml-org/llama.cpp:server-cuda"

    @patch("kitt.engines.image_resolver._detect_arch", return_value=None)
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_no_arch_detection_matches_wildcard(self, mock_cc, mock_arch):
        """When arch detection returns None, wildcard (None) overrides still match."""
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value=None)
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_no_arch_detection_skips_arch_specific(self, mock_cc, mock_arch):
        """When arch is None, arch-specific overrides (arm64) are skipped."""
        result = resolve_image("llama_cpp", "ghcr.io/ggml-org/llama.cpp:server-cuda")
        # arm64 override requires "arm64" != None, so it's skipped
        # Wildcard (None, (10,0)) matches because None == None is not checked,
        # the condition is: required_arch is not None and required_arch != arch
        # For wildcard: required_arch is None -> condition is False -> match proceeds
        assert result == "kitt/llama-cpp:spark"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="arm64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(10, 0))
    def test_arm64_vllm_blackwell_uses_wildcard(self, mock_cc, mock_arch):
        """vLLM has only wildcard overrides — arm64 matches the wildcard entry."""
        result = resolve_image("vllm", "vllm/vllm-openai:latest")
        assert result == "nvcr.io/nvidia/vllm:26.01-py3"

    @patch("kitt.engines.image_resolver._detect_arch", return_value="arm64")
    @patch("kitt.engines.image_resolver._detect_cc", return_value=(12, 1))
    def test_arm64_blackwell_ollama_returns_default(self, mock_cc, mock_arch):
        """Ollama has no overrides — returns default on all hardware."""
        result = resolve_image("ollama", "ollama/ollama:latest")
        assert result == "ollama/ollama:latest"


class TestGetEngineCompatibility:
    """Tests for per-engine platform compatibility reporting."""

    def test_arm64_marks_exllamav2_incompatible(self):
        result = get_engine_compatibility("arm64")
        assert result["exllamav2"]["compatible"] is False
        assert "reason" in result["exllamav2"]

    def test_arm64_marks_vllm_compatible(self):
        result = get_engine_compatibility("arm64")
        assert result["vllm"]["compatible"] is True

    def test_arm64_marks_llama_cpp_compatible(self):
        result = get_engine_compatibility("arm64")
        assert result["llama_cpp"]["compatible"] is True

    def test_arm64_marks_ollama_compatible(self):
        result = get_engine_compatibility("arm64")
        assert result["ollama"]["compatible"] is True

    def test_amd64_all_compatible(self):
        """All engines should be compatible on x86_64."""
        result = get_engine_compatibility("amd64")
        for engine_name, info in result.items():
            assert info["compatible"] is True, (
                f"{engine_name} should be compatible on amd64"
            )

    def test_x86_64_normalized_to_amd64(self):
        """Kernel convention 'x86_64' should be normalized and all engines compatible."""
        result = get_engine_compatibility("x86_64")
        for engine_name, info in result.items():
            assert info["compatible"] is True, (
                f"{engine_name} should be compatible on x86_64"
            )

    def test_aarch64_normalized_to_arm64(self):
        """Kernel convention 'aarch64' should be normalized to arm64."""
        result = get_engine_compatibility("aarch64")
        assert result["exllamav2"]["compatible"] is False
        assert result["vllm"]["compatible"] is True

    def test_empty_arch_all_compatible(self):
        """Empty arch string should treat all engines as compatible."""
        result = get_engine_compatibility("")
        for engine_name, info in result.items():
            assert info["compatible"] is True, (
                f"{engine_name} should be compatible with empty arch"
            )

    def test_unknown_arch_all_compatible(self):
        """Unknown arch should treat all engines as compatible."""
        result = get_engine_compatibility("riscv64")
        for engine_name, info in result.items():
            assert info["compatible"] is True, (
                f"{engine_name} should be compatible on riscv64"
            )

    def test_returns_all_override_engines(self):
        """Result should include all engines from _IMAGE_OVERRIDES."""
        result = get_engine_compatibility("amd64")
        assert "vllm" in result
        assert "llama_cpp" in result
        assert "ollama" in result
        assert "exllamav2" in result
