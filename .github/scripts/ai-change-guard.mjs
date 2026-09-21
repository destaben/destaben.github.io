import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const statePath = resolve(".copilot/validation-state.json");
const sensitivePatterns = [
  /^\.github\/(hooks|scripts|workflows)\//,
  /^astro\.config\.mjs$/,
  /^public\/CNAME$/,
  /^services\/signal-relay\/(src|tests|nginx|Dockerfile|compose\.yaml)/,
  /^docs\/SIGNAL-RELAY\.md$/,
  /^src\/components\/(SignalRelayLab|ContainerMetricsLab|HomeAssistantLab)\.astro$/,
];

const commandChecks = {
  "context-lint": "node .github/scripts/validate-ai-context.mjs",
  "npm-verify": "npm run verify",
  "relay-pytest": "services/signal-relay/.venv/bin/python -m pytest",
  "compose-config": "docker compose -f services/signal-relay/compose.yaml config",
};

const runGit = (arguments_) => execFileSync("git", arguments_, { encoding: "utf8" });
const output = (value) => process.stdout.write(`${JSON.stringify(value)}\n`);
const isSensitive = (file) => sensitivePatterns.some((pattern) => pattern.test(file));

function expandPath(file) {
  const absolutePath = resolve(file);
  if (!existsSync(absolutePath) || !statSync(absolutePath).isDirectory()) return [file];
  return readdirSync(absolutePath, { recursive: true })
    .map((entry) => `${file.replace(/\/$/, "")}/${entry}`)
    .filter((entry) => existsSync(resolve(entry)) && statSync(resolve(entry)).isFile());
}

function changedFiles() {
  const status = runGit(["status", "--porcelain=v1", "-z"]);
  const entries = status.split("\0").filter(Boolean);
  const files = [];
  for (const entry of entries) {
    const file = entry.slice(3);
    if (file) files.push(...expandPath(file));
  }
  return [...new Set(files)].sort();
}

function fingerprint(files) {
  const hash = createHash("sha256");
  for (const file of files) {
    hash.update(`${file}\0`);
    const absolutePath = resolve(file);
    if (existsSync(absolutePath)) hash.update(readFileSync(absolutePath));
    else hash.update("deleted");
  }
  return hash.digest("hex");
}

function requirements() {
  const files = changedFiles();
  const sensitiveFiles = files.filter(isSensitive);
  const checks = new Set();
  const hasSite = files.some((file) => /^(src\/|tests\/|public\/|astro\.config\.mjs$|package(?:-lock)?\.json$|\.github\/workflows\/deploy-pages\.yml$|README\.md$)/.test(file));
  const hasRelay = files.some((file) => /^(services\/signal-relay\/|docs\/SIGNAL-RELAY\.md$|src\/components\/(SignalRelayLab|ContainerMetricsLab|HomeAssistantLab)\.astro$)/.test(file));
  const hasContainer = files.some((file) => /^(services\/signal-relay\/(Dockerfile|compose\.yaml|nginx\/)|\.github\/workflows\/publish-signal-relay\.yml$)/.test(file));
  const hasContext = files.some((file) => /^\.github\/(agents|hooks|instructions|scripts|skills)\//.test(file));
  if (hasContext) checks.add("context-lint");
  if (hasSite) checks.add("npm-verify");
  if (hasRelay) checks.add("relay-pytest");
  if (hasContainer) checks.add("compose-config");
  return { files, sensitiveFiles, checks: [...checks].sort(), fingerprint: fingerprint(sensitiveFiles) };
}

async function record(checks) {
  const current = requirements();
  const required = new Set(current.checks);
  const provided = new Set(checks);
  if (current.sensitiveFiles.length === 0) throw new Error("No sensitive changed files require a validation record.");
  if ([...required].some((check) => !provided.has(check))) {
    throw new Error(`Missing required checks: ${[...required].filter((check) => !provided.has(check)).join(", ")}`);
  }
  await mkdir(resolve(".copilot"), { recursive: true });
  await writeFile(statePath, `${JSON.stringify({ fingerprint: current.fingerprint, checks: current.checks, recordedAt: new Date().toISOString() }, null, 2)}\n`);
  output({ recorded: true, ...current });
}

async function validateStop() {
  const current = requirements();
  if (current.sensitiveFiles.length === 0) return output({});
  if (!existsSync(statePath)) {
    return output({ decision: "block", reason: "Sensitive changes need change-verifier validation before completion." });
  }
  const state = JSON.parse(await readFile(statePath, "utf8"));
  const matches = state.fingerprint === current.fingerprint && current.checks.every((check) => state.checks?.includes(check));
  if (!matches) {
    return output({ decision: "block", reason: "Sensitive diff changed or required validation is missing. Run change-verifier again." });
  }
  output({});
}

async function main() {
  const [command, ...arguments_] = process.argv.slice(2);
  if (command === "requirements") return output(requirements());
  if (command === "record") {
    const checks = arguments_[0] === "--checks" ? arguments_[1] : arguments_[0];
    return record((checks || "").split(",").filter(Boolean));
  }

  const raw = await new Promise((resolveInput) => {
    let value_ = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { value_ += chunk; });
    process.stdin.on("end", () => resolveInput(value_));
  });
  let input = {};
  try { input = raw.trim() ? JSON.parse(raw) : {}; } catch { return output({}); }
  const event = input.hookEventName || input.hook_event_name || input.event || "";
  if (event === "Stop") return validateStop();
  output({});
}

main().catch((error) => {
  output({ decision: "block", reason: error.message });
  process.exitCode = 2;
});