# Database Migrations

DocGraph migrations are packaged under `apps/sidecar/docgraph_sidecar/migrations` and are applied in filename order.

## Current Version

- `001_init`: creates `schema_meta`.
- `002_v4_schema`: creates the V4 Alpha schema tables and indexes.

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

After user data exists, rollback must be snapshot-based rather than table-dropping. The snapshot and restore workflow starts in `VC-007`.

