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


test("keeps the direct-message token list identical in the code, the relay docs, and the inventory script", async () => {
  const [code, relayDocs, readme, inventory] = await Promise.all([
    readRepositoryFile("services/signal-relay/src/signal_relay/home_assistant.py"),
    readRepositoryFile("docs/SIGNAL-RELAY.md"),
    readRepositoryFile("services/signal-relay/README.md"),
    readRepositoryFile("docs/MESHTASTIC-INVENTORY.md"),
  ]);
  const quoted = (block) => [...block.matchAll(/"([a-z]+)"/g)].map((match) => match[1]).sort();
  const backticked = (text) => [...text.matchAll(/`([a-z]+)`/g)].map((match) => match[1]).sort();

  const fromCode = quoted(code.match(/_DIRECT_MESSAGE_TOKENS = frozenset\(\{([\s\S]*?)\}\)/)[1]);
  const fromInventory = quoted(inventory.match(/DM_TOKENS = \{([\s\S]*?)\}/)[1]);
  const fromRelayDocs = backticked(relayDocs.match(/direct-message list \(([^)]*)\)/)[1]);
  const fromReadme = backticked(readme.match(/direct-message list \(([^)]*)\)/)[1]);

  assert.ok(fromCode.length >= 16, "the code list is found");
  assert.deepEqual(fromInventory, fromCode);
  assert.deepEqual(fromRelayDocs, fromCode);
  assert.deepEqual(fromReadme, fromCode);
});

test("keeps one canonical Behavior changes list in docs/SIGNAL-RELAY.md and links to it from the README", async () => {
  const [relayDocs, readme] = await Promise.all([
    readRepositoryFile("docs/SIGNAL-RELAY.md"),
    readRepositoryFile("services/signal-relay/README.md"),
  ]);
  const section = (text) => text.match(/^## Behavior changes\n([\s\S]*?)(?=^## )/m)?.[1] ?? "";

  assert.match(section(readme), /docs\/SIGNAL-RELAY\.md#behavior-changes/);
  assert.doesNotMatch(section(readme), /^- /m, "the README repeats no bullets");
  assert.match(section(relayDocs), /^- Channels publish only when allowlisted/m);
  assert.match(section(relayDocs), /20 seconds/);
  assert.match(section(relayDocs), /direct-message/);
  assert.match(section(relayDocs), /stop the relay at startup/);
});

test("documents the status cache minimum and masking in the env example and the instructions", async () => {
  const [envExample, instructions] = await Promise.all([
    readRepositoryFile("services/signal-relay/.env.example"),
    readRepositoryFile(".github/instructions/signal-relay.instructions.md"),
  ]);

  assert.match(envExample, /clamped to a minimum of 900 seconds/);
  assert.match(instructions, /SIGNAL_RELAY_MESHTASTIC_CHANNEL_ALLOWLIST/);
  assert.match(instructions, /masked/);
});
