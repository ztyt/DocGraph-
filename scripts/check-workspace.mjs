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
  "apps/desktop/src/pages/FilesPage.tsx",
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
  "apps/sidecar/docgraph_sidecar/core/files.py",
  "apps/sidecar/docgraph_sidecar/core/snapshots.py",
  "apps/sidecar/docgraph_sidecar/core/scan_jobs.py",
  "apps/sidecar/docgraph_sidecar/core/tasks.py",
  "apps/sidecar/docgraph_sidecar/indexer/__init__.py",
  "apps/sidecar/docgraph_sidecar/indexer/fts.py",
  "apps/sidecar/docgraph_sidecar/parser/__init__.py",
  "apps/sidecar/docgraph_sidecar/parser/base.py",
  "apps/sidecar/docgraph_sidecar/parser/docx.py",
  "apps/sidecar/docgraph_sidecar/parser/errors.py",
  "apps/sidecar/docgraph_sidecar/parser/pdf.py",
  "apps/sidecar/docgraph_sidecar/parser/pptx.py",
  "apps/sidecar/docgraph_sidecar/parser/registry.py",
  "apps/sidecar/docgraph_sidecar/parser/structure_chunker.py",
  "apps/sidecar/docgraph_sidecar/parser/text.py",
  "apps/sidecar/docgraph_sidecar/parser/xlsx.py",
  "apps/sidecar/docgraph_sidecar/scanner/ignore_rules.py",
  "apps/sidecar/docgraph_sidecar/scanner/metadata.py",
  "apps/sidecar/docgraph_sidecar/retrieval/__init__.py",
  "apps/sidecar/docgraph_sidecar/retrieval/fts_search.py",
  "apps/sidecar/docgraph_sidecar/workers/__init__.py",
  "apps/sidecar/docgraph_sidecar/workers/parse_worker.py",
  "apps/sidecar/docgraph_sidecar/migrations/001_init.sql",
  "apps/sidecar/docgraph_sidecar/migrations/002_v4_schema.sql",
  "apps/sidecar/docgraph_sidecar/migrations/003_task_queue_contract.sql",
  "apps/sidecar/docgraph_sidecar/migrations/004_scan_jobs.sql",
  "apps/sidecar/tests/test_skeleton.py",
  "apps/sidecar/tests/test_db.py",
  "packages/shared/package.json",
  "packages/shared/src/index.ts",
  "fixtures/README.md",
  "docs/README.md",
  "docs/database-migrations.md",
  "scripts/generate-basic-fixtures.py",
  "fixtures/basic_docs/expected_search.json",
  "fixtures/basic_docs/alpha_notes.txt",
  "fixtures/basic_docs/alpha_contract.docx",
  "fixtures/basic_docs/alpha_budget.xlsx",
  "fixtures/basic_docs/alpha_status.pptx",
  "fixtures/basic_docs/alpha_brief.pdf",
  "fixtures/basic_docs/empty.txt",
  "fixtures/basic_docs/bad_file.bin",
  "apps/sidecar/tests/test_fixtures.py",
  "apps/sidecar/tests/test_files_api.py",
  "apps/sidecar/tests/test_files_catalog.py",
  "apps/sidecar/tests/test_fts_indexer.py",
  "apps/sidecar/tests/test_ignore_rules.py",
  "apps/sidecar/tests/test_metadata_scanner.py",
  "apps/sidecar/tests/test_parser_registry.py",
  "apps/sidecar/tests/test_pdf_parser.py",
  "apps/sidecar/tests/test_pptx_parser.py",
  "apps/sidecar/tests/test_parse_worker.py",
  "apps/sidecar/tests/test_docx_parser.py",
  "apps/sidecar/tests/test_scan_api.py",
  "apps/sidecar/tests/test_scan_jobs.py",
  "apps/sidecar/tests/test_search_api.py",
  "apps/sidecar/tests/test_structure_chunker.py",
  "apps/sidecar/tests/test_tasks.py",
  "apps/sidecar/tests/test_text_parser.py",
  "apps/sidecar/tests/test_xlsx_parser.py",
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
