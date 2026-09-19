import { readFile, readdir } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve, relative, sep } from "node:path";

const root = resolve(".github");

async function filesIn(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? filesIn(path) : [path];
  }));
  return nested.flat();
}

function frontmatter(source, file) {
  const match = source.match(/^---\n([\s\S]*?)\n---\n/);
  if (!match) throw new Error(`${file}: missing YAML frontmatter`);
  const values = Object.fromEntries(match[1].split("\n").flatMap((line) => {
    const separator = line.indexOf(":");
    return separator === -1 ? [] : [[line.slice(0, separator).trim(), line.slice(separator + 1).trim().replace(/^"|"$/g, "")]];
  }));
  if (!values.description) throw new Error(`${file}: frontmatter requires description`);
  return values;
}

const files = await filesIn(root);
const markdownFiles = files.filter((file) => /\.(instructions|agent)\.md$|\/SKILL\.md$/.test(file));
for (const file of markdownFiles) {
  const source = await readFile(file, "utf8");
  const values = frontmatter(source, relative(process.cwd(), file));
  if (file.endsWith("SKILL.md")) {
    const expectedName = relative(resolve(".github/skills"), resolve(file, "..")).split(sep).at(-1);
    if (values.name !== expectedName) throw new Error(`${relative(process.cwd(), file)}: name must match ${expectedName}`);
  }
}

for (const file of files.filter((file) => file.endsWith(".json"))) JSON.parse(await readFile(file, "utf8"));
execFileSync(process.execPath, ["--check", ".github/scripts/ai-change-guard.mjs"], { stdio: "inherit" });
console.log(`Validated ${markdownFiles.length} AI customization files.`);