"""Tests for gated model checker."""

import json
from unittest.mock import MagicMock, patch

import pytest

from kitt.campaign.gated_model_checker import GatedModelChecker


@pytest.fixture
def checker():
    return GatedModelChecker()


@pytest.fixture
def checker_with_token():
    return GatedModelChecker(hf_token="hf_test_token")


class TestIsGated:
    def test_not_gated(self, checker):
        mock_response = json.dumps({"gated": False}).encode()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
                read=lambda: mock_response
            )
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            assert checker.is_gated("org/model") is False

    def test_gated_model(self, checker):
        mock_response = json.dumps({"gated": "auto"}).encode()
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: MagicMock(
                read=lambda: mock_response
            )
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)
            assert checker.is_gated("meta-llama/Llama-3.1-8B") is True

    def test_model_not_found(self, checker):
        import urllib.error

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="", code=404, msg="Not Found", hdrs=None, fp=None
            )
            assert checker.is_gated("nonexistent/model") is False

    def test_network_error(self, checker):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = Exception("Network error")
            assert checker.is_gated("org/model") is False


class TestCheckAccess:
    def test_ungated_model(self, checker):
        with patch.object(checker, "_fetch_model_info", return_value={"gated": False}):
            status = checker.check_access("org/model")
            assert status["gated"] is False
            assert status["accessible"] is True

    def test_gated_without_token(self, checker):
        with patch.object(checker, "_fetch_model_info", return_value={"gated": "auto"}):
            status = checker.check_access("org/model")
            assert status["gated"] is True
            assert status["accessible"] is False

    def test_gated_with_token(self, checker_with_token):
        with patch.object(
            checker_with_token, "_fetch_model_info", return_value={"gated": "auto"}
        ):
            status = checker_with_token.check_access("org/model")
            assert status["gated"] is True
            assert status["accessible"] is True

    def test_model_not_found(self, checker):
        with patch.object(checker, "_fetch_model_info", return_value=None):
            status = checker.check_access("nonexistent/model")
            assert status["accessible"] is False
            assert status["error"] is not None


class TestFilterAccessible:
    def test_all_accessible(self, checker):
        with patch.object(
            checker, "check_access", return_value={"accessible": True, "gated": False}
        ):
            accessible, inaccessible = checker.filter_accessible(["a", "b"])
            assert len(accessible) == 2
            assert len(inaccessible) == 0

    def test_some_inaccessible(self, checker):
        def mock_check(repo_id):
            if repo_id == "gated/model":
                return {"accessible": False, "gated": True}
            return {"accessible": True, "gated": False}

        with patch.object(checker, "check_access", side_effect=mock_check):
            accessible, inaccessible = checker.filter_accessible(
                ["open/model", "gated/model"]
            )
            assert accessible == ["open/model"]
            assert inaccessible == ["gated/model"]

    def test_empty_list(self, checker):
        accessible, inaccessible = checker.filter_accessible([])
        assert accessible == []
        assert inaccessible == []


class TestFetchModelInfo:
    def test_sends_auth_header(self, checker_with_token):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps({"gated": False}).encode()
            mock_urlopen.return_value.__enter__ = lambda s: mock_resp
            mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

            checker_with_token._fetch_model_info("org/model")

            req = mock_urlopen.call_args[0][0]
            assert "Authorization" in req.headers

    def test_handles_401(self, checker):
        import urllib.error

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = urllib.error.HTTPError(
                url="", code=401, msg="Unauthorized", hdrs=None, fp=None
            )
            result = checker._fetch_model_info("org/model")
            assert result is not None
            assert result.get("gated") is True

    def test_handles_timeout(self, checker):
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("timeout")
            result = checker._fetch_model_info("org/model")
            assert result is None
