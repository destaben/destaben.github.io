import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readRepositoryFile = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("keeps the relay private on the shared deployment network", async () => {
  const compose = await readRepositoryFile("services/signal-relay/compose.yaml");

  assert.match(compose, /SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES:/);
  assert.doesNotMatch(compose, /SIGNAL_RELAY_RETICULUM_TCP_PORT|target: 4242/);
  assert.match(compose, /name: destaben-edge/);
  assert.match(compose, /external: true/);
  assert.doesNotMatch(compose, /^\s+ports:/m);
  assert.doesNotMatch(compose, /^\s+nginx:/m);
  assert.doesNotMatch(compose, /^\s+cloudflared:/m);
});

test("exposes Meshtastic channels through the discovery settings and no retired lastNode setting", async () => {
  const [compose, envExample] = await Promise.all([
    readRepositoryFile("services/signal-relay/compose.yaml"),
    readRepositoryFile("services/signal-relay/.env.example"),
  ]);

  for (const setting of ["SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX", "SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST", "SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS"]) {
    assert.match(compose, new RegExp(`${setting}: \\$\\{${setting}:-\\}`));
    assert.match(envExample, new RegExp(`^${setting}=`, "m"));
  }
  assert.doesNotMatch(compose, /MESHTASTIC_LAST_NODE/);
  assert.doesNotMatch(envExample, /MESHTASTIC_LAST_NODE/);
});

test("ships a standalone Reticulum template with an interfaces section", async () => {
  const config = await readRepositoryFile("services/signal-relay/reticulum-config.example");

  assert.match(config, /^\[reticulum\]/m);
  assert.match(config, /^\[interfaces\]\n\n\[\[RNS Arborisis\]\]/m);
  assert.doesNotMatch(config, /TCPServerInterface/);
});