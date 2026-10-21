"""Real GLB bytes, measured geometry and unchanged source delivery; no AI mock success."""
import hashlib
import json
from pathlib import Path

import pytest
import trimesh
import numpy as np
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from apps.api import store, studio, export_profiles as exports


def setup_asset(tmp_path, monkeypatch, source_id='TOWER / Archer:T3'):
    monkeypatch.setattr(store,'DATA',tmp_path)
    app=FastAPI();app.include_router(studio.router);app.include_router(exports.router)
    client=TestClient(app)
    project=client.post('/api/projects',json=dict(name='Runavelle')).json()
    value=client.post('/api/assets',json=dict(project_id=project['id'],name='Archer Tower')).json()
    value['settings']['source_asset_id']=source_id;studio.save_asset(value)
    mesh=trimesh.creation.box(extents=[2,3,4])
    mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=trimesh.visual.material.PBRMaterial(baseColorTexture=Image.new('RGB',(4,4),(62,113,91))))
    path=tmp_path/'real-geometry.glb';path.write_bytes(mesh.export(file_type='glb'))
    record=store.add_artifact(path,'candidate','Actual box.glb',dict(project_id=project['id'],asset_id=value['id']))
    return client,project,value,record,path


def test_glb_only_preserves_geometry_hashes_optional_manifest_and_idempotency(tmp_path,monkeypatch):
    client,project,value,record,path=setup_asset(tmp_path,monkeypatch)
    initial=path.read_bytes()
    default=client.get(f'/api/export-profiles/projects/{project["id"]}').json()['settings']
    assert default['preset']=='glb_only' and default['manifest'] and not default['zip'] and not default['fbx']
    endpoint=f'/api/export-profiles/assets/{value["id"]}'
    result=client.post(endpoint,json=dict(artifact_id=record['id']))
    assert result.status_code==200,result.text
    result=result.json();directory=Path(result['export_directory'])
    assert directory.is_relative_to(tmp_path/'exports'/project['id'])
    assert len(list(directory.glob('*.glb')))==1 and not list(directory.glob('*.fbx')) and not list(directory.glob('*.zip'))
    assert (directory/result['filename']).read_bytes()==initial
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['source_asset_id']=='TOWER / Archer:T3'
    assert manifest['dimensions_xyz_m']==[2,3,4] and manifest['glb']==result['filename'] and not Path(manifest['glb']).is_absolute()
    assert manifest['embedded_images']==1 and manifest['materials'][0]['base_color_texture']
    assert manifest['files'][0]['sha256']==hashlib.sha256(initial).hexdigest()
    for file in result['files']:
        response=client.get(file['url']);assert response.status_code==200
        assert hashlib.sha256(response.content).hexdigest()==file['sha256']
    assert client.post(endpoint,json=dict(artifact_id=record['id'])).json()['id']==result['id']
    assert path.read_bytes()==initial
    assert client.get(endpoint).json()[0]['id']==result['id']
    assert client.get(f'/api/export-profiles/exports/{result["id"]}/files/not-real.fbx').status_code==404
    with store.connect() as db:assert db.execute('SELECT count(*) FROM jobs').fetchone()[0]==0
    # A copied version without its completion record is safely resumed from unchanged bytes.
    with store.connect() as db:db.execute('DELETE FROM selective_exports WHERE id=?',(result['id'],))
    resumed=client.post(endpoint,json=dict(artifact_id=record['id']))
    assert resumed.status_code==200,resumed.text
    assert resumed.json()['id']==result['id'] and resumed.json()['created_at']==result['created_at']
    # External game edits are never silently overwritten by re-export.
    (directory/result['filename']).write_bytes(b'user edit')
    response=client.post(endpoint,json=dict(artifact_id=record['id']))
    assert response.status_code==409 and (directory/result['filename']).read_bytes()==b'user edit'
    assert path.read_bytes()==initial


def test_explicit_outputs_persist_per_game_and_do_not_force_extra_formats(tmp_path,monkeypatch):
    client,project,value,record,path=setup_asset(tmp_path,monkeypatch)
    other=client.post('/api/projects',json=dict(name='Other game')).json()
    location=tmp_path/'GameAssets';location.mkdir()
    settings=exports.ExportSettings(manifest=False,zip=False,output_directory=str(location)).model_dump()
    response=client.post(f'/api/export-profiles/projects/{project["id"]}',json=settings)
    assert response.status_code==200,response.text
    assert exports.resolve_project_settings(project['id'])['output_directory']==str(location)
    assert exports.resolve_project_settings(other['id'])['output_directory'] is None
    result=exports.export_asset(project['id'],value['id'],record['id'])
    assert len(result['files'])==1 and Path(result['export_directory']).is_relative_to(location/project['id'])
    assert Path(result['export_directory'],result['filename']).read_bytes()==path.read_bytes()
    for preset in ['unreal']:
        assert client.post(f'/api/export-profiles/projects/{project["id"]}',json=dict(preset=preset)).status_code==422
    response=client.post(f'/api/export-profiles/assets/{value["id"]}',json=dict(settings=dict(preset='custom',fbx=True)))
    assert response.status_code==409 and 'fbx' in response.text
    caps=client.get(f'/api/export-profiles/assets/{value["id"]}/capabilities').json()
    assert caps['available']['glb'] and not caps['available']['fbx'] and not caps['available']['unity_package']
    # The optional archive contains only the explicitly requested actual files.
    result=exports.export_asset(project['id'],value['id'],record['id'],dict(zip=True))
    assert {f['kind'] for f in result['files']}=={'glb','manifest','zip'}
    with pytest.raises(Exception):exports.export_asset(other['id'],value['id'],record['id'])


def test_incremental_project_index_atomic_paths_and_external_edits(tmp_path,monkeypatch):
    client,project,value,record,path=setup_asset(tmp_path,monkeypatch)
    first=exports.export_asset(project['id'],value['id'],record['id'])
    index=Path(first['project_manifest']);one=json.loads(index.read_text(encoding='utf-8'))
    assert len(one['assets'])==1
    entry=one['assets'][value['id']]
    assert not Path(entry['glb']).is_absolute()
    assert store.digest(index.parent/entry['glb'])==entry['sha256']
    another=client.post('/api/assets',json=dict(project_id=project['id'],name='Another real mesh',prompt='Export validation, no inference')).json()
    other_path=tmp_path/'other.glb';other_path.write_bytes(trimesh.creation.icosphere(subdivisions=1).export(file_type='glb'))
    other_record=store.add_artifact(other_path,'candidate','Other actual GLB',dict(project_id=project['id'],asset_id=another['id']))
    second=exports.export_asset(project['id'],another['id'],other_record['id'])
    assert second['project_manifest']==str(index)
    two=json.loads(index.read_text(encoding='utf-8'));assert len(two['assets'])==2 and one['assets'][value['id']]==two['assets'][value['id']]
    assert len(two['history'])==2
    index.write_text('manual game edit',encoding='utf-8')
    response=client.post('/api/export-profiles/assets/'+another['id'],json=dict(artifact_id=other_record['id']))
    assert response.status_code==409 and index.read_text()=='manual game edit'
    assert not list(index.parent.glob('*.part'))
