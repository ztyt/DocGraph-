from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from docgraph_sidecar.core.db import initialize_database, migration_result_json


def main() -> None:
    parser = argparse.ArgumentParser(description="DocGraph sidecar")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the local sidecar service")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8765, type=int)

    init_parser = subparsers.add_parser("init-db", help="Initialize the local SQLite database")
    init_parser.add_argument("--data-dir", type=Path)
    init_parser.add_argument("--db-path", type=Path)

    args = parser.parse_args()

    if args.command == "init-db":
        result = initialize_database(data_dir=args.data_dir, db_path=args.db_path)
        print(migration_result_json(result))
        return

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    uvicorn.run(
        "docgraph_sidecar.api:app",
        host=host,
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
