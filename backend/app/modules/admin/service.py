"""Admin service — DB-backed config/prompt overrides with default fallback."""

from sqlmodel import Session, delete, select

from app.core.config import settings
from app.core.database import app_engine
from app.modules.admin.models import AdminConfig, PromptOverride
from app.modules.admin.seed import DEFAULT_CONFIGS, DEFAULT_PROMPTS

_PROMPT_FALLBACK: dict[str, dict[str, str]] = {p["slug"]: dict(p) for p in DEFAULT_PROMPTS}

_CONFIG_FALLBACK: dict[str, str] = {
    "llm:default_provider": "CHATBOT_DEFAULT_LLM",
    "llm:default_model": "CHATBOT_DEFAULT_MODEL",
    "app_db:url": "app_database_url",
}

SECRET_FIELDS = {"api_key", "password"}
BLOCKED_CONFIG_GROUPS: set[str] = set()


def _is_secret(field: str) -> bool:
    return field in SECRET_FIELDS


def _is_blocked_group(group: str) -> bool:
    return group in BLOCKED_CONFIG_GROUPS


def _purge_blocked_configs(session: Session) -> None:
    if not BLOCKED_CONFIG_GROUPS:
        return
    session.exec(
        delete(AdminConfig).where(AdminConfig.config_group.in_(BLOCKED_CONFIG_GROUPS))
    )


def _default_grouped_configs() -> dict[str, dict[str, str]]:
    grouped: dict[str, dict[str, str]] = {}
    for full_key, value in DEFAULT_CONFIGS.items():
        parts = full_key.split(":", 2)
        if len(parts) != 3 or parts[0] != "config":
            continue
        _, group, field = parts
        if _is_blocked_group(group):
            continue
        if _is_secret(field):
            continue
        grouped.setdefault(group, {})[field] = str(value)
    return grouped


def list_configs() -> dict[str, dict[str, str]]:
    grouped = _default_grouped_configs()
    with Session(app_engine) as session:
        _purge_blocked_configs(session)
        session.commit()
        overrides = session.exec(select(AdminConfig)).all()
        for item in overrides:
            if _is_blocked_group(item.config_group):
                continue
            if _is_secret(item.config_key):
                continue
            grouped.setdefault(item.config_group, {})[item.config_key] = item.value
    return grouped


def update_configs(updates: dict[str, dict[str, str]]) -> None:
    with Session(app_engine) as session:
        _purge_blocked_configs(session)
        for group, fields in updates.items():
            if _is_blocked_group(group):
                continue
            for field, value in fields.items():
                if _is_secret(field):
                    continue
                value = "" if value is None else str(value)

                existing = session.exec(
                    select(AdminConfig)
                    .where(AdminConfig.config_group == group)
                    .where(AdminConfig.config_key == field)
                ).first()

                if not existing:
                    existing = AdminConfig(
                        config_group=group,
                        config_key=field,
                        value=value,
                    )
                else:
                    existing.value = value

                session.add(existing)
        session.commit()


def resolve_config(group: str, key: str) -> str:
    if _is_blocked_group(group):
        return ""
    if _is_secret(key):
        attr = _CONFIG_FALLBACK.get(f"{group}:{key}")
        if attr:
            return str(getattr(settings, attr, ""))
        return ""

    with Session(app_engine) as session:
        existing = session.exec(
            select(AdminConfig)
            .where(AdminConfig.config_group == group)
            .where(AdminConfig.config_key == key)
        ).first()
        if existing:
            return existing.value

    full_key = f"config:{group}:{key}"
    if full_key in DEFAULT_CONFIGS:
        return str(DEFAULT_CONFIGS[full_key])

    attr = _CONFIG_FALLBACK.get(f"{group}:{key}")
    if attr:
        return str(getattr(settings, attr, ""))

    return ""


def list_prompts() -> list[dict[str, str]]:
    merged_by_slug: dict[str, dict[str, str]] = {
        slug: dict(prompt) for slug, prompt in _PROMPT_FALLBACK.items()
    }

    with Session(app_engine) as session:
        overrides = session.exec(select(PromptOverride)).all()
        for item in overrides:
            base = merged_by_slug.setdefault(item.slug, {"slug": item.slug})
            if item.name is not None:
                base["name"] = item.name
            if item.description is not None:
                base["description"] = item.description
            if item.content is not None:
                base["content"] = item.content

    ordered_prompts: list[dict[str, str]] = []
    seen = set()

    for prompt in DEFAULT_PROMPTS:
        slug = prompt["slug"]
        ordered_prompts.append(merged_by_slug[slug])
        seen.add(slug)

    for slug, prompt in merged_by_slug.items():
        if slug not in seen:
            ordered_prompts.append(prompt)

    return ordered_prompts


def update_prompt(slug: str, data: dict[str, str]) -> bool:
    with Session(app_engine) as session:
        existing = session.get(PromptOverride, slug)
        if slug not in _PROMPT_FALLBACK and not existing:
            return False

        if not existing:
            existing = PromptOverride(slug=slug)

        if "name" in data:
            existing.name = data["name"]
        if "description" in data:
            existing.description = data["description"]
        if "content" in data:
            existing.content = data["content"]

        session.add(existing)
        session.commit()
        return True


def reset_prompt(slug: str) -> bool:
    """Delete DB override so the seeder default becomes active again."""
    if slug not in _PROMPT_FALLBACK:
        return False
    with Session(app_engine) as session:
        existing = session.get(PromptOverride, slug)
        if existing:
            session.delete(existing)
            session.commit()
    return True


def resolve_prompt(slug: str) -> str:
    with Session(app_engine) as session:
        existing = session.get(PromptOverride, slug)
        if existing and existing.content is not None:
            return existing.content

    fallback = _PROMPT_FALLBACK.get(slug, {})
    return fallback.get("content", "")
