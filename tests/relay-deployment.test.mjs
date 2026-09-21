import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readRepositoryFile = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");

test("publishes Reticulum node states through the bounded deployment edge", async () => {
  const [compose, nginx] = await Promise.all([
    readRepositoryFile("services/signal-relay/compose.yaml"),
    readRepositoryFile("services/signal-relay/nginx/nginx.conf"),
  ]);

  assert.match(compose, /SIGNAL_RELAY_PUBLIC_TCP_NODE_ALIASES:/);
  assert.doesNotMatch(compose, /SIGNAL_RELAY_RETICULUM_TCP_PORT|target: 4242/);
  assert.match(nginx, /location = \/v1\/lab\/reticulum-nodes \{/);
  assert.match(nginx, /location = \/v1\/lab\/reticulum-nodes \{\s+proxy_pass http:\/\/signal_relay;/);
});

test("ships a standalone Reticulum template with an interfaces section", async () => {
  const config = await readRepositoryFile("services/signal-relay/reticulum-config.example");

  assert.match(config, /^\[reticulum\]/m);
  assert.match(config, /^\[interfaces\]\n\n\[\[RNS Arborisis\]\]/m);
  assert.doesNotMatch(config, /TCPServerInterface/);
});