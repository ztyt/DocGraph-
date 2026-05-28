# DocGraph V4

DocGraph V4 is a local-first desktop assistant for turning scattered documents into a searchable, explainable, measurable, and rollback-safe work knowledge map.

This repository starts from the V4 execution manual. The first delivery target is not a full knowledge graph. The first target is a reliable local document search loop:

1. Start the desktop shell and local sidecar.
2. Scan user-selected folders without moving original files.
3. Parse common office documents into evidence chunks.
4. Search with SQLite FTS5.
5. Open the original file or reveal its folder.

Graph, LLM, OCR, vector search, reranking, and file watchers are later-stage enhancements guarded by feature flags.

## Core Principles

- Do not move, delete, rename, or rewrite user source files.
- Default to local mode. External LLM, OCR, vector search, and watchdog features must be explicitly enabled by feature flags.
- Search comes first. FTS-only search must continue to work when enhanced features fail or are disabled.
- Long-running work must go through the task queue and must not block the UI or API requests.
- Database changes require migrations, rollback notes, and test data.
- API changes require a unified response envelope, error codes, tests, and matching TypeScript types.
- Frontend pages must cover loading, empty, error, and success states.
- Algorithms must be explainable and backed by evidence chunks.
- Releases and migrations must be observable and rollback-safe.

## Repository Layout

```text
.
+-- apps/
|   +-- desktop/          # Tauri + React + TypeScript desktop app
|   +-- sidecar/          # Local Python sidecar service
+-- packages/
|   +-- shared/           # Shared API/domain types and contracts
+-- fixtures/            # Test documents and evaluation datasets
+-- docs/                # Architecture notes, ADRs, release notes
+-- scripts/             # Development, diagnostics, and packaging scripts
+-- README.md
+-- DECISIONS.md
+-- CONTRIBUTING.md
```

This skeleton is intentionally light. Business scanning, parsing, database, and search code starts in later milestones.

## Milestones

| Milestone | Goal | Required Delivery | Explicitly Not Doing |
| --- | --- | --- | --- |
| M0 Project Rules | Establish repository constraints and development constitution. | README, decisions log, contribution rules, phase boundaries. | Business features. |
| M1 Shell and Sidecar | Desktop can start and show sidecar health. | Tauri shell, React app, health check, settings shell. | Scanning and parsing. |
| M2 SQLite Base | Create single local database and migrations. | Core schema, WAL, snapshots, migration runner. | Profile and embedding execution. |
| M3 Scan Center | Safely scan selected folders into the database. | Folder selection, ignore rules, task queue, progress UI. | Always-on watchdog. |
| M4 Parsing and Chunking | Parse common documents into structured chunks. | TXT, PDF, DOCX, XLSX, PPTX parsers and chunking. | Default OCR. |
| M5 FTS Search Loop | Search, inspect evidence, and open files. | FTS5 index, search API, search UI, file detail basics. | Vector search. |
| M6 Document Profile | Generate evidence-backed document profiles. | Rule-based central idea, role, confidence, evidence chunks. | Cloud LLM dependency. |
| M7 Entity Graph | Extract and normalize core entities. | PROJECT, ORG, LOCATION, DEVICE, MONEY, DATE, ID_CODE entities. | Complex reasoning. |
| M8 Related Files | Explain related documents with scored evidence. | Candidate recall, score breakdown, reasons, cache. | Full pairwise computation. |
| M9 Evaluation Suite | Measure search, profile, related, and graph quality. | Evaluation fixtures, metrics, reports. | Subjective tuning only. |
| M10 Hybrid Retrieval | Add optional RRF, vector search, and reranker interfaces. | Feature-flagged retrieval backends. | Blocking core search on heavy dependencies. |
| M11 Local Graph | Explain relationships with bounded local graphs. | Ego graph, clusters, layout constraints. | Full-library graph rendering. |
| M12 Productization | Package, upgrade, rollback, and diagnose. | Installer, snapshots, diagnostics, release checklist. | Uploading raw user documents by default. |

## Development Commands

Enable pnpm through Corepack first if `pnpm` is not available on the machine:

```powershell
corepack enable
corepack prepare pnpm@9.15.4 --activate
```

Then use the workspace commands:

```powershell
# Install dependencies
pnpm install

# Print current development setup guidance
pnpm dev

# Run skeleton and sidecar tests
pnpm test

# Run workspace checks
pnpm lint
pnpm format:check

# Run sidecar tests only without installing dev dependencies
python -m unittest discover apps/sidecar/tests

# Initialize the local SQLite database
python apps/sidecar/app.py init-db
```

## Acceptance for the Current Skeleton

- `README.md`, `DECISIONS.md`, and `CONTRIBUTING.md` exist at the project root.
- `apps/desktop`, `apps/sidecar`, `packages/shared`, `fixtures`, `docs`, and `scripts` exist.
- Root scripts provide basic `dev`, `lint`, `test`, and `format:check` commands.
- `node scripts/check-workspace.mjs` passes.
- `python -m unittest discover apps/sidecar/tests` passes.
- No scanning, parsing, database, search, LLM, OCR, vector, or graph business behavior is implemented yet.
