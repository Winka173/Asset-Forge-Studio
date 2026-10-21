import io
import json
import zipfile
from pathlib import Path
import trimesh
from fastapi.testclient import TestClient
from apps.api import store
from apps.api.main import app


def test_fresh_library_has_no_projects_and_preserves_created_game(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    client=TestClient(app)
    assert client.get('/api/projects').json()==[]
    empty=client.get('/api/studio').json()
    assert empty['project'] is None and empty['assets']==[] and empty['jobs']==[]
    project=client.post('/api/projects',json=dict(name='My own game')).json()
    with store.connect() as db:assert db.execute('SELECT count(*) FROM assets').fetchone()[0]==0
    assert client.get('/api/projects').json()==[project]
    assert client.get('/api/studio',params=dict(project_id=project['id'])).json()['assets']==[]


def test_actual_export_zip_and_project_folders_do_not_mix(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    client=TestClient(app);raw=trimesh.creation.box(extents=[2,3,4]).export(file_type='glb')
    directories=[]
    for index in range(2):
        # Identical names still have different game IDs and disjoint delivery roots.
        project=client.post('/api/projects',json=dict(name='Same name')).json()
        asset=client.post('/api/assets',json=dict(project_id=project['id'],name='Tower')).json()
        model=client.post('/api/import/candidate',params=dict(project_id=project['id'],asset_id=asset['id']),files=dict(file=('tower.glb',raw))).json()
        body=dict(artifact_id=model['id'],preset='Master',format='glb',request_id=f'isolated-export-{index}')
        url=f'/api/assets/{asset["id"]}/export';response=client.post(url,json=body)
        assert response.status_code==201,response.text
        result=response.json();directory=Path(result['export_directory']);directories.append(directory)
        assert directory.is_relative_to(tmp_path/'exports'/project['id']/asset['id'])
        assert (directory/'Master.glb').read_bytes()==raw
        archive=zipfile.ZipFile(io.BytesIO(client.get(result['files'][0]['url']).content))
        assert archive.read(result['archive_root']+'/Master.glb')==raw
        manifest=json.loads(archive.read(result['archive_root']+'/export-manifest.json'))
        assert manifest['project_id']==project['id'] and manifest['source_artifact_id']==model['id']
        assert client.post(url,json=body).json()['export_directory']==str(directory)
        assert client.get(f'/api/exports/{result["id"]}/files/not-created.fbx').status_code==404
        assert client.get('/api/studio',params=dict(project_id=project['id'])).json()['assets'][0]['exports'][0]['export_directory']==str(directory)
    assert directories[0]!=directories[1]
