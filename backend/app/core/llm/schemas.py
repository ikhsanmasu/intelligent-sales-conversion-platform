from pydantic import BaseModel


class GenerateConfig(BaseModel):
    temperature: float = 1.0
    max_tokens: int | None = None
    top_p: float = 1.0
    stop: list[str] | None = None


class LLMResponse(BaseModel):
    text: str
    usage: dict
