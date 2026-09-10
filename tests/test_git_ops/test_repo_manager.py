"""Tests for KARR repo manager."""

from kitt.git_ops.repo_manager import KARRRepoManager


class TestKARRRepoManager:
    def test_create_results_repo(self, tmp_path):
        repo_path = tmp_path / "karr-test"
        fingerprint = "TestGPU-8GB_TestCPU-4c_16GB-DDR4"

        repo = KARRRepoManager.create_results_repo(repo_path, fingerprint)

        # Check repo was created
        assert (repo_path / ".git").exists()

        # Check files were created
        assert (repo_path / ".gitattributes").exists()
        assert (repo_path / ".gitignore").exists()
        assert (repo_path / "README.md").exists()
        assert (repo_path / "hardware_fingerprint.txt").exists()

        # Check fingerprint content
        assert (repo_path / "hardware_fingerprint.txt").read_text() == fingerprint

        # Check README contains KARR branding
        readme = (repo_path / "README.md").read_text()
        assert "KARR" in readme
        assert fingerprint in readme

        # Check gitattributes has LFS rules
        attrs = (repo_path / ".gitattributes").read_text()
        assert "*.jsonl.gz" in attrs
        assert "filter=lfs" in attrs

        # Check initial commit exists
        assert len(list(repo.iter_commits())) == 1

    def test_store_results(self, tmp_path):
        repo_path = tmp_path / "karr-store"
        KARRRepoManager.create_results_repo(repo_path, "test-fp")

        KARRRepoManager.store_results(
            repo_path=repo_path,
            model_name="llama-7b",
            engine_name="vllm",
            timestamp="2025-01-01_120000",
            files={
                "metrics.json": '{"tps": 50}',
                "summary.md": "# Results\nPassed",
            },
        )

        result_dir = repo_path / "llama-7b" / "vllm" / "2025-01-01_120000"
        assert result_dir.exists()
        assert (result_dir / "metrics.json").exists()
        assert (result_dir / "summary.md").exists()

    def test_find_results_repo_not_found(self):
        result = KARRRepoManager.find_results_repo("nonexistent-fingerprint")
        assert result is None
