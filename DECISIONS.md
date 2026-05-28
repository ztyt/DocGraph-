# DocGraph V4 Decisions

This file records early project decisions. New decisions should be appended with date, status, context, decision, consequences, and rollback notes when relevant.

## Decision Template

```text
## ADR-000N: Short Title

Date: YYYY-MM-DD
Status: Proposed | Accepted | Superseded

Context:
- What problem or constraint forced the decision?

Decision:
- What are we choosing?

Consequences:
- What becomes easier?
- What becomes harder?

Rollback:
- How can this decision be reversed or softened?
```

## ADR-0001: Local-First Default

Date: 2026-05-28
Status: Accepted

Context:
- DocGraph indexes private work documents on the user's machine.
- Trust depends on the system being useful without uploading source text.

Decision:
- The default mode is local.
- LLM, OCR, vector search, reranker, and watchdog capabilities are optional enhancements controlled by feature flags.
- FTS-only search, file details, and opening original files must work without enhanced features.

Consequences:
- The MVP remains installable and privacy-preserving.
- Some advanced understanding features arrive later or run with reduced accuracy at first.

Rollback:
- Individual enhanced features may be enabled per user setting or build profile, but local mode remains the baseline.

## ADR-0002: Preserve Original Files

Date: 2026-05-28
Status: Accepted

Context:
- The system scans user folders that may contain important personal or work files.
- Any mutation of source files creates unacceptable trust and recovery risks.

Decision:
- DocGraph must not move, delete, rename, rewrite, or normalize user source files.
- The index stores metadata, hashes, parsed chunks, and derived records in the local database.
- File open and reveal actions must target the existing source path.

Consequences:
- Index corruption cannot damage source files.
- The system must handle deleted, moved, or inaccessible files as external state changes.

Rollback:
- No rollback path is planned for this principle.

## ADR-0003: SQLite as the Single Local Source of Truth

Date: 2026-05-28
Status: Accepted

Context:
- The product needs local search, task status, derived profiles, entities, related-file cache, audit logs, and snapshots.
- The first implementation should avoid distributed local state.

Decision:
- Use SQLite as the single local source of truth.
- Enable WAL, busy timeouts, short transactions, and migration tracking.
- Use SQLite FTS5 for the first search backend.

Consequences:
- The initial system is easier to package and back up.
- Heavy vector or graph backends must be optional and synchronized carefully if introduced later.

Rollback:
- Later retrieval backends can be added behind interfaces and feature flags while SQLite remains the durable index.

## ADR-0004: Search Before Graph

Date: 2026-05-28
Status: Accepted

Context:
- Users need to find documents reliably before graph exploration is valuable.
- Graph quality depends on parsed chunks, profiles, entities, and relation scoring.

Decision:
- M0-M5 prioritize the local search loop.
- Graph UI and cluster views are delayed until relation quality can be explained and evaluated.

Consequences:
- Early releases are less visually ambitious but more useful.
- Graph work has better data foundations when it starts.

Rollback:
- A limited debug graph may be added for development, but it must not become the primary user workflow before M11.

## ADR-0005: Measurable Algorithms

Date: 2026-05-28
Status: Accepted

Context:
- Document profile, entity extraction, related-file scoring, and graph grouping can appear plausible while being wrong.

Decision:
- Algorithm changes must include or update evaluation fixtures when they affect ranking, extraction, profile generation, or graph quality.
- Metrics include parse success rate, search Recall@K, MRR, profile accept rate, evidence coverage, related Precision@5, cluster purity, and reason faithfulness.

Consequences:
- Algorithm work has a slower but safer feedback loop.
- The project avoids tuning by impression alone.

Rollback:
- Metrics may evolve as fixtures mature, but algorithm work must remain measurable.

