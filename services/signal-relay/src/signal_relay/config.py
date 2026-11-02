from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import os
import re
from urllib.parse import urlsplit


_PUBLIC_NODE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}")
# IPv6 prefixes that embed an IPv4 address: NAT64 (RFC 6052) and the deprecated IPv4-compatible ::/96 form.
_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")
_IPV4_COMPATIBLE_PREFIX = ipaddress.ip_network("::/96")
_EMBEDDED_IPV4_PREFIXES = (_NAT64_PREFIX, _IPV4_COMPATIBLE_PREFIX)
_DNS_NAME = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
_IPV6_LITERAL = re.compile(r"[0-9A-Fa-f:.]+")
_INVALID_TCP_URL = "SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must contain public tcp://host:port URLs"
_ENTITY_ID = re.compile(r"[a-z_]+\.[a-z0-9_]+")


_PRIVATE_HOST_SUFFIXES = (
    ".local",
    ".localhost",
    ".localdomain",
    ".lan",
    ".home",
    ".home.arpa",
    ".internal",
    ".intranet",
    ".corp",
    ".private",
)


def _is_printable_ascii(text: str) -> bool:
    # Non-ASCII format characters (soft hyphen, zero-width and BOM code points), whitespace and control
    # characters all fall outside this range, so they are rejected before any parsing can trim or hide them.
    return all(33 <= ord(character) <= 126 for character in text)


def _is_public_hostname(name: str) -> bool:
    """Reject single-label, numeric-looking and private-use names; DNS is never resolved here.

    Expects a lowercase name that has already passed the strict DNS charset check.
    """
    if "." not in name or name.endswith(_PRIVATE_HOST_SUFFIXES):
        return False
    last_label = name.rsplit(".", 1)[-1]
    # Non-canonical IPv4 spellings such as 127.1, 0x7f.1 or 0177.0.0.1 end in a numeric label.
    return not (last_label.isdigit() or last_label.startswith("0x"))


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


def _check_tcp_node_host(host: str, bracketed: bool) -> None:
    """Accept only public DNS names or bracketed global IPv6 literals; plain IPv4 is the only unbracketed IP."""
    if bracketed:
        if not _IPV6_LITERAL.fullmatch(host):
            raise ValueError(_INVALID_TCP_URL)
        try:
            address = ipaddress.IPv6Address(host)
        except ValueError as error:
            raise ValueError(_INVALID_TCP_URL) from error
        if not address.is_global or any(address in prefix for prefix in _EMBEDDED_IPV4_PREFIXES):
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must not contain private IP addresses")
        return
    if not _DNS_NAME.fullmatch(host):
        raise ValueError(_INVALID_TCP_URL)
    name = host.lower()
    try:
        address = ipaddress.IPv4Address(name)
    except ValueError:
        if not _is_public_hostname(name):
            raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must not contain private hostnames") from None
        return
    if not address.is_global:
        raise ValueError("SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must not contain private IP addresses")


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
        # Checked on the raw text, before urlsplit: a stray '?' or '#' yields no query or fragment to inspect.
        if not _is_printable_ascii(url) or "?" in url or "#" in url:
            raise ValueError(_INVALID_TCP_URL)
        try:
            parsed = urlsplit(url)
        except ValueError as error:
            raise ValueError(_INVALID_TCP_URL) from error
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
        ):
            raise ValueError(_INVALID_TCP_URL)
        _check_tcp_node_host(parsed.hostname, bracketed=parsed.netloc.startswith("["))
    return urls


def _entity_id(value: str | None, setting: str) -> str | None:
    if not value:
        return None
    if not _ENTITY_ID.fullmatch(value):
        raise ValueError(f"{setting} must be a Home Assistant entity ID")
    return value


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
    meshtastic_gateway_entity_id: str | None = None
    meshtastic_nodes_online_entity_id: str | None = None
    meshtastic_nodes_total_entity_id: str | None = None
    meshtastic_last_node_entity_id: str | None = None
    meshtastic_cache_seconds: int = 900
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
            home_assistant_temperature_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID"), "SIGNAL_RELAY_HOME_ASSISTANT_TEMPERATURE_ENTITY_ID"),
            home_assistant_humidity_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_HUMIDITY_ENTITY_ID"), "SIGNAL_RELAY_HOME_ASSISTANT_HUMIDITY_ENTITY_ID"),
            home_assistant_air_quality_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_AIR_QUALITY_ENTITY_ID"), "SIGNAL_RELAY_HOME_ASSISTANT_AIR_QUALITY_ENTITY_ID"),
            home_assistant_cache_seconds=int(os.environ.get("SIGNAL_RELAY_HOME_ASSISTANT_CACHE_SECONDS", "900")),
            meshtastic_gateway_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_MESHTASTIC_GATEWAY_ENTITY_ID"), "SIGNAL_RELAY_MESHTASTIC_GATEWAY_ENTITY_ID"),
            meshtastic_nodes_online_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_MESHTASTIC_NODES_ONLINE_ENTITY_ID"), "SIGNAL_RELAY_MESHTASTIC_NODES_ONLINE_ENTITY_ID"),
            meshtastic_nodes_total_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_MESHTASTIC_NODES_TOTAL_ENTITY_ID"), "SIGNAL_RELAY_MESHTASTIC_NODES_TOTAL_ENTITY_ID"),
            meshtastic_last_node_entity_id=_entity_id(os.environ.get("SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID"), "SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID"),
            meshtastic_cache_seconds=int(os.environ.get("SIGNAL_RELAY_MESHTASTIC_CACHE_SECONDS", "900")),
            public_tcp_node_aliases=public_tcp_node_aliases,
            public_tcp_node_urls=public_tcp_node_urls,
        )
