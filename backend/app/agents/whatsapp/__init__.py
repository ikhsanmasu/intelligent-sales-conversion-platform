from app.agents.whatsapp.agent import WhatsAppPolisherAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_whatsapp_polisher_agent(llm: BaseLLM | None = None) -> WhatsAppPolisherAgent:
    polisher_llm = llm or create_llm(config_group="llm_whatsapp")
    return WhatsAppPolisherAgent(llm=polisher_llm)


__all__ = ["WhatsAppPolisherAgent", "create_whatsapp_polisher_agent"]
