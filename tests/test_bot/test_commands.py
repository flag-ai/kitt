"""Tests for bot command handler."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.bot.commands import BotCommandHandler


@pytest.fixture
def mock_store():
    return MagicMock()


@pytest.fixture
def handler(mock_store):
    return BotCommandHandler(result_store=mock_store)


@pytest.fixture
def handler_no_store():
    return BotCommandHandler(result_store=None)


class TestHandleStatus:
    @patch("kitt.bot.commands.CampaignStateManager", create=True)
    def test_with_campaigns_found(self, mock_mgr_cls, handler):
        mock_mgr = MagicMock()
        mock_mgr.list_campaigns.return_value = [
            {
                "campaign_name": "nightly-bench",
                "status": "completed",
                "total_runs": 10,
                "succeeded": 8,
                "failed": 2,
            },
        ]

        with (
            patch(
                "kitt.campaign.state_manager.CampaignStateManager",
                return_value=mock_mgr,
            ),
            patch.dict(
                "sys.modules",
                {
                    "kitt.campaign.state_manager": MagicMock(
                        CampaignStateManager=MagicMock(return_value=mock_mgr)
                    ),
                },
            ),
        ):
            result = handler.handle_status()

        assert "nightly-bench" in result
        assert "completed" in result

    @patch("kitt.bot.commands.CampaignStateManager", create=True)
    def test_with_no_campaigns(self, mock_mgr_cls, handler):
        mock_mgr = MagicMock()
        mock_mgr.list_campaigns.return_value = []

        with patch.dict(
            "sys.modules",
            {
                "kitt.campaign.state_manager": MagicMock(
                    CampaignStateManager=MagicMock(return_value=mock_mgr)
                ),
            },
        ):
            result = handler.handle_status()

        assert "No campaigns found." in result

    def test_with_error(self, handler):
        with patch.dict(
            "sys.modules",
            {
                "kitt.campaign.state_manager": None,
            },
        ):
            result = handler.handle_status()
            assert "Error getting status:" in result


class TestHandleResults:
    def test_with_results(self, handler, mock_store):
        mock_store.query.return_value = [
            {
                "model": "llama-8b",
                "engine": "vllm",
                "passed": True,
                "timestamp": "2024-01-15T12:00:00Z",
            },
        ]
        result = handler.handle_results()
        assert "Recent results (1):" in result
        assert "llama-8b" in result
        assert "vllm" in result
        assert "PASS" in result

    def test_with_no_results(self, handler, mock_store):
        mock_store.query.return_value = []
        result = handler.handle_results()
        assert "No results found." in result

    def test_with_no_store(self, handler_no_store):
        result = handler_no_store.handle_results()
        assert result == "No storage backend configured."

    def test_with_filters(self, handler, mock_store):
        mock_store.query.return_value = [
            {
                "model": "llama-8b",
                "engine": "vllm",
                "passed": True,
                "timestamp": "2024-01-15T12:00:00Z",
            },
        ]
        handler.handle_results(model="llama-8b", engine="vllm")
        call_kwargs = mock_store.query.call_args[1]
        assert call_kwargs["filters"]["model"] == "llama-8b"
        assert call_kwargs["filters"]["engine"] == "vllm"

    def test_with_error(self, handler, mock_store):
        mock_store.query.side_effect = Exception("DB error")
        result = handler.handle_results()
        assert "Error querying results:" in result


class TestHandleCompare:
    def test_with_two_results(self, handler, mock_store):
        mock_store.query.return_value = [
            {
                "model": "llama-8b",
                "engine": "vllm",
                "passed": True,
                "timestamp": "2024-01-16T00:00:00Z",
            },
            {
                "model": "llama-8b",
                "engine": "vllm",
                "passed": False,
                "timestamp": "2024-01-15T00:00:00Z",
            },
        ]
        result = handler.handle_compare("llama-8b", "vllm")
        assert "Comparison for llama-8b / vllm:" in result
        assert "FAIL -> PASS" in result

    def test_with_less_than_two_results(self, handler, mock_store):
        mock_store.query.return_value = [
            {
                "model": "llama-8b",
                "engine": "vllm",
                "passed": True,
                "timestamp": "2024-01-15T00:00:00Z",
            },
        ]
        result = handler.handle_compare("llama-8b", "vllm")
        assert "Need at least 2 runs to compare." in result

    def test_with_no_store(self, handler_no_store):
        result = handler_no_store.handle_compare("llama-8b", "vllm")
        assert result == "No storage backend configured."


class TestHandleHelp:
    def test_returns_help_text(self, handler):
        result = handler.handle_help()
        assert "KITT Bot Commands:" in result
        assert "/kitt status" in result
        assert "/kitt results" in result
        assert "/kitt compare" in result
        assert "/kitt help" in result
