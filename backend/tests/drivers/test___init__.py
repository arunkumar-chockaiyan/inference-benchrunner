# tests/drivers/test___init__.py
import pytest
from drivers import get_driver_class

def test_driver_registry():
    assert get_driver_class("ollama").__name__ == "OllamaDriver"
    assert get_driver_class("vllm").__name__ == "VllmDriver"
    assert get_driver_class("llamacpp").__name__ == "LlamaCppDriver"
    assert get_driver_class("sglang").__name__ == "SGLangDriver"

def test_driver_registry_unsupported():
    with pytest.raises(ValueError):
        get_driver_class("unknown-engine")
