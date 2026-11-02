# Meshtastic Inventory Checklist for Home Assistant

Operator checklist for locating Meshtastic entities in a Home Assistant installation and verifying the read-only projection used by Signal Relay. Nothing produced by these steps belongs on the public site or in Git.

Run the commands on the host where Home Assistant runs. They read local files inside the Home Assistant container. They do not call the HTTP API, do not need an access token, and do not change configuration.

Replace `homeassistant` with your container name. Run the Docker commands as an operator who belongs to the `docker` group, with the system Docker context: `docker context show` must return `default`. Do not prefix them with `sudo`. To locate the container:

```sh
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

## 1. Confirm the Meshtastic integration is installed

```sh
docker exec homeassistant sh -c 'find /config/custom_components /usr/local/lib/python*/site-packages/homeassistant/components -maxdepth 2 -type d -iname "*meshtastic*" 2>/dev/null'
```

## 2. List Meshtastic entities

This command reads the local entity registry and prints each entity ID, display name, platform, and disabled flag. It does not print states, attributes, positions, or radio identifiers. Display names can still reveal channel or node names, so review them before sharing.

```sh
docker exec homeassistant python3 -c 'import json; registry=json.load(open("/config/.storage/core.entity_registry")); entries=registry.get("data", {}).get("entities", []); matches=[{"entity_id": entry.get("entity_id"), "name": entry.get("name") or entry.get("original_name"), "platform": entry.get("platform"), "disabled_by": entry.get("disabled_by")} for entry in entries if "meshtastic" in str(entry).lower()]; print(json.dumps(matches, indent=2, ensure_ascii=False))'
```

Note the gateway entity ID and the online and total node-count entity IDs. You need them in step 7. Channel entities are not configured one by one: the relay looks at entities whose ID starts with the channel prefix (by default the gateway entity ID plus `_channel_`), and publishes only the ones whose names are in the allowlist from step 7. Confirm that prefix in step 5.

## 3. List the config entry

This shows which integration created the entities. It prints the entry ID, domain, title, version, and state. Review the title before sharing it.

```sh
docker exec homeassistant python3 -c 'import json; entries=json.load(open("/config/.storage/core.config_entries")).get("data", {}).get("entries", []); matches=[{"entry_id": entry.get("entry_id"), "domain": entry.get("domain"), "title": entry.get("title"), "version": entry.get("version"), "state": entry.get("state")} for entry in entries if "mesh" in str(entry.get("domain", "")).lower() or "mesh" in str(entry.get("title", "")).lower()]; print(json.dumps(matches, indent=2, ensure_ascii=False))'
```

## 4. Review the integration's services

Locate `services.yaml` and print it. If the first command returns more than one path, run the second command for each path.

```sh
docker exec homeassistant sh -c 'find /config/custom_components /usr/local/lib/python*/site-packages/homeassistant/components -path "*meshtastic*/services.yaml" -type f 2>/dev/null'
```

```sh
docker exec homeassistant sh -c 'cat /config/custom_components/meshtastic/services.yaml'
```

The public website must only use the read-only projection described in steps 5 to 8. It must never call a service that transmits over the radio.

## 5. Read the aggregate restore state

This command reads Home Assistant's saved restore-state file. It does not query the live API. For the gateway entity ID you pass in, it prints the entries whose entity ID matches the gateway itself, entities whose ID starts with the gateway's channel prefix, or node-count sensors. For each matching entry it prints `entity_id`, `state`, and `last_changed`.

Channel entity states may contain message text. Review every value in the output before sharing it, and redact message text, names, coordinates, addresses, keys, and identifiers.

Replace `GATEWAY_ENTITY_ID` with the gateway entity ID from step 2. If your deployment sets `SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX` to something other than the gateway ID plus `_channel_`, change `prefix` to match it.

```sh
docker exec homeassistant python3 -c 'import json; gateway="GATEWAY_ENTITY_ID"; data=json.load(open("/config/.storage/core.restore_state")).get("data", {}); states=data.get("states", []); prefix=gateway + "_channel_"; matches=[{"entity_id": state.get("state", {}).get("entity_id"), "state": state.get("state", {}).get("state"), "last_changed": state.get("state", {}).get("last_changed")} for state in states if (entity_id := state.get("state", {}).get("entity_id", "")) == gateway or entity_id.startswith(prefix) or (entity_id.startswith("sensor.") and "_stats_nodes_" in entity_id)]; print(json.dumps(matches, indent=2, ensure_ascii=False))'
```

## 5b. Verify the channel and message fields (verify on the host)

The relay can only publish what these fields expose, and it does not guess their names. This command prints, for each channel entity under the prefix, the attribute names, the value types, and three shape checks. It never prints attribute values, state values, or friendly names. The `node_id_shape` check is true only for a string shaped like `!` plus eight hexadecimal digits. The `hop_value` check is true for an integer from 0 to 7. The `dm_word` check applies the relay's word-token list to the same words the relay checks: the entity ID suffix, the friendly name with the gateway's own friendly name removed, and any custom-prefix words that the gateway's entity ID and friendly name do not contain. It is a heuristic: a direct message with a neutral name shows `dm_word` false, so review every name yourself.

Replace `GATEWAY_ENTITY_ID` as in step 5. The script runs inside the container, reads only the restore-state file, and prints JSON.

```sh
docker exec -i homeassistant python3 - <<'PY'
import json
import re

