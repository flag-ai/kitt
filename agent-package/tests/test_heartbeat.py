"""Tests for HeartbeatThread — re-registration on 404 and ID sync."""

import json
from unittest.mock import MagicMock, patch

import pytest
from kitt_agent.heartbeat import HeartbeatThread


class TestHeartbeatReRegistration:
    def test_404_triggers_register_fn(self):
        """When heartbeat gets 404, register_fn is called."""
        register_fn = MagicMock(return_value="new-uuid-123")
        on_agent_id_change = MagicMock()

        hb = HeartbeatThread(
            server_url="http://localhost:9999",
            agent_id="old-hostname",
            token="test-token",
            register_fn=register_fn,
            on_agent_id_change=on_agent_id_change,
        )

        # Mock the HTTP call to return 404 then succeed on retry
        from urllib.error import HTTPError

        call_count = 0

        def mock_urlopen(req, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise HTTPError(req.full_url, 404, "Not Found", {}, None)
            # Second call (after re-registration) succeeds
            resp = MagicMock()
            resp.read.return_value = json.dumps(
                {"ack": True, "agent_id": "new-uuid-123", "commands": []}
            ).encode()
            resp.__enter__ = lambda s: resp
            resp.__exit__ = lambda s, *a: None
            return resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            result = hb._send_heartbeat()

        register_fn.assert_called_once()
        assert hb.agent_id == "new-uuid-123"
        assert result["ack"] is True

    def test_404_without_register_fn_raises(self):
        """When heartbeat gets 404 with no register_fn, exception propagates."""
        hb = HeartbeatThread(
            server_url="http://localhost:9999",
            agent_id="old-hostname",
            token="test-token",
        )

        from urllib.error import HTTPError

        def mock_urlopen(req, **kwargs):
            raise HTTPError(req.full_url, 404, "Not Found", {}, None)

        with (
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
            pytest.raises(HTTPError),
        ):
            hb._send_heartbeat()


class TestHeartbeatIdSync:
    def test_syncs_canonical_id(self):
        """Heartbeat syncs agent_id from server response."""
        on_agent_id_change = MagicMock()

        hb = HeartbeatThread(
            server_url="http://localhost:9999",
            agent_id="hostname-id",
            token="test-token",
            on_agent_id_change=on_agent_id_change,
        )

        resp_data = json.dumps(
            {"ack": True, "agent_id": "real-uuid-456", "commands": []}
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            hb._send_heartbeat()

        assert hb.agent_id == "real-uuid-456"
        on_agent_id_change.assert_called_once_with("real-uuid-456")

    def test_no_sync_when_id_matches(self):
        """No sync callback when server returns same agent_id."""
        on_agent_id_change = MagicMock()

        hb = HeartbeatThread(
            server_url="http://localhost:9999",
            agent_id="correct-uuid",
            token="test-token",
            on_agent_id_change=on_agent_id_change,
        )

        resp_data = json.dumps(
            {"ack": True, "agent_id": "correct-uuid", "commands": []}
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = resp_data
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = lambda s, *a: None

        with patch("urllib.request.urlopen", return_value=mock_resp):
            hb._send_heartbeat()

        on_agent_id_change.assert_not_called()


class TestHeartbeatConstruction:
    def test_accepts_register_fn(self):
        fn = MagicMock()
        hb = HeartbeatThread(
            server_url="http://localhost:9999",
            agent_id="test",
            token="tok",
            register_fn=fn,
        )
        assert hb._register_fn is fn

    def test_default_no_register_fn(self):
        hb = HeartbeatThread(
            server_url="http://localhost:9999",
            agent_id="test",
            token="tok",
        )
        assert hb._register_fn is None
        assert hb._on_agent_id_change is None
