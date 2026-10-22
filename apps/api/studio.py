"""Project-scoped studio/library UX over the existing immutable local pipeline."""
import hashlib
import json
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from . import jobs, store

router = APIRouter(prefix='/api')


@router.get('/gpu')
def gpu_status():
    import subprocess
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.used,memory.total,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
        if result.returncode: raise ValueError('nvidia-smi failed')
        parts = result.stdout.splitlines()[0].split(',')
        return dict(available=True, name=parts[0].strip(), used_mib=float(parts[1]), total_mib=float(parts[2]), utilization_percent=float(parts[3]))
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return dict(available=False, reason='Không đọc được GPU local')


def project(identifier):
    with store.connect() as db:
        row = db.execute('SELECT payload FROM projects WHERE id=? AND archived=0', (identifier,)).fetchone()
    if not row: raise HTTPException(404, 'Không tìm thấy game đang hoạt động')
    return json.loads(row['payload'])


def asset(identifier):
    with store.connect() as db:
        row = db.execute('SELECT payload FROM assets WHERE id=?', (identifier,)).fetchone()
    if not row: raise HTTPException(404, 'Không tìm thấy asset')
    result = json.loads(row['payload']); project(result['project_id'])
    return result


def save_asset(value):
    value['updated_at'] = store.now()
    with store.connect() as db:
        db.execute('UPDATE assets SET payload=? WHERE id=?', (json.dumps(value), value['id']))
    return value


def scoped_artifact(identifier, project_id, asset_id=None):
    try: record = store.get_artifact(identifier)
    except KeyError: raise HTTPException(404, 'Không tìm thấy file')
    if record.get('project_id') != project_id or (asset_id and record.get('asset_id') != asset_id):
        raise HTTPException(400, 'File thuộc game/asset khác')
    return record


class ProjectInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default='', max_length=20000)
    cover_artifact_id: str | None = None
    art_bible: dict = Field(default_factory=dict)
    palette: list[str] = Field(default_factory=list, max_length=32)
    material_language: str = Field(default='', max_length=10000)
    default_style: str = Field(default='', max_length=10000)
    units: Literal['m', 'cm'] = 'm'
    target_height_m: float | None = Field(default=None, gt=0, le=1000)
    export_settings: dict = Field(default_factory=dict)
    target_engines: list[Literal['unity','unreal']] = Field(default_factory=list,max_length=2)
    engine_profiles: dict = Field(default_factory=dict)


@router.get('/projects')
def projects():
    with store.connect() as db:
        return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM projects WHERE archived=0')]


@router.post('/projects', status_code=201)
def create_project(body: ProjectInput):
    identifier = uuid.uuid4().hex
    if not body.name.strip(): raise HTTPException(400, 'Tên game không được để trống')
    if body.cover_artifact_id: raise HTTPException(400, 'Tạo game trước rồi nhập ảnh cover thuộc game này')
    value = body.model_dump() | dict(id=identifier)
    with store.connect() as db: db.execute('INSERT INTO projects VALUES (?,?,0)', (identifier, json.dumps(value)))
    return value


@router.post('/projects/{identifier}')
def update_project(identifier: str, body: ProjectInput):
    previous=project(identifier)
    if not body.name.strip(): raise HTTPException(400, 'Tên game không được để trống')
    if body.cover_artifact_id:
        cover = scoped_artifact(body.cover_artifact_id, identifier)
        if cover['role'] not in ('concept', 'reference'): raise HTTPException(400, 'Cover cần ảnh')
    updates=body.model_dump(exclude_unset=True)
    if 'export_settings' in updates:updates['export_settings']=previous.get('export_settings',{}) | updates['export_settings']
    value = previous | updates | dict(id=identifier)
    with store.connect() as db: db.execute('UPDATE projects SET payload=? WHERE id=?', (json.dumps(value), identifier))
    return value


class ConfirmDelete(BaseModel):
    confirm_name: str


@router.post('/projects/{identifier}/delete')
def delete_project(identifier: str, body: ConfirmDelete):
    value = project(identifier)
    if body.confirm_name != value['name']: raise HTTPException(400, 'Nhập đúng tên game để xác nhận xóa')
    active = [j for j in jobs.listing() if j['status'] not in jobs.TERMINAL and job_project(j) == identifier]
    if active: raise HTTPException(409, 'Hủy hoặc hoàn tất job của game trước khi xóa')
    # Preserve immutable source/output and references; remove from active workspace.
    with store.connect() as db: db.execute('UPDATE projects SET archived=1 WHERE id=?', (identifier,))
    return dict(status='ARCHIVED', files_preserved=True)


