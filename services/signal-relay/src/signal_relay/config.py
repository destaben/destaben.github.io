from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import os
import re
from urllib.parse import urlsplit


_PUBLIC_NODE_ALIAS = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,47}")
# IPv6 prefixes that embed an IPv4 address: NAT64 (RFC 6052) and its local-use variant (RFC 8215), the deprecated
# IPv4-compatible ::/96 form, 6to4 (RFC 3056) and Teredo (RFC 4380). They are rejected by prefix rather than by
# is_global, so an interpreter that reports any of them as global still cannot publish an embedded private address.
_NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")
_LOCAL_USE_NAT64_PREFIX = ipaddress.ip_network("64:ff9b:1::/48")
_IPV4_COMPATIBLE_PREFIX = ipaddress.ip_network("::/96")
_SIX_TO_FOUR_PREFIX = ipaddress.ip_network("2002::/16")
_TEREDO_PREFIX = ipaddress.ip_network("2001::/32")
_EMBEDDED_IPV4_PREFIXES = (
    _NAT64_PREFIX,
    _LOCAL_USE_NAT64_PREFIX,
    _IPV4_COMPATIBLE_PREFIX,
    _SIX_TO_FOUR_PREFIX,
    _TEREDO_PREFIX,
)
_DNS_NAME = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
_IPV6_LITERAL = re.compile(r"[0-9A-Fa-f:.]+")
_INVALID_TCP_URL = "SIGNAL_RELAY_PUBLIC_TCP_NODE_URLS must contain public tcp://host:port URLs"
_ENTITY_ID = re.compile(r"[a-z0-9_]+\.[a-z0-9_]+")
_CHANNEL_NAME_SETTING = re.compile(r"[A-Za-z0-9_ -]{1,32}")
_ATTRIBUTE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
_CHANNEL_FIELD_NAMES = frozenset({"text", "node_id", "timestamp", "hop_start", "hop_limit"})
_CHANNEL_FIELDS_MESSAGE = "SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS must be a JSON object that maps supported fields to attribute names"

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
        "recent_activity_1",
        "recent_activity_2",
        "recent_activity_3",
        "recent_activity_4",
        "recent_activity_5",
    }
)

MESHTASTIC_REQUIRED_ENTITY_KEYS = MESHTASTIC_ENTITY_KEYS


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


def _meshtastic_entity_ids(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    try:
        entity_ids = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS must be JSON") from error
    if not isinstance(entity_ids, dict) or not MESHTASTIC_REQUIRED_ENTITY_KEYS <= set(entity_ids) <= MESHTASTIC_ENTITY_KEYS:
        raise ValueError("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS must define the required keys")
    if not all(isinstance(entity_id, str) and _ENTITY_ID.fullmatch(entity_id) for entity_id in entity_ids.values()):
        raise ValueError("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS contains an invalid entity ID")
    return {key: entity_id for key, entity_id in entity_ids.items() if key in MESHTASTIC_REQUIRED_ENTITY_KEYS}


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


def _entity_id_prefix(value: str | None, setting: str) -> str | None:
    if not value:
        return None
    if not _ENTITY_ID.fullmatch(value):
        raise ValueError(f"{setting} must be a Home Assistant entity ID prefix")
    return value


def _channel_denylist(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    names = set()
    for raw_name in value.split(","):
        name = raw_name.strip()
        if not name:
            continue
        if not _CHANNEL_NAME_SETTING.fullmatch(name):
            raise ValueError(
                "SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST must contain channel names of 1 to 32 letters, digits, spaces, underscores, or hyphens"
            )
        names.add(name)
    return frozenset(names)


def _channel_fields(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    try:
        fields = json.loads(value)
    except ValueError:
        raise ValueError(_CHANNEL_FIELDS_MESSAGE) from None
    if not isinstance(fields, dict) or not all(
        key in _CHANNEL_FIELD_NAMES and isinstance(attribute, str) and _ATTRIBUTE_NAME.fullmatch(attribute)
        for key, attribute in fields.items()
    ):
        raise ValueError(_CHANNEL_FIELDS_MESSAGE)
    return fields


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
    # None derives the channel namespace from the gateway entity ID in meshtastic_entity_ids.
    meshtastic_channel_prefix: str | None = None
    meshtastic_channel_denylist: frozenset[str] = frozenset()
    # Maps the fields text, node_id, timestamp, hop_start, and hop_limit to Home Assistant attribute names.
    meshtastic_channel_fields: dict[str, str] | None = None
    meshtastic_status_cache_seconds: int = 900
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
            meshtastic_entity_ids=_meshtastic_entity_ids(os.environ.get("SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS")),
            meshtastic_cache_seconds=max(int(os.environ.get("SIGNAL_RELAY_MESHTASTIC_CACHE_SECONDS", "30")), 15),
            meshtastic_turnstile_secret=os.environ.get("SIGNAL_RELAY_MESHTASTIC_TURNSTILE_SECRET") or None,
            meshtastic_message_cooldown_seconds=max(
                int(os.environ.get("SIGNAL_RELAY_MESHTASTIC_MESSAGE_COOLDOWN_SECONDS", "300")), 60
            ),
            meshtastic_channel_prefix=_entity_id_prefix(os.environ.get("SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX"), "SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX"),
            meshtastic_channel_denylist=_channel_denylist(os.environ.get("SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST")),
            meshtastic_channel_fields=_channel_fields(os.environ.get("SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS")),
            meshtastic_status_cache_seconds=int(os.environ.get("SIGNAL_RELAY_MESHTASTIC_STATUS_CACHE_SECONDS", "900")),
            public_tcp_node_aliases=public_tcp_node_aliases,
            public_tcp_node_urls=public_tcp_node_urls,
        )
