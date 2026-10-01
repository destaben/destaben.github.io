from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import os
import re
from urllib.parse import urlsplit


_PUBLIC_NODE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}")
_ENTITY_ID = re.compile(r"[a-z_]+\.[a-z_0-9]+")

MESHTASTIC_ENTITY_KEYS = frozenset(
    {
        "gateway",
        "node_long_name",
        "node_short_name",
        "uptime_seconds",
        "battery_percent",
        "voltage",
        "channel_utilization_percent",
        "airtime_tx_percent",
        "nodes_online",
        "nodes_total",
        "packets_rx",
        "packets_tx",
        "packets_rx_bad",
        "packets_rx_duplicate",
        "packets_tx_relayed",
        "packets_tx_relay_cancelled",
        "rx_per_minute",
        "tx_per_minute",
        "rf_errors_per_minute",
        "duplicates_per_minute",
        "relay_cancelled_per_minute",
        "last_message",
        "last_sender",
        "last_channel",
        "last_received",
        "last_sender_hops",
        "last_sender_hops_available",
        "neighbor_long_name",
        "neighbor_short_name",
        "neighbor_snr",
        "neighbor_hops_away",
    }
)


def _meshtastic_entity_ids(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    try:
        entity_ids = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS must be JSON") from error
    if not isinstance(entity_ids, dict) or set(entity_ids) != MESHTASTIC_ENTITY_KEYS:
        raise ValueError("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS must define the required keys")
    if not all(isinstance(entity_id, str) and _ENTITY_ID.fullmatch(entity_id) for entity_id in entity_ids.values()):
        raise ValueError("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS contains an invalid entity ID")
    return entity_ids


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


def _public_tcp_node_urls(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        urls = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must be JSON") from error
    if not isinstance(urls, dict) or len(urls) > 12:
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must contain at most 12 URLs")
    for alias, url in urls.items():
        if not isinstance(alias, str) or not _PUBLIC_NODE_ALIAS.fullmatch(alias) or not isinstance(url, str):
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS contains an invalid entry")
        parsed = urlsplit(url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS contains an invalid port") from error
        if (
            parsed.scheme != "tcp"
            or not parsed.hostname
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must contain public tcp://host:port URLs")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must not contain private IP addresses")
    return urls


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
    meshtastic_entity_ids: dict[str, str] | None = None
    meshtastic_cache_seconds: int = 30
    meshtastic_turnstile_secret: str | None = None
    meshtastic_message_cooldown_seconds: int = 300
    public_tcp_node_aliases: dict[str, str] | None = None
    public_tcp_node_urls: dict[str, str] | None = None

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
        public_tcp_node_aliases = _public_tcp_node_aliases(
            os.environ.get("SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES")
        )
        public_tcp_node_urls = _public_tcp_node_urls(
            os.environ.get("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS")
        )
        if set(public_tcp_node_urls) != set(public_tcp_node_aliases.values()):
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must define one URL for every public alias")
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
            meshtastic_entity_ids=_meshtastic_entity_ids(os.environ.get("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS")),
            meshtastic_cache_seconds=max(int(os.environ.get("SIGNAL_RELAY_MESHTASTIC_CACHE_SECONDS", "30")), 15),
            meshtastic_turnstile_secret=os.environ.get("SIGNAL_RELAY_MESHTASTIC_TURNSTILE_SECRET") or None,
            meshtastic_message_cooldown_seconds=max(
                int(os.environ.get("SIGNAL_RELAY_MESHTASTIC_MESSAGE_COOLDOWN_SECONDS", "300")), 60
            ),
            public_tcp_node_aliases=public_tcp_node_aliases,
            public_tcp_node_urls=public_tcp_node_urls,
        )