class Draft(BaseModel):
    draft: dict


@router.post('/projects/{identifier}/draft')
def draft(identifier: str, body: Draft):
    project(identifier)
    if len(json.dumps(body.draft)) > 200000: raise HTTPException(400, 'Draft quá lớn')
    with store.connect() as db:
        db.execute('INSERT INTO drafts VALUES (?,?) ON CONFLICT(project_id) DO UPDATE SET payload=excluded.payload', (identifier, json.dumps(body.draft)))
    return body.draft


class AssetInput(BaseModel):
    project_id: str
    asset_type: Literal['static_3d','map_environment'] = 'static_3d'
    name: str = Field(min_length=1, max_length=200)
    prompt: str = Field(default='', max_length=100000)
    reference_ids: list[str] = Field(default_factory=list, max_length=50)
    settings: dict = Field(default_factory=dict)
    category: str = Field(default='', max_length=200)


@router.post('/assets', status_code=201)
def create_asset(body: AssetInput):
    project(body.project_id)
    for ref in body.reference_ids: scoped_artifact(ref, body.project_id)
    if not body.name.strip(): raise HTTPException(400, 'Tên asset không được để trống')
    value = body.model_dump() | dict(id=uuid.uuid4().hex, favorite=False, status='Candidate', master_artifact_id=None,
                                    approvals=[], created_at=store.now(), updated_at=store.now())
    with store.connect() as db: db.execute('INSERT INTO assets VALUES (?,?,?)', (value['id'], body.project_id, json.dumps(value)))
    return value


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    prompt: str | None = Field(default=None, max_length=100000)
    category: str | None = Field(default=None, max_length=200)
    favorite: bool | None = None
    status: Literal['Candidate', 'Rejected', 'Failed'] | None = None
    settings: dict | None = None
    reference_ids: list[str] | None = None


@router.post('/assets/{identifier}')
def update_asset(identifier: str, body: AssetUpdate):
    value = asset(identifier)
    updates = body.model_dump(exclude_none=True)
    if updates.get('name') is not None and not updates['name'].strip(): raise HTTPException(400, 'Tên asset không được để trống')
    for ref in updates.get('reference_ids', []): scoped_artifact(ref, value['project_id'])
    return save_asset(value | updates)


class Approval(BaseModel):
    artifact_id: str
    reviewer: str = Field(min_length=1, max_length=100)
    notes: str = Field(default='', max_length=10000)


class Attach(BaseModel):
    artifact_id: str


@router.post('/assets/{identifier}/versions')
def attach_version(identifier: str, body: Attach):
    value = asset(identifier)
    record = scoped_artifact(body.artifact_id, value['project_id'])
    if record['role'] != 'candidate': raise HTTPException(400, 'Cần model candidate thật')
    if record.get('asset_id') not in (None, identifier): raise HTTPException(409, 'Version đã thuộc asset khác')
    with store.connect() as db:
        db.execute('UPDATE artifacts SET asset_id=? WHERE id=?', (identifier, record['id']))
    return save_asset(value)


@router.post('/assets/{identifier}/approve')
def approve(identifier: str, body: Approval):
    value = asset(identifier)
    record = scoped_artifact(body.artifact_id, value['project_id'], identifier)
    if record['role'] != 'candidate' and not (value.get('asset_type')=='map_environment' and record['role']=='engine_package' and record['metadata'].get('asset_type')=='map_environment'):
        raise HTTPException(400, 'Select a real model candidate or validated native World package')
    if not body.reviewer.strip(): raise HTTPException(400, 'Cần tên người duyệt')
    entry = body.model_dump() | dict(sha256=record['sha256'], created_at=store.now(), scope='human_master_selection_only',
                                    mesh_quality_parity='NOT_TESTED', unity='NOT_TESTED')
    value.setdefault('approvals', []).append(entry)
    value.update(status='Approved', master_artifact_id=record['id'])
    return save_asset(value)


def job_project(job):
    if job['payload'].get('project_id'): return job['payload']['project_id']
    try: return store.get_artifact(job['payload'].get('artifact_id', ''))['project_id']
    except KeyError: return None


