"""Tests for KITT-managed Dockerfiles — validate files exist and contain expected content."""

from kitt.engines.image_resolver import _BUILD_RECIPES, get_build_recipe


class TestDockerfilesExist:
    def test_llama_cpp_dockerfile_exists(self):
        recipe = get_build_recipe("kitt/llama-cpp:spark")
        assert recipe is not None
        assert recipe.dockerfile_path.exists(), (
            f"Dockerfile not found: {recipe.dockerfile_path}"
        )

    def test_all_recipes_have_dockerfiles(self):
        """Every BuildRecipe must reference an existing Dockerfile."""
        for image, recipe in _BUILD_RECIPES.items():
            assert recipe.dockerfile_path.exists(), (
                f"Missing Dockerfile for {image}: {recipe.dockerfile_path}"
            )


class TestLlamaCppDockerfileSpark:
    def setup_method(self):
        recipe = get_build_recipe("kitt/llama-cpp:spark")
        self.content = recipe.dockerfile_path.read_text()

    def test_uses_cuda_13(self):
        assert "CUDA_VERSION=13" in self.content

    def test_targets_sm_121(self):
        assert "CMAKE_CUDA_ARCHITECTURES=121" in self.content

    def test_has_multi_stage_build(self):
        assert "AS build" in self.content
        assert "AS server" in self.content

    def test_builds_llama_server(self):
        assert "llama-server" in self.content

    def test_clones_llama_cpp(self):
        assert "git clone" in self.content
        assert "llama.cpp" in self.content

    def test_enables_ggml_cuda(self):
        assert "GGML_CUDA=ON" in self.content

    def test_enables_native(self):
        assert "GGML_NATIVE=ON" in self.content
