"""Explicitly assign legacy unowned data to an existing recruiter workspace."""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from database import init_db, get_conn, get_user
from config import DB_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply after creating a database backup; without this flag only preview counts",
    )
    args = parser.parse_args()
    init_db()
    owner = get_user(args.owner.lower().strip())
    if not owner or owner["role"] != "recruiter":
        parser.error("Owner must be an existing recruiter.")
    with get_conn() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table} WHERE owner_id IS NULL").fetchone()[
                0
            ]
            for table in ("candidates", "jd_runs")
        }
    print("Unowned records:", counts)
    if not args.apply:
        return
    backup = Path(DB_PATH).with_name(
        "recruiter-before-ownership-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        + ".db"
    )
    with sqlite3.connect(DB_PATH) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    with get_conn() as conn:
        for table in counts:
            conn.execute(
                f"UPDATE {table} SET owner_id=? WHERE owner_id IS NULL",
                (owner.get("workspace_id") or owner["username"],),
            )
    print("Assigned legacy records. Backup:", backup)


if __name__ == "__main__":
    main()
