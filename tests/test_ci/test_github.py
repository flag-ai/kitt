"""Tests for GitHub CI reporter."""

import json
from unittest.mock import MagicMock, patch

import pytest

from kitt.ci.github import GitHubReporter


@pytest.fixture
def reporter():
    return GitHubReporter(
        token="ghp_test_token",
        repo="owner/repo",
        pr_number=42,
    )


@pytest.fixture
def reporter_no_pr():
    return GitHubReporter(
        token="ghp_test_token",
        repo="owner/repo",
    )


class TestPostComment:
    @patch("urllib.request.urlopen")
    def test_success(self, mock_urlopen, reporter):
        mock_resp = MagicMock()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = reporter.post_comment("Test body")
        assert result is True
        mock_urlopen.assert_called_once()

        req = mock_urlopen.call_args[0][0]
        assert "/repos/owner/repo/issues/42/comments" in req.full_url
        assert req.method == "POST"
        payload = json.loads(req.data)
        assert payload["body"] == "Test body"

    def test_no_pr_number_returns_false(self, reporter_no_pr):
        result = reporter_no_pr.post_comment("Test body")
        assert result is False


class TestPostCheckResult:
    @patch("urllib.request.urlopen")
    def test_success(self, mock_urlopen, reporter):
        mock_resp = MagicMock()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = reporter.post_check_result(
            name="KITT Benchmark",
            conclusion="success",
            summary="All passed",
            details="Detailed results here",
        )
        assert result is True

        req = mock_urlopen.call_args[0][0]
        assert "/repos/owner/repo/check-runs" in req.full_url
        payload = json.loads(req.data)
        assert payload["name"] == "KITT Benchmark"
        assert payload["conclusion"] == "success"
        assert payload["output"]["summary"] == "All passed"
        assert payload["output"]["text"] == "Detailed results here"


class TestUpdateOrCreateComment:
    @patch("urllib.request.urlopen")
    def test_creates_new_when_no_existing(self, mock_urlopen, reporter):
        # First call: _find_comment GET returns empty list
        mock_find_resp = MagicMock()
        mock_find_resp.read.return_value = b"[]"

        # Second call: post_comment POST succeeds
        mock_post_resp = MagicMock()

        mock_urlopen.return_value.__enter__ = MagicMock(
            side_effect=[mock_find_resp, mock_post_resp]
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = reporter.update_or_create_comment("New results")
        assert result is True

    @patch("urllib.request.urlopen")
    def test_updates_existing(self, mock_urlopen, reporter):
        # First call: _find_comment GET returns comment with marker
        comments = [{"id": 999, "body": "<!-- kitt-benchmark -->\nold results"}]
        mock_find_resp = MagicMock()
        mock_find_resp.read.return_value = json.dumps(comments).encode()

        # Second call: _api_patch succeeds
        mock_patch_resp = MagicMock()

        mock_urlopen.return_value.__enter__ = MagicMock(
            side_effect=[mock_find_resp, mock_patch_resp]
        )
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = reporter.update_or_create_comment("Updated results")
        assert result is True

        # Verify the PATCH call
        calls = mock_urlopen.call_args_list
        assert len(calls) == 2
        patch_req = calls[1][0][0]
        assert patch_req.method == "PATCH"
        assert "/issues/comments/999" in patch_req.full_url


class TestFindComment:
    @patch("urllib.request.urlopen")
    def test_returns_id_when_found(self, mock_urlopen, reporter):
        comments = [
            {"id": 100, "body": "unrelated comment"},
            {"id": 200, "body": "<!-- kitt-benchmark -->\nbenchmark results"},
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(comments).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = reporter._find_comment("<!-- kitt-benchmark -->")
        assert result == 200

    @patch("urllib.request.urlopen")
    def test_returns_none_when_not_found(self, mock_urlopen, reporter):
        comments = [
            {"id": 100, "body": "unrelated comment"},
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(comments).encode()
        mock_urlopen.return_value.__enter__ = MagicMock(return_value=mock_resp)
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        result = reporter._find_comment("<!-- kitt-benchmark -->")
        assert result is None

    def test_returns_none_when_no_pr(self, reporter_no_pr):
        result = reporter_no_pr._find_comment("<!-- kitt-benchmark -->")
        assert result is None


class TestApiPost:
    @patch("urllib.request.urlopen", side_effect=Exception("Network error"))
    def test_handles_exception_returns_false(self, mock_urlopen, reporter):
        result = reporter._api_post(
            "https://api.github.com/test",
            {"key": "value"},
        )
        assert result is False
