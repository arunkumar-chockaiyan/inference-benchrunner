from .base import InferenceEngineDriver, PromptParams, ResponseMeta, SpawnResult
from .llamacpp import LlamaCppDriver
from .ollama import OllamaDriver
from .sglang import SGLangDriver
from .vllm import VllmDriver

DRIVERS: dict[str, type[InferenceEngineDriver]] = {
    "ollama": OllamaDriver,
    "llamacpp": LlamaCppDriver,
    "vllm": VllmDriver,
    "sglang": SGLangDriver,
}


def get_driver_class(engine: str) -> type[InferenceEngineDriver]:
    if engine not in DRIVERS:
        raise ValueError(f"Unknown engine: {engine!r}. Valid: {list(DRIVERS)}")
    return DRIVERS[engine]


def get_driver(engine: str) -> InferenceEngineDriver:
    return get_driver_class(engine)()


__all__ = [
    "InferenceEngineDriver",
    "PromptParams",
    "ResponseMeta",
    "SpawnResult",
    "DRIVERS",
    "get_driver_class",
    "get_driver",
]
