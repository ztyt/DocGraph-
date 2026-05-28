import { access, readFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();

const requiredPaths = [
  "README.md",
  "DECISIONS.md",
  "CONTRIBUTING.md",
  "package.json",
  "pnpm-workspace.yaml",
  "apps/desktop/package.json",
  "apps/desktop/src/App.tsx",
  "apps/desktop/src-tauri/tauri.conf.json",
  "apps/sidecar/pyproject.toml",
  "apps/sidecar/app.py",
  "apps/sidecar/tests/test_skeleton.py",
  "packages/shared/package.json",
  "packages/shared/src/index.ts",
  "fixtures/README.md",
  "docs/README.md",
  "scripts/dev-placeholder.mjs",
];

const missing = [];

for (const relativePath of requiredPaths) {
  try {
    await access(path.join(root, relativePath));
  } catch {
    missing.push(relativePath);
  }
}

const packageJson = JSON.parse(
  await readFile(path.join(root, "package.json"), "utf8"),
);

const requiredScripts = ["dev", "lint", "test", "format:check"];
const missingScripts = requiredScripts.filter(
  (scriptName) => !packageJson.scripts?.[scriptName],
);

if (missing.length > 0 || missingScripts.length > 0) {
  if (missing.length > 0) {
    console.error("Missing required paths:");
    for (const item of missing) console.error(`- ${item}`);
  }

  if (missingScripts.length > 0) {
    console.error("Missing required scripts:");
    for (const item of missingScripts) console.error(`- ${item}`);
  }

  process.exit(1);
}

console.log("Workspace skeleton check passed.");

