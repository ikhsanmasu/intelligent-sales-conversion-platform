from typing import Optional

from sqlmodel import Field, SQLModel, UniqueConstraint


class AdminConfig(SQLModel, table=True):
    __tablename__ = "admin_configs"
    __table_args__ = (UniqueConstraint("config_group", "config_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    config_group: str = Field(index=True)
    config_key: str = Field(index=True)
    value: str


class PromptOverride(SQLModel, table=True):
    __tablename__ = "admin_prompt_overrides"

    slug: str = Field(primary_key=True)
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
