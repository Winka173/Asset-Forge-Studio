import io
import sqlite3
import json

import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image
from apps.api import store, jobs
from apps.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    qa_project()
    return TestClient(app)


def test_projects_are_empty_isolated_and_drafts_persist(client):
    first = client.post('/api/projects', json={'name': 'Aetherward', 'default_style': 'painted fantasy'}).json()
    second = client.post('/api/projects', json={'name': 'Forgebound', 'default_style': 'hard surface'}).json()
    for p in [first, second]:
        snapshot = client.get('/api/studio', params={'project_id': p['id']}).json()
        assert snapshot['assets'] == [] and snapshot['artifacts'] == [] and snapshot['jobs'] == []
    a = client.post('/api/assets', json={'project_id': first['id'], 'name': 'Real input asset', 'prompt': 'long prompt ' * 500}).json()
    image = io.BytesIO(); Image.new('RGBA', (16, 16), (0, 0, 0, 0)).save(image, format='PNG')
    uploaded = client.post('/api/import/reference', params={'project_id': first['id'], 'asset_id': a['id']}, files={'file': ('qa.png', image.getvalue())}).json()
    assert client.post('/api/assets', json={'project_id': second['id'], 'name': 'Bad reference', 'reference_ids': [uploaded['id']]}).status_code == 400
    assert client.get('/api/studio', params={'project_id': second['id']}).json()['artifacts'] == []
    client.post(f'/api/projects/{first["id"]}/draft', json={'draft': {'prompt': 'draft text', 'source': uploaded['id']}})
    assert client.get('/api/studio', params={'project_id': first['id']}).json()['draft']['prompt'] == 'draft text'
    assert client.post(f'/api/projects/{first["id"]}/delete', json={'confirm_name': 'wrong'}).status_code == 400
    assert client.post(f'/api/projects/{first["id"]}/delete', json={'confirm_name': first['name']}).json()['files_preserved']
    assert client.get('/api/studio', params={'project_id': first['id']}).status_code == 404
    assert store.get_artifact(uploaded['id'])['sha256'] == uploaded['sha256']


def test_human_master_selection_and_actual_export_keep_versions(client):
    a = client.post('/api/assets', json={'project_id': 'runavelle', 'name': 'QA geometry only'}).json()
    raw = trimesh.creation.box().export(file_type='glb')
    versions = [client.post('/api/import/candidate', params={'asset_id': a['id']}, files={'file': ('qa.glb', raw)}).json() for _ in range(2)]
    for version in versions:
        approval = client.post(f'/api/assets/{a["id"]}/approve', json={'artifact_id': version['id'], 'reviewer': 'QA, not artist acceptance'})
        assert approval.status_code == 200
    assert len(approval.json()['approvals']) == 2
    assert approval.json()['approvals'][0]['mesh_quality_parity'] == 'NOT_TESTED'
    request = dict(artifact_id=versions[1]['id'], request_id='qa-export-unique', preset='Master', format='glb')
    first = client.post(f'/api/assets/{a["id"]}/export', json=request).json()
    repeated = client.post(f'/api/assets/{a["id"]}/export', json=request).json()
    assert first['id'] == repeated['id'] and first['validation'] == 'PASS_FILE_CHECKSUM'
    assert client.get(next(f['url'] for f in first['files'] if f['name']=='Master.glb')).content == raw
    import zipfile
    archive=zipfile.ZipFile(io.BytesIO(client.get(first['files'][0]['url']).content))
    assert archive.read(next(n for n in archive.namelist() if n.endswith('/Master.glb')))==raw
    assert all(n.startswith(first['archive_root']+'/') for n in archive.namelist())
    request['format'] = 'fbx'
    assert client.post(f'/api/assets/{a["id"]}/export', json=request).status_code == 409
    restored = client.get('/api/studio?project_id=runavelle').json()['assets'][0]
    assert len(restored['versions']) == 2 and restored['master_artifact_id'] == versions[1]['id']


def test_generation_request_is_atomic_and_idempotent(client):
    from engines.adapters import ADAPTERS
    if not ADAPTERS['trellis2_community'].installed: pytest.skip('Needs real local engine installation to enqueue')
    a = client.post('/api/assets', json={'project_id': 'runavelle', 'name': 'QA enqueue only'}).json()
    image = io.BytesIO(); Image.new('RGBA', (16, 16), (0, 0, 0, 0)).save(image, format='PNG')
    ref = client.post('/api/import/reference', params={'asset_id': a['id']}, files={'file': ('qa.png', image.getvalue())}).json()
    request = dict(asset_id=a['id'], artifact_id=ref['id'], request_id='qa-generation-once', engine='trellis2_community', seeds=[42])
    first = client.post('/api/studio/generate', json=request)
    assert first.status_code == 201, first.text
    repeated = client.post('/api/studio/generate', json=request).json()
    assert repeated['jobs'][0]['id'] == first.json()['jobs'][0]['id']
    assert len(jobs.listing()) == 1  # Enqueue test only; no inference claimed.
    request['seeds'] = [43]
    assert client.post('/api/studio/generate', json=request).status_code == 409
    identifier = first.json()['jobs'][0]['id']
    jobs.transition(identifier, 'CANCELLED')
    assert jobs.retry(identifier)['id'] == jobs.retry(identifier)['id']


def test_old_database_migrates_without_changing_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    db = sqlite3.connect(tmp_path / 'studio.sqlite')
    db.execute('CREATE TABLE artifacts (id TEXT PRIMARY KEY,role TEXT,name TEXT,relative_path TEXT UNIQUE,sha256 TEXT,created_at TEXT,metadata TEXT)')
    db.execute('INSERT INTO artifacts VALUES (?,?,?,?,?,?,?)', ('old', 'concept', 'Original', 'original.png', 'original-digest', 'before', json.dumps({'kept': True})))
    db.commit(); db.close()
    record = store.get_artifact('old')
    assert record['sha256'] == 'original-digest' and record['metadata']['kept']
    assert record['project_id'] == 'runavelle' and record['asset_id'] == 'archer_tower_t3'


def test_five_distinct_results_are_durable_idempotent_and_never_parallel_gpu(client):
    from engines.adapters import ADAPTERS
    if not ADAPTERS['trellis2_community'].installed:pytest.skip('Real installed TripoSG needed for admission only')
    asset=client.post('/api/assets',json=dict(project_id='runavelle',name='Five seed admission',prompt='Blue roof archer tower',settings={'inspirationGame':'Reference game context'})).json()
    image=io.BytesIO();Image.new('RGBA',(16,16),(0,0,0,0)).save(image,format='PNG')
    reference=client.post('/api/import/reference',params={'asset_id':asset['id']},files={'file':('input.png',image.getvalue())}).json()
    body=dict(asset_id=asset['id'],artifact_id=reference['id'],request_id='five-real-admission',engine='trellis2_community',seeds=[42,43,44,45,46])
    response=client.post('/api/studio/generate',json=body);assert response.status_code==201,response.text
    queued=response.json()['jobs'];assert len(queued)==5 and len(jobs.listing())==5
    assert [j['payload']['seed'] for j in queued]==body['seeds']
    assert all(j['status']=='QUEUED' and jobs.resource_class(j['payload'])=='gpu' for j in queued)
    assert client.post('/api/studio/generate',json=body).json()==response.json()
    assert len(jobs.listing())==5
    assert client.post('/api/studio/generate',json=body|dict(seeds=[1,2,3,4,5,6],request_id='six-blocked-results')).status_code==422
    restored=client.get('/api/studio?project_id=runavelle').json()['assets'][0]
    assert restored['settings']['inspirationGame']=='Reference game context'
