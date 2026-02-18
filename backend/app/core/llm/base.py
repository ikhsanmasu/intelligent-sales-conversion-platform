from abc import ABC, abstractmethod
from collections.abc import Generator

from app.core.llm.schemas import GenerateConfig, LLMResponse


class BaseLLM(ABC):
    @abstractmethod
    def generate(self, messages: list[dict], config: GenerateConfig | None = None) -> LLMResponse:
        """Generate a response from the LLM based on the provided messages."""
        pass

    @abstractmethod
    def generate_stream(self, messages: list[dict], config: GenerateConfig | None = None) -> Generator[str, None, None]:
        """Stream response chunks from the LLM."""
        pass
