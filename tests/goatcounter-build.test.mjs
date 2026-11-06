import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import test from "node:test";

// `npm test` builds dist/ without a GoatCounter code, so the positive branch never reaches the shipped build. This test runs a
// real production build with a fixed code into a temporary directory, so dist/ is never touched.
const projectRoot = fileURLToPath(new URL("../", import.meta.url));
const astroBin = join(projectRoot, "node_modules/astro/bin/astro.mjs");
const distDir = join(projectRoot, "dist");
const fixedCode = "ci-test";
const execFileAsync = promisify(execFile);

const goatcounterScript = /<script\b[^>]*\ssrc="https:\/\/gc\.zgo\.at\/count\.js"[^>]*><\/script>/g;
// Anything that would load or report to GoatCounter. Prose that merely names the
// product or its GOATCOUNTER_CODE variable (for example on the static architecture
// pages) is documentation, not a script, so it is allowed.
const goatcounterAnyReference = /data-goatcounter|gc\.zgo\.at|\b[a-z0-9-]+\.goatcounter\.com/i;

const htmlPagesIn = async (outDir) => {
  const files = await readdir(outDir, { recursive: true });
  const pages = files.filter((file) => file.endsWith(".html")).sort();
  return Promise.all(pages.map(async (file) => [file, await readFile(join(outDir, file), "utf8")]));
};

// public/ holds static HTML copied verbatim (legacy redirect stubs and the architecture pages), so it never goes through the layout.
const staticPublicFiles = new Set(await readdir(join(projectRoot, "public"), { recursive: true }));
const renderedPagesIn = async (outDir) => (await htmlPagesIn(outDir)).filter(([file]) => !staticPublicFiles.has(file));

test("a production build with a GoatCounter code renders exactly one correctly attributed script on every page", async (t) => {
  const outDir = await mkdtemp(join(tmpdir(), "goatcounter-build-"));
  t.after(() => rm(outDir, { recursive: true, force: true }));

  // A failed build rejects here, so the test fails with the build's own output.
  await execFileAsync(process.execPath, [astroBin, "build", "--outDir", outDir], {
    cwd: projectRoot,
    env: { ...process.env, PUBLIC_GOATCOUNTER_CODE: fixedCode },
    maxBuffer: 16 * 1024 * 1024,
    timeout: 240_000,
  });

  const pages = await renderedPagesIn(outDir);
  assert.ok(pages.length >= 6, `the build rendered its Astro pages, got ${pages.length}`);

  for (const [file, page] of pages) {
    const tags = page.match(goatcounterScript) ?? [];
    assert.equal(tags.length, 1, `${file} renders exactly one GoatCounter script`);
    assert.match(tags[0], /\sasync\b/, `${file} loads GoatCounter without blocking the page`);
    assert.match(tags[0], new RegExp(`\\sdata-goatcounter="https://${fixedCode}\\.goatcounter\\.com/count"`), `${file} reports to this site's endpoint`);
    assert.equal([...page.matchAll(/data-goatcounter="/g)].length, 1, `${file} names one GoatCounter endpoint`);
  }
});

test("the shipped dist renders no GoatCounter when the test environment sets no site code", { skip: process.env.PUBLIC_GOATCOUNTER_CODE ? "PUBLIC_GOATCOUNTER_CODE is set, so the shipped build may carry a code" : false }, async () => {
  const pages = await htmlPagesIn(distDir);
  assert.ok(pages.length >= 6, `dist/ has its pages, got ${pages.length}`);

  for (const [file, page] of pages) {
    assert.doesNotMatch(page, goatcounterAnyReference, `${file} carries no GoatCounter reference without a site code`);
  }
});
