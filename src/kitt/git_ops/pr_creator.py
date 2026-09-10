"""GitHub pull request creation for results submission."""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PRCreator:
    """Create GitHub pull requests for results."""

    @staticmethod
    def check_git_config() -> bool:
        """Check if Git is properly configured."""
        try:
            subprocess.run(
                ["git", "config", "user.name"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.email"],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def check_github_cli() -> bool:
        """Check if GitHub CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                check=True,
                capture_output=True,
                text=True,
            )
            return "Logged in" in result.stderr
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def create_pr(
        repo_path: Path,
        title: str,
        description: str,
        upstream_repo: str,
    ) -> str | None:
        """Create pull request for results.

        Args:
            repo_path: Path to results repository.
            title: PR title.
            description: PR description.
            upstream_repo: Upstream repo (e.g., 'user/karr-dgx-spark').

        Returns:
            PR URL if successful, None otherwise.
        """
        if PRCreator.check_github_cli():
            return PRCreator._create_pr_with_gh(
                repo_path, title, description, upstream_repo
            )

        logger.info(
            "GitHub CLI not available. "
            "Install from https://cli.github.com/ for automated PR creation."
        )
        return None

    @staticmethod
    def _create_pr_with_gh(
        repo_path: Path,
        title: str,
        description: str,
        upstream_repo: str,
    ) -> str | None:
        """Create PR using GitHub CLI."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    title,
                    "--body",
                    description,
                    "--repo",
                    upstream_repo,
                ],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create PR: {e.stderr}")
            return None
