# Database Migrations

DocGraph migrations are packaged under `apps/sidecar/docgraph_sidecar/migrations` and are applied in filename order.

## Current Version

- `001_init`: creates `schema_meta`.
- `002_v4_schema`: creates the V4 Alpha schema tables and indexes.
- `003_task_queue_contract`: adds the explicit `retry_count` field and normalizes queued task status.
- `004_scan_jobs`: records scan job state, progress counters, pause/resume timestamps, and the linked queue task.

## Apply

```powershell
python apps/sidecar/app.py init-db
```

For a test or isolated workspace:

```powershell
python apps/sidecar/app.py init-db --data-dir .docgraph\schema-smoke
```

## Rollback Notes

No destructive rollback migration is provided for `002_v4_schema` because this stage only creates empty tables and indexes. To roll back before user data exists, delete the test or local database file and re-run migrations from the desired commit:

```powershell
Remove-Item .docgraph\schema-smoke\docgraph.sqlite
```

After user data exists, rollback must be snapshot-based rather than table-dropping. Use `POST /api/db/snapshot` before applying risky migrations and `POST /api/db/restore/{snapshot_id}` to return to a known database copy.

## Snapshots

Database snapshots copy only the local SQLite index and `settings.json` when it exists. They do not copy, move, delete, rename, or rewrite user source documents.

Snapshot APIs:

- `GET /api/db/status`
- `POST /api/db/snapshot`
- `POST /api/db/restore/{snapshot_id}`

Snapshots are stored under the configured DocGraph data directory:

```text
snapshots/{snapshot_id}/docgraph.sqlite
snapshots/{snapshot_id}/settings.json
```

Restore replaces the local index database with the selected snapshot and restores the snapshot settings file when present. SQLite WAL/SHM sidecar files are removed during restore so SQLite can recreate them cleanly.
