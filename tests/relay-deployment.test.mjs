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

  for (const setting of ["SIGNAL_RELAY_MESHTASTIC_CHANNEL_PREFIX", "SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST", "SIGNAL_RELAY_MESHTASTIC_CHANNEL_DENYLIST", "SIGNAL_RELAY_MESHTASTIC_CHANNEL_FIELDS"]) {
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

test("uses one documented node-count limit in the relay and the front end", async () => {
  const [relay, panel, docs] = await Promise.all([
    readRepositoryFile("services/signal-relay/src/signal_relay/home_assistant.py"),
    readRepositoryFile("src/components/MeshtasticStatusLab.astro"),
    readRepositoryFile("docs/SIGNAL-RELAY.md"),
  ]);

  const relayLimit = relay.match(/^_MAX_NODE_COUNT = ([0-9_]+)$/m)?.[1];
  const frontEndLimit = panel.match(/const maxCount = ([0-9_]+);/)?.[1];

  assert.equal(relayLimit, "100_000");
  assert.equal(frontEndLimit, relayLimit);
  assert.match(docs, /whole numbers from 0 to 100000/);
});


test("gives the browser enough time for a cold relay refresh", async () => {
  const panel = await readRepositoryFile("src/components/MeshtasticStatusLab.astro");
  const timeout = Number(panel.match(/const requestTimeoutMs = ([0-9_]+);/)?.[1].replaceAll("_", ""));

  // The relay's worst case is its 10 second refresh deadline plus a final 5 second read.
  assert.ok(timeout >= 15_000, `requestTimeoutMs must cover the worst cold refresh, got ${timeout}`);
});
