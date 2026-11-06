import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readSource = (path) => readFile(new URL(`../${path}`, import.meta.url), "utf8");
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// WCAG 2.x relative luminance and contrast ratio for #rrggbb colors.
const luminance = (hex) => {
  const [red, green, blue] = [1, 3, 5].map((index) => {
    const channel = parseInt(hex.slice(index, index + 2), 16) / 255;
    return channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
};
const contrast = (foreground, background) => {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
  return (lighter + 0.05) / (darker + 0.05);
};
// color-mix(in srgb, a <weight>%, b) for opaque colors.
const mixSrgb = (weight, first, second) => {
  const channels = [1, 3, 5].map((index) => {
    const value = parseInt(first.slice(index, index + 2), 16) * weight + parseInt(second.slice(index, index + 2), 16) * (1 - weight);
    return Math.round(value).toString(16).padStart(2, "0");
  });
  return `#${channels.join("")}`;
};

const css = await readSource("src/styles/global.css");
const token = (name) => css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6});`))?.[1];
const ruleBody = (selector) => css.match(new RegExp(`(?:^|[}\\s])${escapeRegExp(selector)}\\s*\\{([^}]*)\\}`))?.[1] ?? "";
const declaredColor = (body) => body.match(/(?:^|[;\s])color:\s*(#[0-9a-fA-F]{6})/)?.[1];

const paper = token("paper");
const line = token("line");
const muted = token("muted");
const panel = ruleBody(".relay-panel").match(/background:\s*(#[0-9a-fA-F]{6})/)?.[1];
const plannedWeight = Number(ruleBody('.lab-card[data-lab-state="planned"]').match(/color-mix\(in srgb, var\(--paper\) (\d+)%, var\(--line\)\)/)?.[1]);
const planned = paper && line && plannedWeight ? mixSrgb(plannedWeight / 100, paper, line) : undefined;

test("resolves the surfaces the contrast checks use from the stylesheet", () => {
  assert.match(paper ?? "", /^#/, "--paper is defined");
  assert.match(line ?? "", /^#/, "--line is defined");
  assert.match(muted ?? "", /^#/, "--muted is defined");
  assert.match(panel ?? "", /^#/, "the lab panel background is a literal color");
  assert.ok(plannedWeight > 0, "the planned lab card mixes the paper with the line color");
});

test("keeps --muted text at 4.5:1 or better on paper, panels, and the planned lab card", () => {
  for (const [surface, background] of [["paper", paper], ["lab panel", panel], ["planned lab card", planned]]) {
    assert.ok(
      contrast(muted, background) >= 4.5,
      `--muted ${muted} on ${surface} ${background} is ${contrast(muted, background).toFixed(2)}:1, below 4.5:1`,
    );
  }
});

test("keeps the text-colored status states at 4.5:1 or better on every surface they sit on", () => {
  // Dots and backgrounds keep their status colors; only the text rules below are darkened.
  const statusText = [
    '.relay-wizard-actions p[data-state="delivered"]',
    '.relay-wizard-actions p[data-state="failed"]',
    '.relay-message-form p[data-state="delivered"]',
    '.relay-message-form p[data-state="failed"]',
    '.relay-message-form p[data-state="unconfirmed"]',
    '.relay-route-step[data-state="complete"] [data-route-state]',
    '.relay-route-step[data-state="failed"] [data-route-state]',
    '.relay-route-step[data-state="unknown"] [data-route-state]',
  ];
  for (const selector of statusText) {
    const color = declaredColor(ruleBody(selector));
    assert.ok(color, `${selector} declares a text color`);
    for (const [surface, background] of [["paper", paper], ["lab panel", panel], ["planned lab card", planned]]) {
      assert.ok(
        contrast(color, background) >= 4.5,
        `${selector} ${color} on ${surface} ${background} is ${contrast(color, background).toFixed(2)}:1, below 4.5:1`,
      );
    }
  }
});

test("keeps the unknown route marker's dashed outline at 3:1 or better on paper, so its shape cue is visible", () => {
  // The marker is not text-only: its shape (dashed outline) and its label carry the state, and the outline must stay visible.
  const body = ruleBody('.relay-route-step[data-state="unknown"] .relay-route-marker');
  const outline = body.match(/border-color:\s*(#[0-9a-fA-F]{6})/)?.[1];
  assert.match(body, /border-style:\s*dashed/, "the unknown marker is dashed, unlike the solid failed and complete markers");
  assert.ok(outline, "the unknown marker declares its outline color");
  assert.ok(
    contrast(outline, paper) >= 3,
    `unknown marker outline ${outline} on paper ${paper} is ${contrast(outline, paper).toFixed(2)}:1, below 3:1`,
  );
});

test("keeps the animated eyebrow on the same muted text token", async () => {
  const page = await readSource("src/components/PortfolioPage.astro");
  const eyebrowColor = page.match(/<ShinyText client:load text=\{content\.hero\.eyebrow\} color="(#[0-9a-fA-F]{6})"/)?.[1];

  assert.equal(eyebrowColor, muted, "the hero eyebrow uses the --muted value so its base color stays readable");
});
