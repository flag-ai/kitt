"""Tests for HostConfig and HostManager — uses tmp_path for filesystem."""

from kitt.remote.host_config import HostConfig, HostManager


class TestHostConfig:
    def test_creation_with_defaults(self):
        config = HostConfig(name="dgx01", hostname="192.168.1.10")
        assert config.name == "dgx01"
        assert config.hostname == "192.168.1.10"
        assert config.user == ""
        assert config.ssh_key == ""
        assert config.port == 22
        assert config.kitt_path == "~/.local/bin/kitt"
        assert config.storage_path == "~/kitt-results"
        assert config.gpu_info == ""
        assert config.gpu_count == 0
        assert config.python_version == ""
        assert config.notes == ""

    def test_creation_with_all_fields(self):
        config = HostConfig(
            name="dgx01",
            hostname="192.168.1.10",
            user="kitt",
            ssh_key="/home/kitt/.ssh/id_rsa",
            port=2222,
            kitt_path="/usr/local/bin/kitt",
            storage_path="/data/kitt-results",
            gpu_info="NVIDIA A100, 81920",
            gpu_count=8,
            python_version="Python 3.10.12",
            notes="Production DGX",
        )
        assert config.user == "kitt"
        assert config.port == 2222
        assert config.gpu_count == 8


class TestHostManager:
    def test_default_hosts_path(self):
        manager = HostManager()
        assert str(manager.hosts_path).endswith(".kitt/hosts.yaml")

    def test_add_saves_to_yaml(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        config = HostConfig(name="dgx01", hostname="192.168.1.10", user="kitt")
        manager.add(config)
        assert hosts_file.exists()
        content = hosts_file.read_text()
        assert "dgx01" in content

    def test_get_returns_saved_config(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        config = HostConfig(
            name="dgx01", hostname="192.168.1.10", user="kitt", port=2222
        )
        manager.add(config)
        result = manager.get("dgx01")
        assert result is not None
        assert result.name == "dgx01"
        assert result.hostname == "192.168.1.10"
        assert result.user == "kitt"
        assert result.port == 2222

    def test_get_returns_none_for_missing(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        result = manager.get("nonexistent")
        assert result is None

    def test_remove_existing_host(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        config = HostConfig(name="dgx01", hostname="192.168.1.10")
        manager.add(config)
        assert manager.remove("dgx01") is True
        assert manager.get("dgx01") is None

    def test_remove_missing_host(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        assert manager.remove("nonexistent") is False

    def test_list_hosts_returns_all(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        manager.add(HostConfig(name="dgx01", hostname="192.168.1.10"))
        manager.add(HostConfig(name="dgx02", hostname="192.168.1.11"))
        hosts = manager.list_hosts()
        assert len(hosts) == 2
        names = {h.name for h in hosts}
        assert names == {"dgx01", "dgx02"}

    def test_list_hosts_empty(self, tmp_path):
        hosts_file = tmp_path / "hosts.yaml"
        manager = HostManager(hosts_path=hosts_file)
        assert manager.list_hosts() == []
