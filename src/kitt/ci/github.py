"""GitHub integration for posting CI results."""

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


class GitHubReporter:
    """Post benchmark results as GitHub PR comments."""

    def __init__(
        self,
        token: str,
        repo: str,
        pr_number: int | None = None,
    ) -> None:
        """Initialize GitHub reporter.

        Args:
            token: GitHub API token.
            repo: Repository in "owner/repo" format.
            pr_number: Pull request number (for PR comments).
        """
        self.token = token
        self.repo = repo
        self.pr_number = pr_number
        self.api_base = "https://api.github.com"

    def post_comment(self, body: str) -> bool:
        """Post a comment on the configured PR.

        Args:
            body: Markdown comment body.

        Returns:
            True if comment posted successfully.
        """
        if not self.pr_number:
            logger.error("No PR number configured")
            return False

        url = f"{self.api_base}/repos/{self.repo}/issues/{self.pr_number}/comments"
        return self._api_post(url, {"body": body})

    def post_check_result(
        self,
        name: str,
        conclusion: str,
        summary: str,
        details: str = "",
    ) -> bool:
        """Create a check run with results.

        Args:
            name: Check run name.
            conclusion: "success", "failure", or "neutral".
            summary: Short summary text.
            details: Detailed text (Markdown).

        Returns:
            True if check posted successfully.
        """
        url = f"{self.api_base}/repos/{self.repo}/check-runs"
        payload = {
            "name": name,
            "conclusion": conclusion,
            "output": {
                "title": name,
                "summary": summary,
                "text": details,
            },
        }
        return self._api_post(url, payload)

    def update_or_create_comment(
        self, body: str, marker: str = "<!-- kitt-benchmark -->"
    ) -> bool:
        """Update existing comment or create new one.

        Uses a hidden HTML marker to identify KITT comments.
        """
        if not self.pr_number:
            return False

        # Search for existing comment
        existing_id = self._find_comment(marker)
        if existing_id:
            url = f"{self.api_base}/repos/{self.repo}/issues/comments/{existing_id}"
            return self._api_patch(url, {"body": f"{marker}\n{body}"})
        else:
            return self.post_comment(f"{marker}\n{body}")

    def _find_comment(self, marker: str) -> int | None:
        """Find existing KITT comment on PR."""
        if not self.pr_number:
            return None

        url = f"{self.api_base}/repos/{self.repo}/issues/{self.pr_number}/comments"
        try:
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                comments = json.loads(resp.read().decode())
                for comment in comments:
                    if marker in comment.get("body", ""):
                        return comment["id"]
        except Exception as e:
            logger.debug(f"Error searching comments: {e}")

        return None

    def _api_post(self, url: str, payload: dict[str, Any]) -> bool:
        data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={**self._headers(), "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15):
                return True
        except Exception as e:
            logger.error(f"GitHub API POST failed: {e}")
            return False

    def _api_patch(self, url: str, payload: dict[str, Any]) -> bool:
        data = json.dumps(payload).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={**self._headers(), "Content-Type": "application/json"},
                method="PATCH",
            )
            with urllib.request.urlopen(req, timeout=15):
                return True
        except Exception as e:
            logger.error(f"GitHub API PATCH failed: {e}")
            return False

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
