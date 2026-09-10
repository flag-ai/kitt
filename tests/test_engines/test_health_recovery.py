"""Tests for engine health recovery."""

from unittest.mock import MagicMock, patch

import pytest

from kitt.engines.health_recovery import HealthRecoveryManager


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.health_endpoint.return_value = "/health"
    engine._base_url = "http://localhost:8000"
    return engine


@pytest.fixture
def recovery(mock_engine):
    return HealthRecoveryManager(
        engine=mock_engine,
        model_path="/models/test",
        config={},
        max_retries=2,
    )


class TestHealthRecovery:
    def test_successful_generation(self, recovery, mock_engine):
        result = MagicMock()
        mock_engine.generate.return_value = result

        output = recovery.generate_with_recovery("test prompt")
        assert output == result
        assert recovery.retry_count == 0

    def test_retries_on_failure(self, recovery, mock_engine):
        mock_engine.generate.side_effect = [
            RuntimeError("Connection refused"),
            MagicMock(),  # Succeeds on second try
        ]
        mock_engine.initialize.return_value = None

        result = recovery.generate_with_recovery("test prompt")
        assert result is not None
        assert mock_engine.generate.call_count == 2
        assert mock_engine.cleanup.call_count == 1
        assert mock_engine.initialize.call_count == 1

    def test_max_retries_exhausted(self, recovery, mock_engine):
        mock_engine.generate.side_effect = RuntimeError("Always fails")
        mock_engine.initialize.return_value = None

        with pytest.raises(RuntimeError, match="failed after 3 attempts"):
            recovery.generate_with_recovery("test prompt")

        assert mock_engine.generate.call_count == 3  # Initial + 2 retries

    def test_recovery_restarts_container(self, recovery, mock_engine):
        mock_engine.generate.side_effect = [
            RuntimeError("OOM"),
            MagicMock(),
        ]
        mock_engine.initialize.return_value = None

        recovery.generate_with_recovery("test prompt")

        mock_engine.cleanup.assert_called_once()
        mock_engine.initialize.assert_called_once_with("/models/test", {})

    def test_retry_count_resets_on_success(self, recovery, mock_engine):
        mock_engine.generate.side_effect = [
            RuntimeError("fail"),
            MagicMock(),
        ]
        mock_engine.initialize.return_value = None

        recovery.generate_with_recovery("test prompt")
        assert recovery.retry_count == 0  # Reset on success

    def test_check_health(self, recovery):
        with patch("urllib.request.urlopen") as mock:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock.return_value = mock_resp

            assert recovery.check_health() is True

    def test_check_health_failure(self, recovery):
        import urllib.error

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            assert recovery.check_health() is False
