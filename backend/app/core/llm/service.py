from typing import Dict, Tuple

from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.providers.anthropic import AnthropicProvider
from app.core.llm.providers.google import GoogleProvider
from app.core.llm.providers.xai import XaiProvider
from app.core.llm.providers.openai import OpenAIProvider


PROVIDER_ALIASES = {
    "grok": "xai",
    "gemini": "google",
}

LLM_REGISTRY = {
    "openai": OpenAIProvider,
    "xai": XaiProvider,
    "google": GoogleProvider,
    "anthropic": AnthropicProvider,
}

PROVIDER_CONFIG: Dict[str, dict[str, str]] = {
    "openai": {
        "api_key_attr": "OPENAI_API_KEY",
    },
    "xai": {
        "api_key_attr": "XAI_API_KEY",
    },
    "google": {
        "api_key_attr": "GOOGLE_API_KEY",
    },
    "anthropic": {
        "api_key_attr": "ANTHROPIC_API_KEY",
    },
}

LLM_MODEL_REGISTRY: Dict[str, list[str]] = {
    "openai": [
        "gpt-5.2",
        "gpt-5.2-pro",
        "gpt-5.2-codex",
        "gpt-5.1",
        "gpt-5.1-codex",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex-max",
        "gpt-5",
        "gpt-5-pro",
        "gpt-5-codex",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "o3",
        "o3-mini",
        "o3-pro",
        "o4-mini",
        "gpt-4",
        "gpt-3.5-turbo",
        "codex-mini-latest",
    ],
    "xai": [
        "grok-4",
        "grok-4-fast-reasoning",
        "grok-4-fast-non-reasoning",
        "grok-4-1-fast-reasoning",
        "grok-4-1-fast-non-reasoning",
        "grok-code-fast-1",
        "grok-3",
        "grok-3-mini",
        "grok-3-latest",
        "grok-3-beta",
        "grok-3-fast",
        "grok-3-fast-latest",
        "grok-3-fast-beta",
        "grok-2-1212",
        "grok-2-vision-1212",
        "grok-beta",
        "grok-vision-beta",
    ],
    "google": [
        "gemini-3-pro-preview",
        "gemini-3-pro-image-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-lite-preview-09-2025",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash-lite-001",
    ],
    "anthropic": [
        "claude-opus-4-1-20250805",
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-3-7-sonnet-20250219",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-haiku-20241022",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-opus-latest",
        "claude-3-sonnet-20240229",
        "claude-opus-4-0",
        "claude-sonnet-4-0",
        "claude-3-7-sonnet-latest",
        "claude-3-5-sonnet-latest",
        "claude-3-5-haiku-latest",
    ],
}


def list_llm_options() -> dict[str, object]:
    providers = list(LLM_REGISTRY.keys())
    models = {provider: LLM_MODEL_REGISTRY.get(provider, []) for provider in providers}
    return {"providers": providers, "models": models}


# cache instance per (provider, model)
_instances: Dict[Tuple[str, str], BaseLLM] = {}


def _llm_key(group: str, key: str) -> str:
    if group == "llm":
        if key == "provider":
            return "default_provider"
        if key == "model":
            return "default_model"
    return key


def _resolve(group: str, key: str, fallback_attr: str) -> str:
    """Try admin config override first, fall back to settings."""
    try:
        from app.modules.admin.service import resolve_config
        resolved_key = _llm_key(group, key)
        val = resolve_config(group, resolved_key)
        if val:
            return val
        if group != "llm":
            val = resolve_config("llm", _llm_key("llm", key))
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




def create_llm(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    config_group: str = "llm",
    use_cache: bool = True,
) -> BaseLLM:

    provider = provider or _resolve(config_group, "provider", "CHATBOT_DEFAULT_LLM")
    provider = PROVIDER_ALIASES.get(provider, provider)
    model = model or _resolve(config_group, "model", "CHATBOT_DEFAULT_MODEL")
    api_key = api_key or _resolve_api_key(provider)

    if provider not in LLM_REGISTRY:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    if not api_key:
        attr = PROVIDER_CONFIG.get(provider, {}).get("api_key_attr", "")
        hint = f" Set {attr} in env." if attr else ""
        raise ValueError(f"Missing API key for provider '{provider}'.{hint}")
    key = (provider, model)

    if use_cache and key in _instances:
        return _instances[key]

    llm_class = LLM_REGISTRY[provider]

    instance = llm_class(
        api_key=api_key,
        model=model,
    )

    if use_cache:
        _instances[key] = instance

    return instance


def clear_llm_cache() -> None:
    """Clear cached LLM instances so next call picks up new config."""
    _instances.clear()
