"""Tests for engine registry."""

import pytest

from kitt.engines.base import InferenceEngine
from kitt.engines.registry import EngineRegistry, register_engine


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before each test."""
    EngineRegistry.clear()
    yield
    EngineRegistry.clear()


def _make_engine(engine_name: str, available: bool = True):
    """Create a minimal test engine class."""

    class TestEngine(InferenceEngine):
        _available = available

        @classmethod
        def name(cls):
            return engine_name

        @classmethod
        def supported_formats(cls):
            return ["test"]

        @classmethod
        def default_image(cls):
            return "test:latest"

        @classmethod
        def default_port(cls):
            return 8000

        @classmethod
        def container_port(cls):
            return 8000

        @classmethod
        def health_endpoint(cls):
            return "/health"

        @classmethod
        def is_available(cls):
            return cls._available

        def initialize(self, model_path, config):
            pass

        def generate(self, prompt, **kwargs):
            pass

        def cleanup(self):
            pass

    return TestEngine


class TestEngineRegistry:
    def test_register_and_get(self):
        engine_cls = _make_engine("test_engine")
        EngineRegistry.register(engine_cls)
        assert EngineRegistry.get_engine("test_engine") is engine_cls

    def test_get_unknown_engine(self):
        with pytest.raises(ValueError, match="not found"):
            EngineRegistry.get_engine("nonexistent")

    def test_list_all(self):
        EngineRegistry.register(_make_engine("a"))
        EngineRegistry.register(_make_engine("b"))
        assert sorted(EngineRegistry.list_all()) == ["a", "b"]

    def test_list_available(self):
        EngineRegistry.register(_make_engine("available", available=True))
        EngineRegistry.register(_make_engine("unavailable", available=False))
        assert EngineRegistry.list_available() == ["available"]

    def test_clear(self):
        EngineRegistry.register(_make_engine("a"))
        EngineRegistry.clear()
        assert EngineRegistry.list_all() == []


class TestRegisterDecorator:
    def test_decorator_registers(self):
        @register_engine
        class DecoratedEngine(InferenceEngine):
            @classmethod
            def name(cls):
                return "decorated"

            @classmethod
            def supported_formats(cls):
                return ["test"]

            @classmethod
            def default_image(cls):
                return "test:latest"

            @classmethod
            def default_port(cls):
                return 8000

            @classmethod
            def container_port(cls):
                return 8000

            @classmethod
            def health_endpoint(cls):
                return "/health"

            def initialize(self, model_path, config):
                pass

            def generate(self, prompt, **kwargs):
                pass

            def cleanup(self):
                pass

        assert "decorated" in EngineRegistry.list_all()
        assert EngineRegistry.get_engine("decorated") is DecoratedEngine


class TestAutoDiscover:
    def test_auto_discover_loads_engines(self):
        EngineRegistry.auto_discover()
        all_engines = EngineRegistry.list_all()
        assert "vllm" in all_engines
        assert "llama_cpp" in all_engines
        assert "ollama" in all_engines
