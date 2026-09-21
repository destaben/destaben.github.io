from dataclasses import dataclass
import json
from pathlib import Path
import os
import re


_PUBLIC_NODE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}")


def _public_tcp_node_aliases(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        aliases = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES must be JSON") from error
    if not isinstance(aliases, dict) or len(aliases) > 12:
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES must contain at most 12 aliases")
    if not all(isinstance(name, str) and isinstance(alias, str) and _PUBLIC_NODE_ALIAS.fullmatch(alias) for name, alias in aliases.items()):
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES contains an invalid alias")
    if len(set(aliases.values())) != len(aliases):
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES aliases must be unique")
    return aliases


@dataclass(frozen=True)
class Settings:
    mode: str
    allowed_origins: set[str]
    rate_limit: int
    rate_window_seconds: int
    reticulum_config_dir: Path | None
    storage_dir: Path
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    lab_send_enabled: bool = False
    lab_sender_config_dir: Path | None = None
    prometheus_url: str | None = None
    home_assistant_url: str | None = None
    home_assistant_token: str | None = None
    home_assistant_temperature_entity_id: str | None = None
    home_assistant_humidity_entity_id: str | None = None
    home_assistant_air_quality_entity_id: str | None = None
    home_assistant_cache_seconds: int = 900
    public_tcp_node_aliases: dict[str, str] | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        config_dir = os.environ.get("SIGNAL_RELAY_RETICULUM_CONFIG_DIR")
        origins = os.environ.get(
            "SIGNAL_RELAY_ALLOWED_ORIGINS",
            "http://127.0.0.1:4321,http://localhost:4321",
        )
        telegram_bot_token = os.environ.get("SIGNAL_RELAY_TELEGRAM_BOT_TOKEN") or None
        telegram_chat_id = os.environ.get("SIGNAL_RELAY_TELEGRAM_CHAT_ID") or None
        if bool(telegram_bot_token) != bool(telegram_chat_id):
            raise ValueError(
                "SIGNAL_RELAY_TELEGRAM_BOT_TOKEN and SIGNAL_RELAY_TELEGRAM_CHAT_ID must be set together"
            )
        return cls(
            mode=os.environ.get("SIGNAL_RELAY_MODE", "demo"),
            allowed_origins={origin.strip() for origin in origins.split(",") if origin.strip()},
            rate_limit=int(os.environ.get("SIGNAL_RELAY_RATE_LIMIT", "10")),
            rate_window_seconds=int(os.environ.get("SIGNAL_RELAY_RATE_WINDOW_SECONDS", "60")),
            reticulum_config_dir=Path(config_dir) if config_dir else None,
            storage_dir=Path(os.environ.get("SIGNAL_RELAY_STORAGE_DIR", "./data")),
            telegram_bot_token=telegram_bot_token,
            telegram_chat_id=telegram_chat_id,
            lab_send_enabled=os.environ.get("SIGNAL_RELAY_LAB_SEND_ENABLED", "false").lower() == "true",
            lab_sender_config_dir=Path(os.environ["SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR"])
            if os.environ.get("SIGNAL_RELAY_LAB_SENDER_CONFIG_DIR")
            else None,
            prometheus_url=os.environ.get("SIGNAL_RELAY_PROMETHEUS_URL") or None,
            home_assistant_url=os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_URL") or None,
            home_assistant_token=os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_TOKEN") or None,
            home_assistant_temperature_entity_id=os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID") or None,
            home_assistant_humidity_entity_id=os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_HUMIDITY_ENTITY_ID") or None,
            home_assistant_air_quality_entity_id=os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_AIR_QUALITY_ENTITY_ID") or None,
            home_assistant_cache_seconds=int(os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_CACHE_SECONDS", "900")),
            public_tcp_node_aliases=_public_tcp_node_aliases(
                os.environ.get("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES")
            ),
        )