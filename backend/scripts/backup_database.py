"""Create a consistent SQLite backup before an explicitly approved migration."""

import argparse
import sqlite3
from pathlib import Path


def create_backup(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Backup destination must differ from the source database.")
    if not source.is_file():
        raise FileNotFoundError(f"Source database does not exist: {source}")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = source.as_uri() + "?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as source_db:
        with sqlite3.connect(destination) as backup_db:
            source_db.backup(backup_db)
            result = backup_db.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise sqlite3.DatabaseError(f"Backup integrity check failed: {result}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="SQLite database to copy")
    parser.add_argument("destination", type=Path, help="New backup file (must not already exist)")
    args = parser.parse_args()
    create_backup(args.source, args.destination)
    print(f"Verified SQLite backup created: {args.destination.resolve()}")


if __name__ == "__main__":
    main()