gateway = "GATEWAY_ENTITY_ID"
prefix = gateway + "_channel_"
DM_TOKENS = {"dm", "dms", "pm", "pms", "direct", "directa", "directas", "directo", "directos",
             "private", "privada", "privadas", "privado", "privados", "whisper", "secret"}


def words(text):
    return [token for token in re.split(r"[^a-z0-9]+", str(text).lower()) if token]


data = json.load(open("/config/.storage/core.restore_state")).get("data", {})
states = [item.get("state", {}) for item in data.get("states", [])]
gateway_entry = next((s for s in states if s.get("entity_id") == gateway), {})
gateway_name = str((gateway_entry.get("attributes") or {}).get("friendly_name", ""))
gateway_words = set(words(gateway)) | set(words(gateway_name))
gateway_phrase = words(gateway_name)


def checked_words(state):
    entity_id = str(state.get("entity_id", ""))
    friendly = str((state.get("attributes") or {}).get("friendly_name", "")).lower()
    if gateway_phrase:
        friendly = re.sub(r"\b" + r"[^a-z0-9]+".join(re.escape(w) for w in gateway_phrase) + r"\b", " ", friendly)
    return ((set(words(entity_id[:len(prefix)])) - gateway_words)
            | set(words(entity_id[len(prefix):]))
            | set(words(friendly)))


def describe(value):
    return {"type": type(value).__name__,
            "node_id_shape": isinstance(value, str) and re.fullmatch(r"![0-9A-Fa-f]{8}", value) is not None,
            "hop_value": isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 7}


report = [{"entity_id": s.get("entity_id"),
           "state_type": type(s.get("state")).__name__,
           "dm_word": not DM_TOKENS.isdisjoint(checked_words(s)),
           "fields": {name: describe(value) for name, value in (s.get("attributes") or {}).items()}}
          for s in states if str(s.get("entity_id", "")).startswith(prefix)]
