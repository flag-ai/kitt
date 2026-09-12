"""Tests for RemoteSetup — all tests mock the SSHConnection."""

from unittest.mock import MagicMock

from kitt.remote.host_config import HostManager
from kitt.remote.setup import RemoteSetup
from kitt.remote.ssh_connection import SSHConnection


def _make_connection(**kwargs):
    """Create an SSHConnection with mocked internals."""
    conn = MagicMock(spec=SSHConnection)
    conn.host = kwargs.get("host", "gpu-server")
    conn.user = kwargs.get("user", "kitt")
    conn.ssh_key = kwargs.get("ssh_key")
    conn.port = kwargs.get("port", 22)
    conn.target = f"{conn.user}@{conn.host}" if conn.user else conn.host
    return conn


class TestCheckPrerequisites:
    def test_returns_checks_dict(self):
        conn = _make_connection()
        conn.check_connection.return_value = True
        conn.run_command.side_effect = [
            (0, "Python 3.10.12\n", ""),  # python3 --version
            (0, "Docker version 24.0.5\n", ""),  # docker --version
            (0, "NVIDIA A100, 81920\n", ""),  # nvidia-smi
            (0, "500G\n", ""),  # df
        ]
        setup = RemoteSetup(conn)
        checks = setup.check_prerequisites()
        assert checks["ssh"] is True
        assert checks["python"] is True
        assert checks["python_version"] == "Python 3.10.12"
        assert checks["docker"] is True
        assert checks["gpu"] is True
        assert checks["gpu_info"] == "NVIDIA A100, 81920"

    def test_ssh_failure_returns_early(self):
        conn = _make_connection()
        conn.check_connection.return_value = False
        setup = RemoteSetup(conn)
        checks = setup.check_prerequisites()
        assert checks["ssh"] is False
        assert "python" not in checks
        conn.run_command.assert_not_called()

    def test_detects_python(self):
        conn = _make_connection()
        conn.check_connection.return_value = True
        conn.run_command.side_effect = [
            (0, "Python 3.11.0\n", ""),  # python3
            (1, "", "not found"),  # docker
            (1, "", "not found"),  # nvidia-smi
            (1, "", ""),  # df
        ]
        setup = RemoteSetup(conn)
        checks = setup.check_prerequisites()
        assert checks["python"] is True
        assert checks["python_version"] == "Python 3.11.0"

    def test_detects_gpu(self):
        conn = _make_connection()
        conn.check_connection.return_value = True
        conn.run_command.side_effect = [
            (1, "", "not found"),  # python3
            (1, "", "not found"),  # docker
            (0, "RTX 4090, 24576\n", ""),  # nvidia-smi
            (0, "1000G\n", ""),  # df
        ]
        setup = RemoteSetup(conn)
        checks = setup.check_prerequisites()
        assert checks["gpu"] is True
        assert checks["gpu_info"] == "RTX 4090, 24576"


class TestInstallKitt:
    def test_pip_method(self):
        conn = _make_connection()
        conn.run_command.return_value = (0, "", "")
        setup = RemoteSetup(conn)
        result = setup.install_kitt(method="pip")
        assert result is True
        cmd = conn.run_command.call_args[0][0]
        assert "pip install" in cmd
        assert "kitt-llm" in cmd

    def test_clone_method(self):
        conn = _make_connection()
        conn.run_command.return_value = (0, "", "")
        setup = RemoteSetup(conn)
        result = setup.install_kitt(method="clone")
        assert result is True
        cmd = conn.run_command.call_args[0][0]
        assert "git clone" in cmd
        assert "poetry install" in cmd

    def test_install_failure(self):
        conn = _make_connection()
        conn.run_command.return_value = (1, "", "pip error")
        setup = RemoteSetup(conn)
        result = setup.install_kitt(method="pip")
        assert result is False

    def test_unknown_method(self):
        conn = _make_connection()
        setup = RemoteSetup(conn)
        result = setup.install_kitt(method="unknown")
        assert result is False


class TestVerifyKitt:
    def test_returns_version(self):
        conn = _make_connection()
        conn.run_command.return_value = (0, "kitt 0.5.0\n", "")
        setup = RemoteSetup(conn)
        version = setup.verify_kitt()
        assert version == "kitt 0.5.0"

    def test_returns_none_when_not_installed(self):
        conn = _make_connection()
        conn.run_command.return_value = (1, "", "command not found")
        setup = RemoteSetup(conn)
        version = setup.verify_kitt()
        assert version is None


class TestSetupHost:
    def test_creates_config(self, tmp_path):
        conn = _make_connection()
        conn.check_connection.return_value = True
        # check_prerequisites run_command calls
        conn.run_command.side_effect = [
            (0, "Python 3.10.12\n", ""),  # python3 --version
            (0, "Docker 24.0.5\n", ""),  # docker --version
            (0, "A100, 81920\n", ""),  # nvidia-smi (prereqs)
            (0, "500G\n", ""),  # df
            (0, "kitt 0.5.0\n", ""),  # verify_kitt
            (0, "a100-80gb_fingerprint\n", ""),  # kitt fingerprint (detect_hardware)
            (0, "A100, 81920\n", ""),  # nvidia-smi (detect_hardware)
        ]
        hosts_file = tmp_path / "hosts.yaml"
        hm = HostManager(hosts_path=hosts_file)
        setup = RemoteSetup(conn)
        config = setup.setup_host("dgx01", host_manager=hm)
        assert config is not None
        assert config.name == "dgx01"
        assert config.hostname == "gpu-server"
        assert config.user == "kitt"
        # Verify it was saved
        saved = hm.get("dgx01")
        assert saved is not None

    def test_fails_when_ssh_unavailable(self):
        conn = _make_connection()
        conn.check_connection.return_value = False
        setup = RemoteSetup(conn)
        result = setup.setup_host("dgx01")
        assert result is None


class TestSetupEngines:
    def test_single_engine_success(self):
        conn = _make_connection()
        conn.run_command.return_value = (0, "vllm ready.", "")
        setup = RemoteSetup(conn)
        results = setup.setup_engines(["vllm"])
        assert results == {"vllm": True}
        conn.run_command.assert_called_once_with("kitt engines setup vllm")

    def test_single_engine_failure(self):
        conn = _make_connection()
        conn.run_command.return_value = (1, "", "Docker not found")
        setup = RemoteSetup(conn)
        results = setup.setup_engines(["vllm"])
        assert results == {"vllm": False}

    def test_multiple_engines(self):
        conn = _make_connection()
        conn.run_command.side_effect = [
            (0, "ok", ""),
            (1, "", "error"),
            (0, "ok", ""),
        ]
        setup = RemoteSetup(conn)
        results = setup.setup_engines(["vllm", "tgi", "llama_cpp"])
        assert results == {"vllm": True, "tgi": False, "llama_cpp": True}
        assert conn.run_command.call_count == 3

    def test_dry_run_flag(self):
        conn = _make_connection()
        conn.run_command.return_value = (0, "would run: ...", "")
        setup = RemoteSetup(conn)
        results = setup.setup_engines(["vllm"], dry_run=True)
        assert results == {"vllm": True}
        conn.run_command.assert_called_once_with("kitt engines setup vllm --dry-run")

    def test_empty_list(self):
        conn = _make_connection()
        setup = RemoteSetup(conn)
        results = setup.setup_engines([])
        assert results == {}
        conn.run_command.assert_not_called()
