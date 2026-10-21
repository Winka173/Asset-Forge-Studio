import hashlib
import json
import os
import sqlite3
import uuid
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get('AFS_RESOURCE_ROOT',Path(__file__).resolve().parents[2])).resolve()
WORKSPACE = Path(os.environ.get('AFS_WORKSPACE',ROOT)).resolve()
CONFIG_ROOT = Path(os.environ.get('LOCALAPPDATA',Path.home() / '.local/share')) / 'AssetForgeStudio'
DATA = Path(os.environ.get("AFS_DATA", CONFIG_ROOT / 'Library' if os.environ.get('AFS_DESKTOP')=='1' else WORKSPACE / "data")).resolve()
SCHEMA_LOCK=threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def connect():
    # API requests and the scheduler can open a new library simultaneously.
    # Serialize initialization; normal connections do not repeat WAL/DDL changes.
    with SCHEMA_LOCK:
        return _connect()


def _connect():
    DATA.mkdir(parents=True, exist_ok=True)
    existed=(DATA/'studio.sqlite').exists()
    db = sqlite3.connect(DATA / "studio.sqlite", timeout=30)
    db.row_factory = sqlite3.Row
    if db.execute('PRAGMA user_version').fetchone()[0]>=3:return db
    db.execute("PRAGMA journal_mode=WAL")
    if existed and db.execute('PRAGMA user_version').fetchone()[0] < 3:
        backup_dir=DATA/'backups';backup_dir.mkdir(parents=True,exist_ok=True)
        backup_path=backup_dir/'studio-before-schema-v3.sqlite'
        if not backup_path.exists():
            target=sqlite3.connect(backup_path)
            try:db.backup(target)
            finally:target.close()
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
    CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, payload TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS drafts (project_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS studio_requests (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, response TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS asset_exports (id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS migrations (id TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, project_id TEXT NOT NULL, payload TEXT NOT NULL);
    """)
    columns = {r['name'] for r in db.execute('PRAGMA table_info(artifacts)')}
    for column in ('project_id', 'asset_id'):
        if column not in columns:
            db.execute(f'ALTER TABLE artifacts ADD COLUMN {column} TEXT')
    if not db.execute("SELECT 1 FROM migrations WHERE id='studio_v1'").fetchone():
        # Only migrate real pre-project artifacts; fresh libraries stay empty.
        rows = db.execute('SELECT id,role,metadata FROM artifacts WHERE project_id IS NULL').fetchall()
        if rows:
            config = json.loads((ROOT / 'presets/runavelle.json').read_text(encoding='utf-8'))
            project = dict(id='runavelle', name='Runavelle', description='Archer Tower quality benchmark',
                           art_bible=config, palette=[], material_language='', default_style='', units='m',
                           target_height_m=10, export_settings={}, cover_artifact_id=None)
            db.execute('INSERT OR IGNORE INTO projects VALUES (?,?,0)', ('runavelle', json.dumps(project)))
            references = [r['id'] for r in rows if r['role'] == 'concept']
            asset = dict(id='archer_tower_t3', project_id='runavelle', name='Archer Tower T3', prompt='',
                         category='Architecture', favorite=False, status='Candidate', master_artifact_id=None,
                         reference_ids=references, settings={}, approvals=[], created_at=now(), updated_at=now())
            db.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?)', (asset['id'], 'runavelle', json.dumps(asset)))
            db.execute("UPDATE artifacts SET project_id='runavelle',asset_id='archer_tower_t3' WHERE project_id IS NULL")
        db.execute("INSERT INTO migrations VALUES ('studio_v1')")
    db.commit()
    db.execute('PRAGMA user_version=3')
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
    parent = None
    if metadata.get('parent_id'):
        try: parent = get_artifact(metadata['parent_id'])
        except KeyError: pass
    project_id = metadata.get('project_id') or (parent or {}).get('project_id') or 'runavelle'
    asset_id = metadata.get('asset_id') or (parent or {}).get('asset_id')
    with connect() as db:
        db.execute("INSERT INTO artifacts (id,role,name,relative_path,sha256,created_at,metadata,project_id,asset_id) VALUES (?,?,?,?,?,?,?,?,?)", (
            identifier, role, name, relative, digest(path), now(), json.dumps(metadata), project_id, asset_id))
    return get_artifact(identifier)
