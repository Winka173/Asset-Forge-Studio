"""Selective, checksum-verified local delivery. Never schedules AI or mutates masters."""
import hashlib
import json
import re
import shutil
import threading
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from typing import Literal
from . import store
from .inspection import inspect_glb, glb_document

router = APIRouter(prefix='/api/export-profiles')
_lock = threading.RLock()


class ExportSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preset: Literal['glb_only', 'unity', 'unreal', 'full_source', 'custom'] = 'glb_only'
    glb: bool = True
    manifest: bool = True
    zip: bool = False
    fbx: bool = False
    blend: bool = False
    textures: bool = False
    lods: bool = False
    high_poly: bool = False
    unity_package: bool = False
    unreal_package: bool = False
    output_directory: str | None = None


class ExportRequest(BaseModel):
    artifact_id: str | None = None
    settings: ExportSettings | None = None


def _schema():
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS selective_exports (id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS delivery_indexes (path TEXT PRIMARY KEY, payload TEXT NOT NULL, sha256 TEXT NOT NULL)')


def publish_index(result,manifest):
    """Atomic, recoverable project pointer; never replaces a manually edited game index."""
    if not result['settings']['manifest']:return
    root=Path(result['output_root'])/_slug(result['project_id']);target=root/'manifest.json'
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM delivery_indexes WHERE path=?',(str(target),)).fetchone()
        previous=json.loads(row['payload']) if row else dict(schema_version='1.0',project_id=result['project_id'],assets={},history={})
        if target.exists():
            content=target.read_bytes()
            if row and hashlib.sha256(content).hexdigest()!=row['sha256']:
                # Reconcile a process crash after atomic rename but before SQLite commit.
                try:on_disk=json.loads(content)
                except ValueError:raise HTTPException(409,'Project manifest was edited; it was not overwritten.')
                expected=dict(previous);expected['assets']=dict(previous['assets']);expected['history']=dict(previous['history'])
                key=result['asset_id'];entry=_index_entry(result,manifest,root)
                expected['assets'][key]=entry;expected['history'][result['id']]=entry
                if on_disk!=expected:raise HTTPException(409,'Project manifest was edited; it was not overwritten.')
                previous=expected
            elif not row:raise HTTPException(409,'An unmanaged project manifest already exists. Choose another output folder.')
        updated=dict(previous);updated['assets']=dict(previous['assets']);updated['history']=dict(previous['history'])
        entry=_index_entry(result,manifest,root);updated['assets'][result['asset_id']]=entry;updated['history'][result['id']]=entry
        content=json.dumps(updated,ensure_ascii=False,indent=2).encode('utf-8')
        temporary=target.with_suffix('.json.part');temporary.write_bytes(content);temporary.replace(target)
        db.execute('INSERT INTO delivery_indexes VALUES (?,?,?) ON CONFLICT(path) DO UPDATE SET payload=excluded.payload,sha256=excluded.sha256',(str(target),json.dumps(updated),hashlib.sha256(content).hexdigest()))
    result['project_manifest']=str(target)


def _index_entry(result,manifest,root):
    return dict(asset_id=result['asset_id'],source_asset_id=result['source_asset_id'],name=manifest['name'],category=manifest['category'],export_version=result['id'],created_at=result['created_at'],
                glb=(Path(result['export_directory'])/manifest['glb']).relative_to(root).as_posix() if manifest['glb'] else None,
                dimensions_xyz_m=manifest['dimensions_xyz_m'],bounds_xyz_m=manifest['bounds_xyz_m'],units=manifest['units'],orientation=manifest['orientation'],
                sha256=next((f['sha256'] for f in result['files'] if f['name']==manifest['glb']),None),qa_status='passed',art_review_status=manifest.get('art_review_status','not_reviewed'),provenance=manifest.get('generation_provenance',dict(source_artifact_id=manifest['source_artifact_id'])))


def generation_provenance(record,value):
    metadata=record['metadata'];raw=record
    if metadata.get('parent_id'):
        try:raw=store.get_artifact(metadata['parent_id'])
        except KeyError:pass
    payload={}
    if raw['metadata'].get('job_id'):
        from .jobs import get
        try:payload=get(raw['metadata']['job_id'])['payload']
        except KeyError:pass
    effective=payload.get('effective_config') or {}
    return dict(source_artifact_id=record['id'],source_sha256=record['sha256'],raw_artifact_id=raw['id'],raw_sha256=raw['sha256'],
                engine=payload.get('engine') or raw['metadata'].get('engine'),seed=payload.get('seed'),quality=payload.get('quality'),
                effective_config_hash=payload.get('effective_config_hash'),checkpoint_manifest_hash=effective.get('checkpoint',{}).get('manifest_hash'),
                source_prompt_sha256=hashlib.sha256(value.get('prompt','').encode('utf-8')).hexdigest() if value.get('prompt') else None,
                license=raw['metadata'].get('license','UNKNOWN'),commercial=raw['metadata'].get('commercial','NOT_CLEARED'),artistic_approval='NOT_GIVEN_BY_EXPORT')


def _settings(value=None):
    result = ExportSettings.model_validate(value or {}).model_dump()
    if result['output_directory']:
        location=Path(result['output_directory'])
        if not location.is_absolute() or str(location).startswith(('\\\\','//')) or '..' in location.parts or not location.is_dir():
            raise HTTPException(422,'Output location must be an existing absolute local directory selected by the user.')
        result['output_directory']=str(location.resolve())
    if result['preset'] == 'unreal' or result['unreal_package']:
        raise HTTPException(422, 'Unreal native export has not been validated on this machine. Use GLB Only for portable geometry.')
    if result['preset'] == 'glb_only' and any(result[key] for key in ('fbx', 'blend', 'textures', 'lods', 'high_poly', 'unity_package')):
        raise HTTPException(422, 'GLB Only cannot include extra formats. Choose Custom to select extra components.')
    if result['preset'] == 'glb_only':
        result['glb'] = True
    if not any(result[key] for key in ('glb', 'fbx', 'blend', 'textures', 'lods', 'high_poly', 'unity_package')):
        raise HTTPException(422, 'Select at least one actual asset output.')
    return result


def resolve_project_settings(project_id):
    from .studio import project
    return _settings(project(project_id).get('export_settings', {}).get('selective_export'))


@router.get('/capabilities')
def capabilities():
    return dict(default=ExportSettings().model_dump(), profiles=[
        dict(id='glb_only', name='GLB Only', available=True, explanation='One self-contained GLB, unchanged source quality.'),
        dict(id='unity', name='Unity', available=True, explanation='GLB delivery. FBX / native package only when a validated output already exists.'),
        dict(id='unreal', name='Unreal', available=False, explanation='Unreal Editor validation deferred; native package unavailable.'),
        dict(id='full_source', name='Full Source', available=True, explanation='Existing validated sources only; missing requested components block export.'),
        dict(id='custom', name='Custom', available=True, explanation='Select independently from outputs available for this asset.')],
        generation_quality_affected=False, output_root=str(store.DATA / 'exports'),
        components=dict(glb=True, manifest=True, zip=True, fbx='validated Blender output required', blend='validated Blender source required',
                        textures='actual separate texture files required', lods='validated Blender LOD files required', high_poly='distinct high-poly master required',
                        unity_package='passing Unity native package required', unreal_package=False))


@router.get('/projects/{project_id}')
def project_settings(project_id: str):
    return dict(settings=resolve_project_settings(project_id), output_root=str(store.DATA / 'exports' / _slug(project_id)))


@router.post('/projects/{project_id}')
def save_project_settings(project_id: str, body: ExportSettings):
    from .studio import project
    settings = _settings(body.model_dump())
    with _lock, store.connect() as db:
        # Read again inside the transaction to avoid replacing other additive project settings.
        project(project_id)
        row = db.execute('SELECT payload FROM projects WHERE id=? AND archived=0', (project_id,)).fetchone()
        value = json.loads(row['payload']); value.setdefault('export_settings', {})['selective_export'] = settings
        db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(value), project_id))
    return dict(settings=settings, output_root=str(store.DATA / 'exports' / _slug(project_id)))


