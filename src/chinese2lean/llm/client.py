from typing import Protocol

from chinese2lean.llm.schemas import LeanCandidate


class OptionalLLMClient(Protocol):
    def propose_repair(self, prompt: str) -> LeanCandidate: ...


class DisabledLLMClient:
    def propose_repair(self, prompt: str) -> LeanCandidate:
        raise RuntimeError("LLM 修复未启用；核心流水线保持离线可用。")
