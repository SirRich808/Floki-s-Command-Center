from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    # NoDecode: skip pydantic-settings' default JSON parsing so "1,2,3" works
    # instead of requiring "[1,2,3]". The field_validator below splits on comma.
    allowed_chat_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_CHAT_IDS"
    )
    dashboard_tunnel_url: str = Field(default="", alias="DASHBOARD_TUNNEL_URL")
    pin_hash: str = Field(default="", alias="PIN_HASH")

    queue_db_path: Path = Field(default=ROOT / "data" / "queue.db", alias="QUEUE_DB_PATH")
    dispatch_poll_interval: float = Field(default=0.25, alias="DISPATCH_POLL_INTERVAL")
    dispatch_max_retries: int = Field(default=3, alias="DISPATCH_MAX_RETRIES")

    dashboard_host: str = Field(default="127.0.0.1", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8787, alias="DASHBOARD_PORT")
    pipecat_ws_secret: str = Field(default="", alias="PIPECAT_WS_SECRET")
    daily_room_url: str = Field(default="", alias="DAILY_ROOM_URL")

    obsidian_root: Path | None = Field(default=None, alias="OBSIDIAN_ROOT")
    washer_interval: int = Field(default=60, alias="WASHER_INTERVAL")  # seconds

    @field_validator("allowed_chat_ids", mode="before")
    @classmethod
    def _split_ids(cls, v: object) -> list[int]:
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []

    @field_validator("queue_db_path", mode="before")
    @classmethod
    def _resolve_path(cls, v: object) -> Path:
        p = Path(str(v))
        return p if p.is_absolute() else ROOT / p

    @field_validator("obsidian_root", mode="before")
    @classmethod
    def _optional_path(cls, v: object) -> Path | None:
        if v in (None, "", b""):
            return None
        return Path(str(v)).expanduser()


@lru_cache
def settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


@lru_cache
def agents_config() -> dict:
    with open(ROOT / "config" / "agents.yaml") as f:
        return yaml.safe_load(f)
