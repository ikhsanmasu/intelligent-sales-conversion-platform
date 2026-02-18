from typing import Dict

from app.core.config import settings
from app.core.websearch.base import BaseWebSearch
from app.core.websearch.providers.serper import SerperSearch
from app.core.websearch.providers.tavily import TavilySearch

PROVIDER_ALIASES = {
    "google": "serper",
}

WEBSEARCH_REGISTRY = {
    "serper": SerperSearch,
    "tavily": TavilySearch,
}

PROVIDER_CONFIG: Dict[str, dict[str, str]] = {
    "serper": {
        "api_key_attr": "WEB_SEARCH_API_KEY",
        "url_attr": "WEB_SEARCH_API_URL",
    },
    "tavily": {
        "api_key_attr": "WEB_SEARCH_API_KEY",
        "url_attr": "WEB_SEARCH_API_URL",
    },
}


_instances: dict[str, BaseWebSearch] = {}


def list_websearch_options() -> dict[str, object]:
    providers = list(WEBSEARCH_REGISTRY.keys())
    return {"providers": providers}


def _resolve(group: str, key: str, fallback_attr: str) -> str:
    try:
        from app.modules.admin.service import resolve_config
        val = resolve_config(group, key)
        if val:
            return val
    except Exception:
        pass
    return str(getattr(settings, fallback_attr, ""))


def _resolve_api_key(provider: str) -> str:
    provider = PROVIDER_ALIASES.get(provider, provider)
    cfg = PROVIDER_CONFIG.get(provider, {})
    attr = cfg.get("api_key_attr", "")
    if attr:
        val = getattr(settings, attr, "")
        if val:
            return str(val)
    return ""


def create_websearch(
    provider: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    config_group: str = "websearch",
    use_cache: bool = True,
) -> BaseWebSearch:
    provider = provider or _resolve(config_group, "provider", "WEB_SEARCH_PROVIDER")
    provider = PROVIDER_ALIASES.get(provider, provider)

    if provider not in WEBSEARCH_REGISTRY:
        raise ValueError(f"Unsupported web search provider: {provider}")

    cfg = PROVIDER_CONFIG.get(provider, {})
    api_key = api_key or _resolve_api_key(provider)
    api_url = api_url or _resolve(config_group, "url", cfg.get("url_attr", "WEB_SEARCH_API_URL"))

    if use_cache and provider in _instances:
        return _instances[provider]

    if provider == "serper":
        instance = SerperSearch(api_key=api_key, api_url=api_url or None)
    elif provider == "tavily":
        instance = TavilySearch(api_key=api_key, api_url=api_url or None)
    else:
        raise ValueError(f"Unsupported web search provider: {provider}")

    if use_cache:
        _instances[provider] = instance

    return instance


def clear_websearch_cache() -> None:
    _instances.clear()
