from dataclasses import dataclass
from pathlib import Path
import os


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
        )