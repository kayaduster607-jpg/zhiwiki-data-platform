"""Consistent snapshots and fail-closed restore into a new, empty directory."""

import json
import re
import shutil
import sqlite3
import time
from contextlib import closing

from .common import encode, safe_path
from .database import ServiceDatabase
from .persistent_index import checksum


def _required_artifacts(connection):
    """Derive the complete immutable file set from the backed-up database."""
    uploads = [row[0] for row in connection.execute(
        "SELECT DISTINCT file_hash FROM team_revisions WHERE filename<>'legacy'"
    )]
    indexes = [row[0] for row in connection.execute(
        "SELECT artifact FROM team_kbs WHERE artifact IS NOT NULL"
    )]
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in uploads):
        raise ValueError("Invalid upload artifact reference")
    if any(not isinstance(value, str) or not re.fullmatch(r"indexes/[0-9a-f]{64}\.sqlite3", value) for value in indexes):
        raise ValueError("Invalid index artifact reference")
    return {"knowledge.sqlite3", *("uploads/" + value for value in uploads), *indexes}


def _verify_database(path):
    """Check the snapshot database without creating or modifying sidecar files."""
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Snapshot database failed integrity verification")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Snapshot database failed foreign key verification")
            return _required_artifacts(connection)
    except sqlite3.DatabaseError as error:
        raise ValueError("Invalid snapshot database") from error


def _content_address(relative):
    """Return the SHA-256 encoded in an immutable artifact's filename."""
    if relative.startswith("uploads/"):
        return relative.split("/", 1)[1]
    if relative.startswith("indexes/"):
        return relative.split("/", 1)[1].removesuffix(".sqlite3")
    return None


def _verify_member(root, relative, expected):
    """Reject links, path escapes, corruption, and mismatched content addresses."""
    raw = root / relative
    if raw.is_symlink() or raw.parent.is_symlink():
        raise ValueError("Unsafe backup member")
    path = safe_path(raw)
    if root not in path.parents or not path.is_file():
        raise ValueError("Unsafe or missing backup member")
    actual = checksum(path)
    if actual != expected:
        raise ValueError("Backup checksum mismatch")
    address = _content_address(relative)
    if address is not None and actual != address:
        raise ValueError("Backup artifact content address mismatch")
    return path


def backup_workspace(settings, destination):
    database = ServiceDatabase(settings)
    output = safe_path(destination)
    if output == database.root or database.root in output.parents:
        raise ValueError("Snapshot must be outside the live data directory")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Use a new empty snapshot directory")
    started = time.monotonic()
    target = output / "knowledge.sqlite3"
    with closing(database.connect()) as source, closing(sqlite3.connect(str(target))) as backup:
        source.backup(backup)
    # The database snapshot determines the complete immutable artifact set.
    paths = ["knowledge.sqlite3"]
    for relative in sorted(_verify_database(target) - {"knowledge.sqlite3"}):
        source = database.artifact_path(relative)
        if not source.is_file():
            raise ValueError("Snapshot source artifact missing: " + relative)
        if checksum(source) != _content_address(relative):
            raise ValueError("Snapshot source artifact content address mismatch")
        copied = output / relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, copied)
        if checksum(copied) != _content_address(relative):
            raise ValueError("Snapshot artifact changed while copying")
        paths.append(relative)
    manifest = {"format": 1, "created_at": time.time(), "files": {relative: checksum(output / relative) for relative in paths}}
    (output / "manifest.json").write_text(encode(manifest), encoding="utf-8")
    return {"snapshot": str(output), "files": len(paths), "seconds": round(time.monotonic() - started, 3)}


def restore_workspace(snapshot, destination):
    source, target = safe_path(snapshot), safe_path(destination)
    if target == source or source in target.parents or target in source.parents:
        raise ValueError("Restore into a separate empty directory")
    manifest_path = source / 'manifest.json'
    if manifest_path.is_symlink():
        raise ValueError("Unsafe backup manifest")
    manifest_path = safe_path(manifest_path)
    if source not in manifest_path.parents:
        raise ValueError("Unsafe backup manifest")
    if manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError('Backup manifest too large')
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("format") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported backup manifest")
    files = manifest["files"]
    if "knowledge.sqlite3" not in files or any(not isinstance(name, str) or not isinstance(value, str)
                                                or not re.fullmatch(r"[0-9a-f]{64}", value)
                                                for name, value in files.items()):
        raise ValueError("Unsupported backup manifest")
    # Verify the database before trusting its list of required immutable files.
    database = _verify_member(source, "knowledge.sqlite3", files["knowledge.sqlite3"])
    required = _verify_database(database)
    if set(files) != required:
        raise ValueError("Backup manifest does not match database references")
    verified = []
    for relative, expected in files.items():
        path = _verify_member(source, relative, expected)
        output = safe_path(target / relative)
        if target not in output.parents:
            raise ValueError("Unsafe backup member")
        verified.append((path, output, expected))
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Restore never overwrites an existing workspace")
    started = time.monotonic()
    for path, output, expected in verified:
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        if checksum(output) != expected:
            raise ValueError("Backup member changed while restoring")
    with closing(sqlite3.connect(str(target / "knowledge.sqlite3"))) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Restored database failed integrity verification")
    return {"restored": str(target), "files": len(verified), "seconds": round(time.monotonic() - started, 3)}


def cleanup(settings):
    """Expire only short-lived receipts/keys; published/history content is kept."""
    database = ServiceDatabase(settings)
    return expire_ephemeral(database)


def expire_ephemeral(database):
    """Safe automatic expiry; audit/history/source retention is a separate policy."""
    with database.tx(write=True) as connection:
        receipts = connection.execute("DELETE FROM team_receipts WHERE expires<?", (time.time(),)).rowcount
        keys = connection.execute("DELETE FROM team_idempotency WHERE expires<?", (time.time(),)).rowcount
    return {"expired_receipts": receipts, "expired_keys": keys, "source_history_deleted": False}
