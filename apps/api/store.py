import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("AFS_DATA", ROOT / "data")).resolve()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "studio.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS artifacts (
      id TEXT PRIMARY KEY, role TEXT NOT NULL, name TEXT NOT NULL,
      relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL,
      created_at TEXT NOT NULL, metadata TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reviews (
      id TEXT PRIMARY KEY, candidate TEXT NOT NULL, golden TEXT NOT NULL,
      created_at TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL, payload TEXT NOT NULL, error TEXT);
    """)
    return db


def safe_path(relative):
    path = (DATA / relative).resolve()
    if not path.is_relative_to(DATA) or path == DATA:
        raise ValueError("Artifact path escapes data root")
    return path


def artifact(row):
    result = dict(row)
    result["metadata"] = json.loads(result["metadata"])
    result["url"] = f"/api/artifacts/{result['id']}/file"
    return result


def get_artifact(identifier):
    with connect() as db:
        row = db.execute("SELECT * FROM artifacts WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise KeyError(identifier)
    return artifact(row)


def add_artifact(path, role, name, metadata):
    path = Path(path).resolve()
    relative = path.relative_to(DATA).as_posix()
    identifier = uuid.uuid4().hex
    with connect() as db:
        db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)", (
            identifier, role, name, relative, digest(path), now(), json.dumps(metadata)))
    return get_artifact(identifier)