def output_files(export):
    from .export_files import deliver
    if export.get('native_world_job_id'):
        job=jobs.get(export['native_world_job_id'])
        if job['status']!='REVIEW_REQUIRED':return export|dict(validation=job['status'],files=[])
        value=asset(export['asset_id'])
        if job['payload'].get('asset_id')!=value['id'] or job['payload'].get('project_id')!=value['project_id']:raise HTTPException(409,'World export project mismatch')
        folder=store.DATA/'jobs'/job['id']/'output'
        report=json.loads((folder/'world_unity_reopen.json').read_text(encoding='utf-8-sig'))
        if report.get('checks_passed') is not True:raise HTTPException(409,'Native World reopen did not pass')
        names=['AFS_World.unitypackage','world_sources.zip','height.png','height.raw','roads.png','build_zones.png','world_plan.json','world_unity_report.json','world_unity_reopen.json']
        return deliver(export|dict(validation='PASS_EDITOR_VALIDATION'),[dict(name=n,_source=str(folder/n)) for n in names])
    if not export.get('job_id'):
        if export.get('validation')=='PASS_FILE_CHECKSUM':
            value=asset(export['asset_id']);record=scoped_artifact(export['artifact_id'],value['project_id'],value['id'])
            path=store.safe_path(record['relative_path'])
            if store.digest(path)!=record['sha256']:raise HTTPException(409,'Source checksum changed')
            return deliver(export,[dict(name='Master.glb',_source=str(path))])
        return export
    job = jobs.get(export['job_id']); export['job'] = job
    export['validation'] = job['status']
    export['files'] = []
    if job['status'] == 'REVIEW_REQUIRED':
        folder = store.DATA / 'jobs' / job['id'] / 'output'
        # Success requires Blender validation of every GLB/FBX reimport first.
        report = json.loads((folder / 'report.json').read_text(encoding='utf-8'))
        if report['checks'].get('export_reopen') != 'PASS':
            export['validation'] = 'FAILED'; return export
        lod = 0 if export['preset'] == 'Master' else 2 if export['preset'] == 'Unity Mobile' else 1
        name = f'LOD{lod}.{export["format"]}'
        path = folder / name
        if path.is_file(): export['files'].append(dict(name=name, _source=str(path)))
        else: export['validation'] = 'FAILED'
        for path in folder.rglob('*.png'):
            if 'textures' in path.relative_to(folder).parts:
                relative = path.relative_to(folder).as_posix()
                export['files'].append(dict(name=relative, _source=str(path)))
        if export['validation']=='REVIEW_REQUIRED':return deliver(export,export['files'])
        export['files']=[]
    return export


@router.get('/exports/{identifier}/files/{name:path}')
def export_download(identifier:str,name:str):
    from fastapi.responses import FileResponse
    from .export_files import download
    path=download(identifier,name)
    return FileResponse(path,filename=path.name)


@router.get('/studio')
def studio_view(project_id: str = ''):
    from .statuses import refresh_all
    refresh_all()
    return studio(project_id)