def _slug(value):
    text = re.sub(r'[^a-zA-Z0-9._-]+', '-', str(value)).strip(' .-')[:100] or 'asset'
    if text.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:text = 'asset-' + text
    return text


def _record_path(record):
    path = store.safe_path(record['relative_path'])
    if not path.is_file() or store.digest(path) != record['sha256']:
        raise HTTPException(409, 'Stored source is missing or its checksum changed; no delivery was marked complete.')
    return path


def _source(asset, artifact_id=None):
    from .studio import scoped_artifact
    if artifact_id:
        record = scoped_artifact(artifact_id, asset['project_id'], asset['id'])
    else:
        with store.connect() as db:
            records = [store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE project_id=? AND asset_id=? ORDER BY created_at DESC', (asset['project_id'], asset['id']))]
        meshes = [r for r in records if Path(r['relative_path']).suffix.lower() == '.glb' and r['role'] in ('candidate','master','processed')]
        record = next((r for r in meshes if r['id'] == asset.get('master_artifact_id')), None)
        record = record or next((r for r in meshes if r['metadata'].get('stage') == 'blender_processed' and 'LOD0' in r['name']), None)
        record = record or next(iter(meshes), None)
        if not record:raise HTTPException(409, 'No completed GLB exists for this asset. Generation is not started by export.')
    path = _record_path(record)
    if path.suffix.lower() != '.glb':raise HTTPException(422, 'Select an actual GLB candidate or master.')
    try:qa = inspect_glb(path)
    except Exception as error:raise HTTPException(409, f'GLB validation failed: {error}') from error
    return record, path, qa


def available_sources(asset, record, path):
    """Never fabricate formats or copy arbitrary paths from a request."""
    sources = dict(glb=[(path, '.glb')], fbx=[], blend=[], textures=[], lods=[], high_poly=[], unity_package=[])
    job_id = record['metadata'].get('job_id')
    if job_id:
        from . import jobs
        try:
            job = jobs.get(job_id)
            folder = store.DATA / 'jobs' / job_id / 'output'
            report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
            if job['status'] == 'REVIEW_REQUIRED' and job['payload'].get('asset_id') == asset['id'] and report.get('checks',{}).get('export_reopen') == 'PASS':
                recorded={entry['path']:entry['sha256'] for entry in report.get('artifacts',[]) if entry.get('path') and entry.get('sha256')}
                for file in folder.rglob('*'):
                    if not file.is_file():continue
                    relative=file.relative_to(folder).as_posix()
                    if not (file.suffix.lower() in ('.glb','.fbx','.blend') or (file.suffix.lower() in ('.png','.jpg','.jpeg') and 'textures' in file.relative_to(folder).parts)):continue
                    if recorded.get(relative)!=store.digest(file):continue
                    if file.suffix.lower() == '.fbx' and file.name == 'LOD0.fbx' and report.get('checks',{}).get('fbx_reopen') == 'PASS':sources['fbx'].append((file, '.fbx'))
                    if file.suffix.lower() == '.blend':sources['blend'].append((file, '_' + file.name))
                    if file.suffix.lower() in ('.png','.jpg','.jpeg') and 'textures' in file.relative_to(folder).parts:sources['textures'].append((file, '/' + relative))
                    if re.fullmatch(r'LOD[1-3]\.glb', file.name):
                        inspect_glb(file); sources['lods'].append((file, '_' + file.name))
        except (KeyError, OSError, ValueError):pass
    master = asset.get('master_artifact_id')
    if master and master != record['id']:
        from .studio import scoped_artifact
        source = scoped_artifact(master, asset['project_id'], asset['id']); file = _record_path(source)
        if file.suffix.lower() == '.glb' and inspect_glb(file)['triangles']>=inspect_glb(path)['triangles']:sources['high_poly'].append((file, '_master.glb'))
    with store.connect() as db:
        native = [store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE project_id=? AND asset_id=? AND role='engine_package' ORDER BY created_at DESC", (asset['project_id'], asset['id']))]
    for entry in native:
        if Path(entry['relative_path']).suffix == '.unitypackage' and entry['metadata'].get('parent_id')==record['id']:
            from . import jobs
            try:
                job = jobs.get(entry['metadata'].get('job_id',''))
                if job['status'] == 'REVIEW_REQUIRED' and job['payload'].get('asset_id') == asset['id']:
                    sources['unity_package'].append((_record_path(entry), '.unitypackage'));break
            except (KeyError, HTTPException):continue
    return sources


@router.get('/assets/{asset_id}/capabilities')
def asset_capabilities(asset_id: str, artifact_id: str | None = None):
    from .studio import asset
    value = asset(asset_id);record,path,qa = _source(value, artifact_id)
    return dict(artifact_id=record['id'], available={key:bool(files) for key,files in available_sources(value,record,path).items()}, qa=qa)


def revision_output_directory():
    # Application-owned staging root is not a user-selected export directory.
    target=store.DATA/'revision-previews'
    target.mkdir(parents=True,exist_ok=True)
    return str(target)


def export_asset(project_id, asset_id, artifact_id=None, settings=None, allow_publish=False):
    from .studio import asset, project
    value = asset(asset_id)
    if value['project_id'] != project_id:raise HTTPException(409, 'Asset belongs to another project.')
    project_value = project(project_id)
    settings = _settings(settings if settings is not None else resolve_project_settings(project_id))
    record,path,qa = _source(value,artifact_id)
    revision=next((r for r in value.get('revisions',[]) if r.get('artifact_id')==record['id']),None)
    staged=bool(revision and revision.get('previous_delivery_ids') and not revision.get('auto_replace') and value.get('published_artifact_id')!=record['id'] and not allow_publish)
    if staged:settings['output_directory']=revision_output_directory()

    sources = available_sources(value,record,path)
    requested = [key for key in sources if settings.get(key)]
    missing = [key for key in requested if not sources[key]]
    if missing:raise HTTPException(409, 'Requested outputs are not validated/available: ' + ', '.join(missing) + '. Disable them or create real validated outputs first.')
    source_id = value.get('settings',{}).get('source_asset_id') or value['id']
    # Stable source-ID-based basename with a stable identity suffix prevents sanitized/case collisions.
    stem = _slug(source_id) + '--' + hashlib.sha256(value['id'].encode()).hexdigest()[:10]
    selected = sorted([(source, stem + suffix) for kind in requested for source,suffix in sources[kind]],key=lambda pair:pair[1])
    if len({name.casefold() for _,name in selected}) != len(selected):raise HTTPException(409,'Source components have colliding output names.')
    from .statuses import approved,policy
    from .automation import project_workflow
    if policy(value,project_workflow(project_id))=='manual_approval' and not approved(value,record['id']):raise HTTPException(409,'Manual Approval policy: explicitly approve the selected candidate before export.')
    review_state='approved' if approved(value,record['id']) else 'not_reviewed'
    fingerprint = json.dumps(dict(delivery_schema='1.2',art_review_status=review_state,asset_id=asset_id,settings=settings,files=[(name,store.digest(source)) for source,name in selected]),sort_keys=True)
    identifier = uuid.uuid5(uuid.NAMESPACE_URL,'afs-selective-export:' + fingerprint).hex
    base = Path(settings['output_directory']) if settings.get('output_directory') else store.DATA / 'exports'
    folder = base / _slug(project_id) / 'selective' / _slug(asset_id) / identifier
    _schema()
    with _lock:
        with store.connect() as db:row = db.execute('SELECT payload FROM selective_exports WHERE id=?',(identifier,)).fetchone()
        if row:
            result = json.loads(row['payload']); _verify_delivery(result)
            if settings['manifest']:publish_index(result,json.loads((folder/'manifest.json').read_text(encoding='utf-8')))
            return result
        folder.mkdir(parents=True,exist_ok=True);files=[]
        for source,name in selected:
            target=folder/name; target.parent.mkdir(parents=True,exist_ok=True)
            checksum=store.digest(source)
            if target.exists():
                if store.digest(target)!=checksum:raise HTTPException(409,'Existing export was edited externally. It was not overwritten; choose another output location or version.')
            else:
                temporary=target.with_name(target.name+'.part');shutil.copyfile(source,temporary)
                if store.digest(temporary)!=checksum:raise HTTPException(409,'Copy checksum failed.')
                if target.suffix.lower()=='.glb':inspect_glb(temporary)
                temporary.replace(target)
            files.append(dict(name=name,bytes=target.stat().st_size,sha256=store.digest(target),kind=target.suffix.lstrip('.')))
        created=store.now();doc=glb_document(path)
        manifest=dict(schema_version='1.2',qa_status='passed',art_review_status=review_state,generation_provenance=generation_provenance(record,value),export_version=identifier,created_at=created,project_id=project_id,project_name=project_value['name'],asset_id=value['id'],source_asset_id=source_id,
                      name=value['name'],category=value.get('category'),source_artifact_id=record['id'],glb=next((f['name'] for f in files if f['name']==stem+'.glb'),None),
                      bounds_xyz_m=qa['bounds_xyz_m'],dimensions_xyz_m=qa['dimensions_xyz_m'],units='m',orientation='glTF Y-up',source_scale_approved=False,
                      lods=[f['name'] for f in files if re.search(r'_LOD[1-3]\.glb$',f['name'])],materials=qa['materials'],embedded_images=qa['images'],
                      mesh_normals_present=all('NORMAL' in p.get('attributes',{}) for m in doc.get('meshes',[]) for p in m.get('primitives',[])),qa=qa,files=files.copy(),
                      approval_status=value.get('status'),source_preserved=True,quality='Unchanged source bytes; technical validation is not artistic approval')
        if settings['manifest']:
            target=folder/'manifest.json'
            if target.exists():
                try:
                    previous=json.loads(target.read_text(encoding='utf-8'))
                    # A crash may leave a fully copied immutable version without its SQLite completion record.
                    manifest['created_at']=previous['created_at'];created=previous['created_at']
                    if previous!=manifest:raise ValueError('Manifest was edited')
                except (ValueError,KeyError):raise HTTPException(409,'Existing manifest differs from the validated source. It was not overwritten.')
            else:
                temporary=target.with_suffix('.json.part');temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(target)
            files.append(dict(name=target.name,bytes=target.stat().st_size,sha256=store.digest(target),kind='manifest'))
        if settings['zip']:
            target=folder/(stem+'.zip');temporary=target.with_suffix('.zip.part')
            if target.exists():
                try:
                    with zipfile.ZipFile(target) as archive:
                        if sorted(archive.namelist())!=sorted(file['name'] for file in files):raise ValueError('Archive members differ')
                        for file in files:
                            with archive.open(file['name']) as member:
                                if hashlib.file_digest(member,'sha256').hexdigest()!=file['sha256']:raise ValueError('Archive checksum differs')
                except (ValueError,zipfile.BadZipFile):raise HTTPException(409,'Existing ZIP differs; it was not overwritten.')
            else:
                with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_STORED) as archive:
                    for item in files:archive.write(folder/item['name'],item['name'])
                temporary.replace(target)
            files.append(dict(name=target.name,bytes=target.stat().st_size,sha256=store.digest(target),kind='zip'))
        result=dict(id=identifier,status='COMPLETED',delivery_scope='staged' if staged else 'game',asset_id=asset_id,project_id=project_id,source_asset_id=source_id,artifact_id=record['id'],settings=settings,created_at=created,
                    export_directory=str(folder),output_root=str(base.resolve()),filename=stem+'.glb' if settings['glb'] else files[0]['name'],files=[f|dict(url=f'/api/export-profiles/exports/{identifier}/files/{f["name"]}') for f in files],qa=qa)
        publish_index(result,manifest)
        with store.connect() as db:db.execute('INSERT INTO selective_exports VALUES (?,?,?)',(identifier,asset_id,json.dumps(result)))
    return result


def _verify_delivery(result):
    folder=Path(result['export_directory']).resolve()
    if not folder.is_relative_to(Path(result.get('output_root',store.DATA)).resolve()):raise HTTPException(409,'Export location is invalid.')
    for file in result['files']:
        path=(folder/file['name']).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or store.digest(path)!=file['sha256']:raise HTTPException(409,'Completed export missing or checksum changed; original source remains preserved.')


@router.post('/assets/{asset_id}')
def prepare_export(asset_id:str,body:ExportRequest):
    from .studio import asset
    value=asset(asset_id)
    return export_asset(value['project_id'],asset_id,body.artifact_id,body.settings.model_dump() if body.settings else None)


@router.get('/assets/{asset_id}')
def export_history(asset_id:str):
    from .studio import asset
    asset(asset_id);_schema()
    with store.connect() as db:return [json.loads(row['payload']) for row in db.execute('SELECT payload FROM selective_exports WHERE asset_id=? ORDER BY rowid DESC',(asset_id,))]


class BatchExport(BaseModel):
    selection:Literal['selected','completed','all_completed']='all_completed'


@router.post('/batches/{batch_id}')
def export_batch(batch_id:str,body:BatchExport):
    from . import batch
    value=batch.detail(batch.batch(batch_id));completed=[];errors=[];skipped=[]
    for item in value['items']:
        if body.selection=='selected' and not item['selected']:continue
        artifact_id=item.get('automation',{}).get('candidate_selection',{}).get('artifact_id')
        artifact_id=artifact_id or next((a['id'] for a in item['versions'] if a['metadata'].get('stage')=='blender_processed'),None)
        if not artifact_id:skipped.append(dict(asset_id=item['asset_id'],reason='No technically processed model'));continue
        try:completed.append(export_asset(value['project_id'],item['asset_id'],artifact_id))
        except HTTPException as exc:errors.append(dict(asset_id=item['asset_id'],error=exc.detail))
    return dict(status='PARTIAL' if errors else 'COMPLETED' if completed else 'NO_COMPLETED_ASSETS',completed=completed,errors=errors,skipped=skipped,inference_started=False)


@router.get('/exports/{identifier}/files/{name:path}')
def download(identifier:str,name:str):
    _schema()
    with store.connect() as db:row=db.execute('SELECT payload FROM selective_exports WHERE id=?',(identifier,)).fetchone()
    if not row:raise HTTPException(404,'Export not found')
    result=json.loads(row['payload']);_verify_delivery(result)
    if not any(file['name']==name for file in result['files']):raise HTTPException(404,'File is not part of a completed export')
    return FileResponse(Path(result['export_directory'])/name,filename=Path(name).name)
