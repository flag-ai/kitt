"""Tests for Devon connection configuration."""

import pytest
from pydantic import ValidationError

from kitt.devon.config import DevonConnectionConfig


class TestDevonConnectionConfig:
    def test_defaults(self):
        config = DevonConnectionConfig()
        assert config.url is None
        assert config.api_key is None
        assert config.timeout == 30.0
        assert config.download_timeout == 7200.0

    def test_with_url(self):
        config = DevonConnectionConfig(url="http://192.168.1.50:8000")
        assert config.url == "http://192.168.1.50:8000"

    def test_with_all_fields(self):
        config = DevonConnectionConfig(
            url="http://devon:8000",
            api_key="secret-token",
            timeout=60.0,
            download_timeout=3600.0,
        )
        assert config.url == "http://devon:8000"
        assert config.api_key == "secret-token"
        assert config.timeout == 60.0
        assert config.download_timeout == 3600.0

    def test_timeout_minimum(self):
        with pytest.raises(ValidationError):
            DevonConnectionConfig(timeout=0.5)

    def test_download_timeout_minimum(self):
        with pytest.raises(ValidationError):
            DevonConnectionConfig(download_timeout=10.0)
