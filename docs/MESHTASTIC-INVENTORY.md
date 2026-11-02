# Meshtastic Inventory Checklist for Home Assistant

Operator checklist for locating Meshtastic entities in a Home Assistant installation and verifying the read-only projection used by Signal Relay. Nothing produced by these steps belongs on the public site or in Git.

Run the commands on the host where Home Assistant runs. They read local files inside the Home Assistant container. They do not call the HTTP API, do not need an access token, and do not change configuration.

Replace `homeassistant` with your container name. The examples use `sudo` because Docker commonly requires it on the host; drop it if your user can run Docker directly. To locate the container:

```sh
sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

## 1. Confirm the Meshtastic integration is installed

```sh
sudo docker exec homeassistant sh -c 'find /config/custom_components /usr/local/lib/python*/site-packages/homeassistant/components -maxdepth 2 -type d -iname "*meshtastic*" 2>/dev/null'
```

## 2. List Meshtastic entities

This command reads the local entity registry and prints each entity ID, display name, platform, and disabled flag. It does not print states, attributes, positions, or radio identifiers. Display names can still reveal channel or node names, so review them before sharing.

```sh
sudo docker exec homeassistant python3 -c 'import json; registry=json.load(open("/config/.storage/core.entity_registry")); entries=registry.get("data", {}).get("entities", []); matches=[{"entity_id": entry.get("entity_id"), "name": entry.get("name") or entry.get("original_name"), "platform": entry.get("platform"), "disabled_by": entry.get("disabled_by")} for entry in entries if "meshtastic" in str(entry).lower()]; print(json.dumps(matches, indent=2, ensure_ascii=False))'
```

Note the gateway entity ID and the online and total node-count entity IDs. You need them in steps 5 and 7. Channel entities are found automatically from the gateway ID in step 5 and are not configured.

## 3. List the config entry

This shows which integration created the entities. It prints the entry ID, domain, title, version, and state. Review the title before sharing it.

```sh
sudo docker exec homeassistant python3 -c 'import json; entries=json.load(open("/config/.storage/core.config_entries")).get("data", {}).get("entries", []); matches=[{"entry_id": entry.get("entry_id"), "domain": entry.get("domain"), "title": entry.get("title"), "version": entry.get("version"), "state": entry.get("state")} for entry in entries if "mesh" in str(entry.get("domain", "")).lower() or "mesh" in str(entry.get("title", "")).lower()]; print(json.dumps(matches, indent=2, ensure_ascii=False))'
```

## 4. Review the integration's services

Locate `services.yaml` and print it. If the first command returns more than one path, run the second command for each path.

```sh
sudo docker exec homeassistant sh -c 'find /config/custom_components /usr/local/lib/python*/site-packages/homeassistant/components -path "*meshtastic*/services.yaml" -type f 2>/dev/null'
```

```sh
sudo docker exec homeassistant sh -c 'cat /config/custom_components/meshtastic/services.yaml'
```

The public website must only use the read-only projection described in steps 5 to 8. It must never call a service that transmits over the radio.

## 5. Read the aggregate restore state

This command reads Home Assistant's saved restore-state file. It does not query the live API. For the gateway entity ID you pass in, it prints the entries whose entity ID matches the gateway itself, entities whose ID starts with the gateway's channel prefix, or node-count sensors. For each matching entry it prints `entity_id`, `state`, and `last_changed`.

Channel entity states may contain message text. Review every value in the output before sharing it, and redact message text, names, coordinates, addresses, keys, and identifiers.

Replace `GATEWAY_ENTITY_ID` with the gateway entity ID from step 2.

```sh
sudo docker exec homeassistant python3 -c 'import json; gateway="GATEWAY_ENTITY_ID"; data=json.load(open("/config/.storage/core.restore_state")).get("data", {}); states=data.get("states", []); prefix=gateway + "_channel_"; matches=[{"entity_id": state.get("state", {}).get("entity_id"), "state": state.get("state", {}).get("state"), "last_changed": state.get("state", {}).get("last_changed")} for state in states if (entity_id := state.get("state", {}).get("entity_id", "")) == gateway or entity_id.startswith(prefix) or (entity_id.startswith("sensor.") and "_stats_nodes_" in entity_id)]; print(json.dumps(matches, indent=2, ensure_ascii=False))'
```

## 6. Share only what is needed

Do not share the node list. It can include names of other people and their locations.

Before pasting any output, remove coordinates, addresses, keys, passwords, node IDs, message text, and any other private data. Share the output of step 5 only after that review.

Entity IDs are private configuration. Keep them out of Git and out of the public site. They may be shared privately to configure the Signal Relay projection in step 7.

## 7. Configure the private projection in Signal Relay

In the private directory where Signal Relay is deployed, set these values in its ignored `.env` file. Use the dedicated read-only Home Assistant token configured for the relay. Never write the token into this document or into Git.

```sh
SIGNAL_RELAY_MESHTASTIC_GATEWAY_ENTITY_ID=GATEWAY_ENTITY_ID
SIGNAL_RELAY_MESHTASTIC_NODES_ONLINE_ENTITY_ID=ONLINE_COUNT_ENTITY_ID
SIGNAL_RELAY_MESHTASTIC_NODES_TOTAL_ENTITY_ID=TOTAL_COUNT_ENTITY_ID
# Optional: only an entity whose state is a name that is safe to publish.
SIGNAL_RELAY_MESHTASTIC_LAST_NODE_ENTITY_ID=
SIGNAL_RELAY_MESHTASTIC_CACHE_SECONDS=900
```

The first three entity IDs are required before `GET /v1/lab/meshtastic-status` becomes available. The last one is optional: a missing entity (HTTP 404) omits `lastNode`, while other HTTP errors (such as 401 or 500) and transport errors still make the route return `503`. The relay rejects negative, non-integer, or inconsistent counts, and never publishes entity IDs or Home Assistant attributes. Do not lower the cache below 900 seconds.

Recreate only the relay after changing its environment:

```sh
sudo docker compose up -d --force-recreate signal-relay
```

## 8. Verify the projection without exposing private data

Run this check on the relay host. It confirms that the route returns only the public contract, and it does not print the values or the configured identifiers:

```sh
sudo docker compose exec -T signal-relay python -c 'import json; from urllib.request import urlopen; payload=json.load(urlopen("http://127.0.0.1:8787/v1/lab/meshtastic-status")); assert payload.get("status") == "available"; assert set(payload) <= {"status", "onlineNodes", "totalNodes", "lastNode", "refreshedAt"}; assert isinstance(payload["onlineNodes"], int) and isinstance(payload["totalNodes"], int) and payload["onlineNodes"] <= payload["totalNodes"]'
```

If private configuration is missing or Home Assistant does not respond, the route returns `503 meshtastic_status_unavailable`. Do not open a host port or publish Home Assistant to troubleshoot it.
