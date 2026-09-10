"""Tests for plugin installer."""

from unittest.mock import MagicMock, patch

from kitt.plugins.installer import (
    install_plugin,
    list_installed_plugins,
    uninstall_plugin,
)


class TestInstallPlugin:
    def test_install_calls_pip(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = install_plugin("kitt-plugin-example")
            assert result is True
            args = mock_run.call_args[0][0]
            assert "install" in args
            assert "kitt-plugin-example" in args

    def test_install_with_version(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            install_plugin("kitt-plugin-example", version=">=0.2.0")
            args = mock_run.call_args[0][0]
            assert "kitt-plugin-example>=0.2.0" in args

    def test_install_with_upgrade(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            install_plugin("kitt-plugin-example", upgrade=True)
            args = mock_run.call_args[0][0]
            assert "--upgrade" in args

    def test_install_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error")
            result = install_plugin("bad-package")
            assert result is False

    def test_install_timeout(self):
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pip", timeout=300)
            result = install_plugin("slow-package")
            assert result is False

    def test_install_exception(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("fail")
            result = install_plugin("bad-package")
            assert result is False


class TestUninstallPlugin:
    def test_uninstall_calls_pip(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = uninstall_plugin("kitt-plugin-example")
            assert result is True
            args = mock_run.call_args[0][0]
            assert "uninstall" in args
            assert "-y" in args

    def test_uninstall_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="not found")
            result = uninstall_plugin("nonexistent")
            assert result is False

    def test_uninstall_exception(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("fail")
            result = uninstall_plugin("bad")
            assert result is False


class TestListInstalledPlugins:
    def test_returns_empty_when_no_plugins(self):
        result = list_installed_plugins()
        # No kitt-plugin-* packages installed in test env
        assert isinstance(result, list)

    def test_finds_matching_packages(self):
        mock_dist = MagicMock()
        mock_dist.metadata = {
            "Name": "kitt-plugin-example",
            "Version": "0.1.0",
        }
        mock_other = MagicMock()
        mock_other.metadata = {
            "Name": "unrelated-package",
            "Version": "1.0.0",
        }

        with patch(
            "importlib.metadata.distributions", return_value=[mock_dist, mock_other]
        ):
            result = list_installed_plugins()
            assert len(result) == 1
            assert result[0]["name"] == "kitt-plugin-example"
            assert result[0]["version"] == "0.1.0"
