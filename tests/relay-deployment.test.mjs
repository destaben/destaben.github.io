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

test("ships a standalone Reticulum template with an interfaces section", async () => {
  const config = await readRepositoryFile("services/signal-relay/reticulum-config.example");

  assert.match(config, /^\[reticulum\]/m);
  assert.match(config, /^\[interfaces\]\n\n\[\[RNS Arborisis\]\]/m);
  assert.doesNotMatch(config, /TCPServerInterface/);
});