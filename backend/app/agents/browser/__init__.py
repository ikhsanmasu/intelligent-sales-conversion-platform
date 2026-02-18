from app.agents.browser.agent import BrowserAgent
from app.core.llm import create_llm
from app.core.llm.base import BaseLLM


def create_browser_agent(llm: BaseLLM | None = None) -> BrowserAgent:
    return BrowserAgent(llm=llm or create_llm(config_group="llm_browser"))


__all__ = ["BrowserAgent", "create_browser_agent"]
