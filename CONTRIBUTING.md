# Contributing to DocGraph V4

DocGraph V4 is built in small, testable milestones. Each change should be scoped to the current milestone and should keep the FTS-only local search path healthy.

## Working Rules

- Keep source files safe: never move, delete, rename, or rewrite user documents.
- Keep local mode useful: LLM, OCR, vector, reranker, and watchdog features are optional.
- Keep work observable: log important task state, errors, and migration outcomes.
- Keep changes reversible: database changes need migrations, rollback notes, and snapshots where applicable.
- Keep interfaces typed: API payload changes must update shared TypeScript types.
- Keep UI states complete: every page or feature surface needs loading, empty, error, and success states.
- Keep algorithms evidenced: explanations must point back to chunks, entities, or stored scoring features.

## Change Checklist

Before a change is complete, verify the relevant items:

- Scope matches the current milestone.
- New behavior has tests or a clear manual acceptance path.
- Errors use documented codes and user-readable messages.
- Long-running work goes through the task queue.
- Feature flags protect optional or heavy behavior.
- FTS-only search still works when enhanced features are disabled.
- Documentation is updated when commands, schema, APIs, or user-visible behavior change.

## Database Changes

Every database change must include:

- A forward migration.
- A rollback or recovery note.
- Test data or fixtures.
- A migration id recorded in schema metadata.
- A check that migrations can be run repeatedly without corrupting existing data.

SQLite settings required by default:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
```

## API Changes

All API responses use the same envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "trace_id": "trace-id",
  "elapsed_ms": 32
}
```

Failed responses use:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "User-readable message",
    "retryable": false,
    "details": {}
  },
  "trace_id": "trace-id",
  "elapsed_ms": 32
}
```

API changes must include tests, error codes, and shared TypeScript type updates.

## Frontend Changes

Frontend work should follow the planned information architecture:

- Home
- Scan
- Search
- File Detail
- Profile
- Entities
- Graph
- Evaluation
- Settings
- Audit

Do not make graph views the default entry point before the search loop is stable. Every page must handle loading, empty, error, and success states.

## Algorithm Changes

Algorithm changes include parser behavior, chunking, profile generation, entity extraction, related-file scoring, retrieval ranking, reranking, clustering, and graph layout.

Each algorithm change must include:

- Evaluation fixtures or an update to existing fixtures.
- Metrics affected by the change.
- Evidence records that explain outputs.
- A feature flag when the change introduces heavy dependencies or uncertain behavior.

## Development Commands

These commands become active once the monorepo skeleton is created:

```powershell
pnpm install
pnpm dev
pnpm test
pnpm lint
pnpm format:check
python -m pytest apps/sidecar/tests
```

## Pull Request or Milestone Summary

Each completed milestone should report:

- Files changed.
- What was implemented.
- Commands run.
- Test results.
- Manual acceptance steps.
- Explicit non-goals for the milestone.

## Current Non-Goals

Until the relevant milestone starts, do not implement:

- Business scanning or parsing before M3/M4.
- Vector search before M10.
- LLM or OCR as required dependencies.
- Full-library graph rendering.
- Full pairwise related-file computation.
- Always-on filesystem watching.
- Uploading raw user documents by default.

