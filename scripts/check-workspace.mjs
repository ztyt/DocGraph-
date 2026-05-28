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
  "apps/desktop/src/apiClient.ts",
  "apps/desktop/src/App.tsx",
  "apps/desktop/src/router.tsx",
  "apps/desktop/src/components/layout/AppShell.tsx",
  "apps/desktop/src/components/system/ErrorBoundary.tsx",
  "apps/desktop/src/components/system/PageState.tsx",
  "apps/desktop/src/components/system/PlaceholderPage.tsx",
  "apps/desktop/src/pages/HomePage.tsx",
  "apps/desktop/src/pages/OnboardingPage.tsx",
  "apps/desktop/src/pages/ScanPage.tsx",
  "apps/desktop/src/pages/SearchPage.tsx",
  "apps/desktop/src/pages/FileDetailPage.tsx",
  "apps/desktop/src/pages/SettingsPage.tsx",
  "apps/desktop/src/pages/AuditPage.tsx",
  "apps/desktop/src-tauri/tauri.conf.json",
  "apps/sidecar/pyproject.toml",
  "apps/sidecar/app.py",
  "apps/sidecar/docgraph_sidecar/api.py",
  "apps/sidecar/docgraph_sidecar/logging.py",
  "apps/sidecar/docgraph_sidecar/responses.py",
  "apps/sidecar/docgraph_sidecar/settings_store.py",
  "apps/sidecar/docgraph_sidecar/core/db.py",
  "apps/sidecar/docgraph_sidecar/migrations/001_init.sql",
  "apps/sidecar/docgraph_sidecar/migrations/002_v4_schema.sql",
  "apps/sidecar/tests/test_skeleton.py",
  "apps/sidecar/tests/test_db.py",
  "packages/shared/package.json",
  "packages/shared/src/index.ts",
  "fixtures/README.md",
  "docs/README.md",
  "docs/database-migrations.md",
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
