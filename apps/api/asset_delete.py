"""Permanently delete one asset and every file the app made for it (user-requested; there is no undo).

Removes: its jobs (unfinished ones are cancelled first) and their folders, every artifact file and row, library export
folders, the asset record and folder, its batch entry (an emptied batch goes too) and notifications. A delivery into
a game folder is removed only when asked, only for files whose checksum still matches what the app wrote, and the
game manifest entry is taken out with the same edited-manifest protection as delivery. Other assets are untouched.
"""
import hashlib
import json
import shutil
import time
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from . import store, studio, jobs

router = APIRouter(prefix='/api/asset-delete')


def _size(path):
    path = Path(path)
    if path.is_file(): return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob('*') if f.is_file()) if path.is_dir() else 0


def _inside(path, root):
    try: Path(path).resolve().relative_to(Path(root).resolve()); return True
    except ValueError: return False


def collect(asset_id):
    model = studio.asset(asset_id)
    from .export_profiles import _schema; _schema()  # delivery tables are created lazily
    with store.connect() as db:
        artifacts = [store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=?', (asset_id,))]
        deliveries = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM selective_exports WHERE asset_id=?', (asset_id,))]
        batches = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches WHERE project_id=?', (model['project_id'],))]
    owned = [j for j in jobs.listing() if j['payload'].get('asset_id') == asset_id]
    folders = [store.DATA / 'jobs' / j['id'] for j in owned if (store.DATA / 'jobs' / j['id']).is_dir()]
    files = [store.DATA / a['relative_path'] for a in artifacts]
    library_exports, game = [], []
    for d in deliveries:
        directory = Path(d.get('export_directory') or '')
        if not d.get('export_directory'): continue
        (library_exports if _inside(directory, store.DATA) else game).append(d)
    asset_dir = store.DATA / 'projects' / model['project_id'] / 'assets' / asset_id
    library_bytes = sum(_size(p) for p in {*folders, *files, *(Path(d['export_directory']) for d in library_exports), asset_dir})
    game_files = [Path(d['export_directory']) / f['name'] for d in game for f in d.get('files', []) if (Path(d['export_directory']) / f['name']).is_file()]
    return dict(model=model, artifacts=artifacts, owned=owned, folders=folders, files=files, library_exports=library_exports, game=game,
                game_files=game_files, batches=[b for b in batches if any(i['asset_id'] == asset_id for i in b['items'])], asset_dir=asset_dir, library_bytes=library_bytes)


@router.get('/{asset_id}')
def plan(asset_id: str):
    c = collect(asset_id)
    return dict(asset_id=asset_id, name=c['model']['name'], active_jobs=sum(j['status'] not in jobs.TERMINAL for j in c['owned']), jobs=len(c['owned']),
                artifacts=len(c['artifacts']), library_bytes=c['library_bytes'], batches=[b['name'] for b in c['batches']],
                game_files=[dict(path=str(p), bytes=p.stat().st_size) for p in c['game_files']])


class Delete(BaseModel):
    confirm_name: str
    include_game_files: bool = False


def _unpublish(delivery, asset_id):
    """Take the asset out of the game manifest the app manages; an edited manifest is left alone."""
    root = Path(delivery.get('output_root') or ''); target = root / studio_slug(delivery['project_id']) / 'manifest.json'
    with store.connect() as db:
        row = db.execute('SELECT * FROM delivery_indexes WHERE path=?', (str(target),)).fetchone()
        if not row or not target.is_file(): return 'no managed manifest'
        if hashlib.sha256(target.read_bytes()).hexdigest() != row['sha256']: return 'manifest was edited; entry kept'
        value = json.loads(row['payload']); value['assets'].pop(asset_id, None)
        value['history'] = {k: v for k, v in value.get('history', {}).items() if v.get('asset_id') != asset_id}
        content = json.dumps(value, ensure_ascii=False, indent=2).encode('utf-8')
        temporary = target.with_suffix('.json.part'); temporary.write_bytes(content); temporary.replace(target)
        db.execute('UPDATE delivery_indexes SET payload=?,sha256=? WHERE path=?', (json.dumps(value), hashlib.sha256(content).hexdigest(), str(target)))
    return 'manifest entry removed'


def studio_slug(project_id):
    from .export_profiles import _slug
    return _slug(project_id)


def _remove(path):
    for attempt in range(20):  # a cancelled worker may still hold a file for a moment on Windows
        try:
            if Path(path).is_dir(): shutil.rmtree(path)
            elif Path(path).exists(): Path(path).unlink()
            return
        except OSError:
            time.sleep(0.5)
    raise HTTPException(409, f'Could not remove {path}; close any program using it and delete again.')


@router.post('/{asset_id}')
def delete(asset_id: str, body: Delete):
    c = collect(asset_id)
    if body.confirm_name.strip() != c['model']['name'].strip(): raise HTTPException(400, 'Type the asset name exactly to confirm.')
    for j in c['owned']:  # stop unfinished work first; the worker kills its processes on CANCELLED
        if j['status'] not in jobs.TERMINAL:
            try: jobs.transition(j['id'], 'CANCELLED', 'Asset deleted by the user')
            except (ValueError, KeyError): pass
    deadline = time.time() + 20
    while time.time() < deadline and any(jobs.get(j['id'])['status'] in ('RUNNING', 'POSTPROCESSING', 'VALIDATING', 'GENERATED') for j in c['owned']): time.sleep(0.5)
    game = []
    if body.include_game_files:
        for d in c['game']:
            for f in d.get('files', []):
                path = Path(d['export_directory']) / f['name']
                if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == f.get('sha256'): _remove(path); game.append(str(path))
            folder = Path(d['export_directory'])
            if folder.is_dir() and not any(folder.iterdir()): folder.rmdir()
            game.append(_unpublish(d, asset_id))
    for path in [*c['folders'], *c['files'], *(Path(d['export_directory']) for d in c['library_exports']), c['asset_dir']]: _remove(path)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM artifacts WHERE asset_id=?', (asset_id,))
        db.executemany('DELETE FROM jobs WHERE id=?', [(j['id'],) for j in c['owned']])
        db.execute('DELETE FROM selective_exports WHERE asset_id=?', (asset_id,))
        db.execute('DELETE FROM asset_exports WHERE asset_id=?', (asset_id,))
        for table in ('production_notifications',):
            try: db.execute(f'DELETE FROM {table} WHERE asset_id=?', (asset_id,))
            except Exception: pass
        for b in c['batches']:
            b['items'] = [i for i in b['items'] if i['asset_id'] != asset_id]
            if b['items']: db.execute('UPDATE batches SET payload=? WHERE id=?', (json.dumps(b), b['id']))
            else: db.execute('DELETE FROM batches WHERE id=?', (b['id'],))
        db.execute('DELETE FROM assets WHERE id=?', (asset_id,))
    return dict(status='DELETED', asset_id=asset_id, freed_bytes=c['library_bytes'], jobs=len(c['owned']), artifacts=len(c['artifacts']), game=game)