print(json.dumps(report, indent=2, ensure_ascii=False))
PY
```

The restore-state file may not list every live entity, and the relay reads the live entity list. Treat a channel that is missing here as unverified, not as absent, and recheck it after the relay is recreated with the step 8 check.

Use the output to decide each setting in step 7. Check each item:

- **Channel discovery:** list in `SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST` (step 7) only the names of public channels; an entity that is not allowlisted is never published. For each direct-message entity, add its name to `SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST` (step 7) even if it is not allowlisted today, because `dm_word` is only a heuristic, and tell the maintainer when a direct message is missed by the token list.
- **Text:** find the attribute that holds the message text. If the text is the entity state, leave `text` out of `SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS`. If it is an attribute, configure its name as `text`.
- **Sender:** find the attribute with `node_id_shape` true. Configure its name as `node_id`. Without it, no message is published.
- **Time:** an attribute with an ISO-8601 or epoch type can be configured as `timestamp`. Otherwise the entity's `last_changed` is used.
- **Hops:** configure `hop_start` and `hop_limit` only when both attributes have `hop_value` true. Otherwise hops are omitted.

Do not paste this output into Git or the public site. Share it privately only if you need help interpreting it, and first replace entity IDs and any name you do not want to share.

## 6. Share only what is needed

Do not share the node list. It can include names of other people and their locations.

Before pasting any output, remove coordinates, addresses, keys, passwords, node IDs, message text, and any other private data. Share the output of step 5 only after that review.

Entity IDs are private configuration. Keep them out of Git and out of the public site. They may be shared privately to configure the Signal Relay projection in step 7.

## 7. Configure the private projection in Signal Relay

In the private directory where Signal Relay is deployed, set these values in its ignored `.env` file. Use the dedicated read-only Home Assistant token configured for the relay. Never write the token into this document or into Git.

```sh
# The same private map the Meshtastic send projection already requires. The status route reads only its gateway, nodes_online, and nodes_total keys.
SIGNAL_RELAY_MESHTASTIC_ENTITY_IDS={"gateway": "GATEWAY_ENTITY_ID", "nodes_online": "ONLINE_COUNT_ENTITY_ID", "nodes_total": "TOTAL_COUNT_ENTITY_ID", ...all other required keys, one entity ID each...}
# Optional. Defaults to the gateway entity ID plus "_channel_".
SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX=
# Default-deny: comma-separated names of the only public channels to publish. Empty publishes no channels.
# Each name is 1 to 32 letters, digits, spaces, underscores, or hyphens; matching ignores case and treats spaces, underscores, and hyphens alike.
SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST=
# Extra layer applied after the allowlist: names hidden even when allowlisted, with the same name rules.
SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST=
# Optional JSON map from published fields to the attribute names verified in step 5b.
# Leave empty to publish channel names without messages. Use the names verified on the host.
SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS='{"text": "TEXT_ATTRIBUTE", "node_id": "NODE_ID_ATTRIBUTE", "timestamp": "TIMESTAMP_ATTRIBUTE", "hop_start": "HOP_START_ATTRIBUTE", "hop_limit": "HOP_LIMIT_ATTRIBUTE"}'
SIGNAL_RELAY_MESHTASTIC_STATUS_CACHE_SECONDS=900
```

The map must contain every key listed in `services/signal-relay/README.md`; the three status keys are required before `GET /v1/lab/meshtastic-status` becomes available. The gateway entity must report exactly `Connected`. Remove any field from `SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS` that you have not verified; an unset field is never read. The relay rejects negative, non-integer, or inconsistent counts, and never publishes entity IDs, Home Assistant attributes, author names, serial numbers, MAC addresses, full node IDs, or direct messages. The relay refuses to start on a malformed entity ID or an invalid channel setting, so check that the container is running after recreation. A failure while discovering channels omits `channels` and keeps the counts available. Values below 900 seconds for the status cache are raised to 900.

Recreate only the relay after changing its environment:

```sh
docker compose up -d --force-recreate signal-relay
```

## 8. Verify the projection without exposing private data

Run this check on the relay host. It confirms that the route returns only the public contract. It checks key names, the channel count, and the masked node-ID shape, and it does not print any values:

```sh
docker compose exec -T signal-relay python -c 'import json, re; from urllib.request import urlopen; payload=json.load(urlopen("http://127.0.0.1:8787/v1/lab/meshtastic-status")); assert payload.get("status") == "available"; assert set(payload) <= {"status", "onlineNodes", "totalNodes", "channels", "refreshedAt"}; assert isinstance(payload["onlineNodes"], int) and isinstance(payload["totalNodes"], int) and payload["onlineNodes"] <= payload["totalNodes"]; channels=payload.get("channels", []); assert len(channels) <= 16; assert all(set(channel) <= {"name", "last"} for channel in channels); assert all(set(channel["last"]) <= {"nodeId", "text", "time", "hops"} and re.fullmatch(r"![0-9A-Fa-f]{6}\*\*", channel["last"]["nodeId"]) for channel in channels if "last" in channel)'
```

If `channels` is missing, either `SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST` is empty or channel discovery failed while the counts still succeeded. Check the allowlist, the channel prefix, the denylist, and whether the relay's token can read the entity states. If the route returns `503 meshtastic_status_unavailable`, private configuration is missing or Home Assistant did not answer the counts. Do not open a host port or publish Home Assistant to troubleshoot it.

**Symptom: channels missing while the counts show `available`.** The relay reads the whole entity list from `/api/states` in one response, and it refuses any response body above 1 MiB. A large Home Assistant installation can exceed that. The list read then fails, the relay omits `channels` for 60 seconds and retries, and the counts keep working, so the route still reports `available`. The check above then shows no `channels` key even though the allowlist names channels. This version has no setting that raises the cap, and this document does not change it.

**Workarounds, in order.**

1. **Reduce the entity list.** Disabling entities nobody uses in Home Assistant's entity registry generally removes them from the state machine, so they leave `/api/states`. This is the only workaround that works without a code change.
2. **Setting `SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX` does not help.** The Home Assistant REST API has no server-side filter for `/api/states`. The relay downloads the whole list and filters it afterwards, so the prefix only selects which entities are kept, not how much is downloaded.
3. **A dedicated token or area does not help, as far as this endpoint is documented.** I did not find a per-user or per-area filter for `/api/states` in the REST API. Verify this on your installation before relying on it.
4. **A durable fix needs a code change.** Options include reading each allowlisted channel directly from `GET /api/states/<prefix><slug>`, because the allowlist already names the entities, or asking Home Assistant's template API for the filtered list. Neither is implemented in this version.
