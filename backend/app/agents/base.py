from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass, field

from app.core.llm.base import BaseLLM


@dataclass
class AgentResult:
    output: str
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    @abstractmethod
    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        ...

    @abstractmethod
    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        ...
