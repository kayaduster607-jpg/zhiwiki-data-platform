"""Report potential orphan upload blobs without modifying data or reading contents."""

import argparse
from contextlib import closing
import json
import re
import sqlite3
import stat
import time
from pathlib import Path

from .common import load_service_settings, safe_path


def orphan_report(data_dir, grace_seconds=86400):
    """Find old hash-named files absent from revision references; never delete."""
    if type(grace_seconds) is not int or grace_seconds < 3600:
        raise ValueError("Grace period must be at least 3600 seconds")
    root = safe_path(data_dir)
    database, uploads = root / "knowledge.sqlite3", root / "uploads"
    if database.is_symlink() or not database.is_file():
        raise ValueError("An existing non-symlink workspace database is required")
    if uploads.is_symlink() or not uploads.is_dir():
        raise ValueError("An existing non-symlink uploads directory is required")
    cutoff = time.time() - grace_seconds
    candidates = []
    # Read-only mode prevents a typo in the data path from creating a database.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.execute("BEGIN")
        references = {row[0] for row in connection.execute(
            "SELECT DISTINCT file_hash FROM team_revisions WHERE file_hash IS NOT NULL"
        )}
        for path in uploads.iterdir():
            if not re.fullmatch(r"[0-9a-f]{64}", path.name):
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.name in references or info.st_mtime > cutoff:
                continue
            candidates.append({"hash": path.name, "size_bytes": info.st_size,
                               "last_modified_unix": info.st_mtime})
        connection.rollback()
    candidates.sort(key=lambda item: item["hash"])
    return {"mode": "report_only", "grace_seconds": grace_seconds,
            "candidate_count": len(candidates),
            "candidate_bytes": sum(item["size_bytes"] for item in candidates),
            "candidates": candidates,
            "warning": "Concurrent service activity may change references; candidates are not deletion approval."}


def main():
    parser = argparse.ArgumentParser(description="Report potential orphan uploads; no files are deleted")
    parser.add_argument("--config", required=True, help="Explicit service JSON configuration")
    parser.add_argument("--grace-hours", type=int, default=24)
    args = parser.parse_args()
    settings = load_service_settings(args.config)
    print(json.dumps(orphan_report(settings.data_dir, args.grace_hours * 3600), ensure_ascii=False))


if __name__ == "__main__":
    main()