def studio(project_id: str = ''):
    from engines.adapters import ADAPTERS
    from engines.concept_adapter import CONCEPT_ADAPTER
    from .prompt_intent import capability as intent_capability
    selected = project(project_id) if project_id else None
    with store.connect() as db:
        artifacts = [store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at', (project_id,))]
        values = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM assets WHERE project_id=?', (project_id,))]
        exports = [dict(id=r['id'], **json.loads(r['payload'])) for r in db.execute('SELECT * FROM asset_exports')]
        row = db.execute('SELECT payload FROM drafts WHERE project_id=?', (project_id,)).fetchone()
    for value in values:
        value['versions'] = [a for a in artifacts if a['asset_id'] == value['id'] and (a['role'] == 'candidate' or (value.get('asset_type')=='map_environment' and a['role'] in ['world_plan','engine_package']))]
        value['exports'] = [output_files(e) for e in exports if e.get('asset_id') == value['id']]
        thumbnail = next((a for a in artifacts if a['id'] in value['reference_ids']), None)
        value['thumbnail_url'] = thumbnail['url'] if thumbnail else None
        value['thumbnail_kind'] = 'reference' if thumbnail else None
        if value.get('asset_type')=='map_environment':
            preview=next((a for a in reversed(artifacts) if a['asset_id']==value['id'] and a['name']=='world_overview.png' and a['role']=='preview'),None)
            if preview:value.update(thumbnail_url=preview['url'],thumbnail_kind='unity_map_preview')
        for version in reversed(value['versions']):
            job_id = version['metadata'].get('job_id')
            if job_id and (store.DATA / 'jobs' / job_id / 'output/mobile_three_quarter.png').is_file():
                value['thumbnail_url'] = f'/api/jobs/{job_id}/files/output/mobile_three_quarter.png'
                value['thumbnail_kind'] = 'model_render'
                break
    return dict(projects=projects(), project=selected, assets=values, artifacts=artifacts,
                jobs=[j for j in jobs.listing() if job_project(j) == project_id], draft=json.loads(row['payload']) if row else {},
                capabilities=dict(prompt_interpretation=intent_capability(),text_to_concept=CONCEPT_ADAPTER.installed, concept_engine=CONCEPT_ADAPTER.probe(), text_conditioning=False, image_to_3d=any(a.installed for a in ADAPTERS.values())))


class ConceptInput(BaseModel):
    interpreted_prompt: str | None = Field(default=None,max_length=100000)
    style_reference_ids: list[str] = Field(default_factory=list,max_length=5)
    asset_id: str
    request_id: str = Field(min_length=8,max_length=100)
    prompt: str = Field(min_length=1,max_length=100000)
    quality: Literal['Fast','Balanced','Maximum'] = 'Maximum'
    seed: int = Field(default=42,ge=0,le=4294967295)
    batch_id: str | None = None
    batch_attempt: int = Field(default=0,ge=0)


@router.post('/studio/concept',status_code=201)
def concept(body: ConceptInput):
    from engines.concept_adapter import CONCEPT_ADAPTER
    value=asset(body.asset_id);config=project(value['project_id'])
    if value.get('asset_type','static_3d')!='static_3d':raise HTTPException(409,'This asset type uses its own output route; no universal concept-to-3D substitution')
    if body.batch_id:
        from .batch import batch
        parent=batch(body.batch_id)
        if not any(i['asset_id']==value['id'] for i in parent['items']):raise HTTPException(400,'Asset không thuộc batch')
        config=parent['style_snapshot']
    if not CONCEPT_ADAPTER.installed:raise HTTPException(409,'SDXL local chưa đủ weights/environment; không tải tự động')
    style='; '.join(filter(None,[config.get('default_style'),config.get('material_language'),', '.join(config.get('palette',[]))]))
    bible=config.get('art_bible',{})
    inherited=[]
    if isinstance(bible.get('materials'),list):inherited.extend(bible['materials'])
    if isinstance(bible.get('palette'),dict):inherited.extend(f'{name} {color}' for name,color in bible['palette'].items())
    if isinstance(bible.get('camera'),dict) and bible['camera'].get('projection'):inherited.append(bible['camera']['projection']+' view')
    overrides=value.get('settings',{}).get('style_overrides',{})
    if overrides:inherited.append('Asset style overrides: '+json.dumps(overrides,ensure_ascii=False))
    style='; '.join(filter(None,[style,*inherited]))
    from .reference_direction import concept_direction
    try:directed,reference_direction=concept_direction(body.interpreted_prompt or body.prompt,body.style_reference_ids,value['project_id'])
    except ValueError as exc:raise HTTPException(409,str(exc))
    prompt=directed+('\nGame art direction: '+style if style else '')+'\nSingle isolated game asset, three-quarter view, whole object visible, neutral plain background, coherent geometry, no labels or text.'
    from engines.quality import resolve_concept,fingerprint
    size=768 if body.quality=='Fast' else 1024;steps={'Fast':20,'Balanced':32,'Maximum':50}[body.quality]
    effective=resolve_concept(prompt,body.seed,steps,size,config,body.quality)
    if body.style_reference_ids:effective.update(reference_hashes=[r['sha256'] for r in reference_direction['references']],reference_direction=reference_direction)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');previous=cached(db,body.request_id,request_digest(body))
        if previous:return previous
        result=jobs.enqueue(dict(kind='concept',batch_id=body.batch_id,batch_attempt=body.batch_attempt,project_id=value['project_id'],asset_id=value['id'],name=value['name']+' concept',
            prompt=prompt,user_prompt=body.prompt,reference_direction=reference_direction,project_style_snapshot=config,seed=body.seed,
            steps=steps,size=size,effective_config=effective,effective_config_hash=fingerprint(effective)),db=db)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(body.request_id,request_digest(body),json.dumps(result)))
        value.update(prompt=body.prompt,updated_at=store.now())
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(value),value['id']))
    return result


class ConceptApproval(BaseModel):
    reviewer: str = Field(min_length=1,max_length=100)
    notes: str = Field(default='',max_length=10000)


