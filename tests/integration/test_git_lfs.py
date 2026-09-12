"""Integration test for Git LFS operations."""

import gzip
import subprocess

import pytest


@pytest.fixture
def lfs_available():
    """Check if Git LFS is available."""
    try:
        result = subprocess.run(
            ["git", "lfs", "version"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            pytest.skip("Git LFS not installed")
    except FileNotFoundError:
        pytest.skip("Git LFS not installed")


def test_git_lfs_workflow(lfs_available, tmp_path):
    """Integration test for Git LFS operations."""
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()

    # Initialize repo
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "lfs", "install"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create .gitattributes
    (repo_path / ".gitattributes").write_text(
        "*.gz filter=lfs diff=lfs merge=lfs -text\n"
    )

    # Create a large file (>1KB to verify LFS tracking)
    test_file = repo_path / "test.jsonl.gz"
    with gzip.open(test_file, "wt") as f:
        for i in range(10000):
            f.write(f'{{"line": {i}}}\n')

    # Add and commit
    subprocess.run(
        ["git", "add", ".gitattributes", "test.jsonl.gz"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Test LFS"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Verify it's tracked by LFS
    result = subprocess.run(
        ["git", "lfs", "ls-files"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    assert "test.jsonl.gz" in result.stdout, "File not tracked by LFS"


def test_karr_repo_with_lfs(lfs_available, tmp_path):
    """Test KARR repo creation includes working LFS setup."""
    from kitt.git_ops.repo_manager import KARRRepoManager

    repo_path = tmp_path / "karr-test-lfs"
    KARRRepoManager.create_results_repo(repo_path, "test-fingerprint")

    # Create a compressed test file
    test_file = repo_path / "test_results.jsonl.gz"
    with gzip.open(test_file, "wt") as f:
        for i in range(1000):
            f.write(f'{{"iteration": {i}, "tps": {50 + i * 0.1}}}\n')

    # Add via subprocess (GitPython's index.add bypasses LFS filters)
    subprocess.run(
        ["git", "add", "test_results.jsonl.gz"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test results"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Verify LFS tracking
    result = subprocess.run(
        ["git", "lfs", "ls-files"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    assert "test_results.jsonl.gz" in result.stdout