@router.post('/assets/{identifier}/concepts/{artifact_id}/approve')
def approve_concept(identifier:str,artifact_id:str,body:ConceptApproval):
    value=asset(identifier);record=scoped_artifact(artifact_id,value['project_id'])
    if record['role'] not in ('concept','reference'):raise HTTPException(400,'Cần ảnh concept/reference')
    if not body.reviewer.strip():raise HTTPException(400,'Cần tên người duyệt')
    value.setdefault('concept_approvals',[]).append(dict(artifact_id=artifact_id,sha256=record['sha256'],reviewer=body.reviewer,notes=body.notes,created_at=store.now()))
    value['reference_ids']=list(dict.fromkeys(value['reference_ids']+[artifact_id]))
    return save_asset(value)


class Generate(BaseModel):
    asset_id: str
    request_id: str = Field(min_length=8, max_length=100)
    engine: Literal['auto', 'triposg', 'trellis2_community'] = 'auto'
    quality: Literal['Fast', 'Balanced', 'Maximum'] = 'Maximum'
    artifact_id: str
    prompt: str | None = Field(default=None, max_length=100000)
    seeds: list[int] = Field(default=[42], min_length=1, max_length=5)
    steps: int | None = Field(default=None, ge=1, le=100)
    pipeline_type: Literal['512', '1024_cascade'] | None = None
    texture_size: Literal[2048, 4096] | None = None
    auto_blender: bool = True
    benchmark_height_m: float | None = Field(default=None, gt=0, le=1000)
    batch_id: str | None = None
    batch_attempt: int = Field(default=0,ge=0)
    quality_lock: bool | None = None
    required_stages: list[str] = Field(default_factory=list,max_length=20)


def request_digest(body):
    return hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()


def cached(db, key, fingerprint):
    row = db.execute('SELECT * FROM studio_requests WHERE id=?', (key,)).fetchone()
    if row:
        if row['fingerprint'] != fingerprint: raise HTTPException(409, 'Request ID đã dùng với cấu hình khác')
        return json.loads(row['response'])


@router.post('/studio/generate', status_code=201)
def generate(body: Generate):
    from engines.adapters import ADAPTERS
    value = asset(body.asset_id); config = project(value['project_id'])
    if value.get('asset_type','static_3d')!='static_3d':raise HTTPException(409,'Use the asset-specific World Plan route; a GLB is not a finished level')
    if body.batch_id:
        from .batch import batch
        parent=batch(body.batch_id)
        if not any(i['asset_id']==value['id'] for i in parent['items']):raise HTTPException(400,'Asset không thuộc batch')
        config=parent['style_snapshot']
    source = scoped_artifact(body.artifact_id, value['project_id'])
    if source['role'] not in ('concept', 'reference'): raise HTTPException(400, 'Cần ảnh concept/reference đã chọn')
    automatic_selection=False
    if body.batch_id:
        parent=batch(body.batch_id)
        item=next(i for i in parent['items'] if i['asset_id']==value['id'])
        selection=item.get('automation',{}).get('concept_selection',{})
        automatic_selection=bool(parent.get('automation') and not parent['paused'] and item.get('started') and selection.get('artifact_id')==source['id'] and selection.get('sha256')==source['sha256'])
    if source['metadata'].get('requires_concept_approval') and not automatic_selection and not any(a['artifact_id']==source['id'] and a['sha256']==source['sha256'] for a in value.get('concept_approvals',[])):
        raise HTTPException(409,'Cần duyệt concept thật trước khi tạo 3D')
    if len(set(body.seeds)) != len(body.seeds) or any(not 0 <= s < 2**32 for s in body.seeds):
        raise HTTPException(400, 'Cần 1–4 seed nguyên không trùng trong 0..4294967295')
    engine = body.engine
    if engine == 'auto':
        engine = next((e for e in ('trellis2_community', 'triposg') if ADAPTERS[e].installed and
                       (e != 'triposg' or source['metadata'].get('has_transparency'))), '')
    if engine not in ADAPTERS or not ADAPTERS[engine].installed: raise HTTPException(409, 'Chưa có engine local phù hợp. Không tạo output giả.')
    if engine == 'triposg' and not source['metadata'].get('has_transparency'): raise HTTPException(400, 'TripoSG cần ảnh PNG có alpha thật')
    quality = body.quality
    payload = dict(kind='inference', batch_id=body.batch_id, batch_attempt=body.batch_attempt,project_id=value['project_id'], asset_id=value['id'], artifact_id=source['id'], engine=engine,
                   prompt=body.prompt if body.prompt is not None else value['prompt'], project_style_snapshot=config,
                   steps=body.steps or (50 if engine == 'triposg' else {'Fast': 12, 'Balanced': 24, 'Maximum': 32}[quality]),
                   pipeline_type=body.pipeline_type or ('512' if quality == 'Fast' else '1024_cascade'),
                   texture_size=body.texture_size or (2048 if quality == 'Fast' else 4096),
                   auto_blender=body.auto_blender, benchmark_height_m=body.benchmark_height_m or config.get('target_height_m'),
                   tournament_id=uuid.uuid4().hex, purpose='evaluation_only', quality=quality,
                   prompt_conditioning='NOT_SUPPORTED_RECORDED_ONLY', auto_selection='prefer proven textured engine, not measured universal quality ranking')
    from engines.quality import resolve, fingerprint
    options=body.model_dump() | dict(engine=engine,prompt=payload['prompt'])
    if options['quality_lock'] is None:options['quality_lock']=body.quality=='Maximum'
    try:effective=resolve(options,source,config)
    except ValueError as exc:raise HTTPException(409,str(exc))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = cached(db, body.request_id, request_digest(body))
        if previous: return previous
        queued=[]
        for seed in body.seeds:
            per_job=effective | dict(seed=seed)
            queued.append(jobs.enqueue(payload | dict(seed=seed,effective_config=per_job,effective_config_hash=fingerprint(per_job)),db=db))
        result = dict(tournament_id=payload['tournament_id'], engine=engine, jobs=queued)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)', (body.request_id, request_digest(body), json.dumps(result)))
        value.update(prompt=payload['prompt'], settings=value.get('settings', {}) | body.model_dump(exclude={'request_id'}), reference_ids=list(dict.fromkeys(value['reference_ids'] + [source['id']])), updated_at=store.now())
        db.execute('UPDATE assets SET payload=? WHERE id=?', (json.dumps(value), value['id']))
    return result


class Export(BaseModel):
    artifact_id: str
    preset: Literal['Master', 'Unity Mobile', 'Unity PC'] = 'Master'
    format: Literal['glb', 'fbx'] = 'glb'
    request_id: str = Field(min_length=8, max_length=100)


@router.post('/assets/{identifier}/export', status_code=201)
def export(identifier: str, body: Export):
    value = asset(identifier); record = scoped_artifact(body.artifact_id, value['project_id'], identifier)
    if record['role'] != 'candidate': raise HTTPException(400, 'Cần model GLB thật để export')
    fingerprint = hashlib.sha256((identifier + request_digest(body)).encode()).hexdigest()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        previous = cached(db, body.request_id, fingerprint)
        if previous: return output_files(previous)
        result = body.model_dump() | dict(id=uuid.uuid4().hex, asset_id=identifier, created_at=store.now(), unity='NOT_TESTED', files=[], validation='QUEUED')
        if body.preset == 'Master' and body.format == 'glb':
            path = store.safe_path(record['relative_path'])
            if store.digest(path) != record['sha256']: raise HTTPException(409, 'Source checksum changed')
            result.update(validation='PASS_FILE_CHECKSUM', files=[dict(name=record['name'] + '.glb', bytes=path.stat().st_size, url=record['url'])])
        else:
            # Existing pipeline preserves source and produces all formats/LODs before success.
            options = {}
            if body.preset != 'Master':
                target = 25000 if body.preset == 'Unity Mobile' else 100000
                ratio = min(.95, target / max(record['metadata'].get('triangles', target), 1))
                options['lod_ratios'] = [min(.95, ratio * 2), ratio, ratio / 2] if body.preset == 'Unity Mobile' else [ratio, ratio / 2, ratio / 4]
                result.update(target_triangles=target, budget_scope='whole source target; per-object minimum can exceed it', quality='NEEDS_REVIEW', baking='NOT_REQUESTED')
            queued = jobs.enqueue(dict(kind='blender', artifact_id=record['id'], project_id=value['project_id'], asset_id=identifier,
                normalize=False, render=False, export_preset=body.preset, **options), db=db)
            result.update(job_id=queued['id'], job=queued)
        db.execute('INSERT INTO asset_exports VALUES (?,?,?)', (result['id'], identifier, json.dumps({k:v for k,v in result.items() if k != 'id'})))
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)', (body.request_id, fingerprint, json.dumps(result)))
    return output_files(result)
