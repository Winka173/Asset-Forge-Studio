"""Actual licensed GLBs, Blender image sequences and full MP4 decode; no AI output claim."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs
from apps.api.main import app
from apps.api.cinematic import Scene

def setup(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app);objects=[]
    for index,name in enumerate(('RiggedFigure','RiggedSimple')):
        file=store.ROOT/f'.local/fixtures/{name}.glb'
        if not file.is_file():pytest.skip('Actual licensed GLB fixture unavailable')
        asset=client.post('/api/assets',json=dict(project_id='runavelle',name=name,prompt='Licensed technical fixture; not generated Aetherward content')).json()
        record=client.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=asset['id']),files={'file':(file.name,file.read_bytes(),'model/gltf-binary')}).json()
        objects.append(dict(id='object'+str(index),name=name,asset_id=asset['id'],artifact_id=record['id'],sha256=record['sha256'],position=[index*4,0,0]))
    scene=Scene(project_id='runavelle',name='Two actual GLB cinematic',objects=objects,shots=[dict(id='establish',name='Orbit',duration=4,movement='orbit',distance=14),dict(id='reveal',name='Dolly',duration=4,movement='dolly',distance=14)],width=320,height=180,fps=12,samples=8).model_dump()
    return client,scene

def test_scene_snapshot_validation_and_concurrent_save(tmp_path,monkeypatch,qa_project):
    c,scene=setup(tmp_path,monkeypatch,qa_project)
    bad=json.loads(json.dumps(scene));bad['objects'][0]['parent_id']=bad['objects'][1]['id'];bad['objects'][1]['parent_id']=bad['objects'][0]['id']
    assert c.post('/api/cinematics/scenes',json=dict(scene=bad,request_id='invalid-cycle-scene')).status_code==422
    body=dict(scene=scene,request_id='actual-scene-snapshot')
    saved=c.post('/api/cinematics/scenes',json=body);assert saved.status_code==201,saved.text
    assert c.post('/api/cinematics/scenes',json=body).json()==saved.json()
    first=saved.json();path=store.safe_path(store.get_artifact(first['scene_id'])['relative_path']);original=path.read_bytes()
    revised=json.loads(json.dumps(scene));revised['objects'][0]['position'][0]=3
    v2=c.post('/api/cinematics/scenes',json=dict(scene=revised,asset_id=first['asset_id'],base_scene_id=first['scene_id'],request_id='second-real-scene-snapshot'));assert v2.status_code==201,v2.text
    assert c.post('/api/cinematics/scenes',json=dict(scene=scene,asset_id=first['asset_id'],base_scene_id=first['scene_id'],request_id='stale-real-scene-snapshot')).status_code==409
    assert path.read_bytes()==original and not jobs.listing()
    wrong=json.loads(json.dumps(scene));wrong['objects'][0]['sha256']='0'*64
    assert c.post('/api/cinematics/scenes',json=dict(scene=wrong,request_id='bad-source-hash-scene')).status_code==409

def test_real_8_second_multi_glb_Blender_MP4_decode_delivery_and_frame_resume(tmp_path,monkeypatch,qa_project):
    from apps.api.local_tools import executable
    from engines.cinematic import media_tools
    if not executable('blender'):pytest.skip('Actual Blender unavailable')
    try:media_tools()
    except ValueError:pytest.skip('Actual FFmpeg/FFprobe unavailable')
    c,scene=setup(tmp_path,monkeypatch,qa_project)
    saved=c.post('/api/cinematics/scenes',json=dict(scene=scene,request_id='actual-8-second-cinematic')).json()
    body=dict(scene_id=saved['scene_id'],request_id='actual-8-second-render')
    r=c.post('/api/cinematics/render',json=body);assert r.status_code==201,r.text
    assert c.post('/api/cinematics/render',json=body).json()==r.json()
    job=r.json();assert jobs.resource_class(job['payload'])=='cpu'
    with jobs.resource_slot('cpu'):jobs.Worker().execute(job)
    result=jobs.get(job['id']);assert result['status']=='REVIEW_REQUIRED',result.get('error')
    output=store.DATA/'jobs'/job['id']/'output';report=json.loads((output/'video_qa.json').read_text())
    assert report['status']=='PASS_VIDEO_DECODE' and report['frames']==96 and report['duration_seconds']==pytest.approx(8,abs=.1)
    assert len(report['source_hashes'])==2
    frames=store.DATA/'cinematic-cache'/job['payload']['effective_config_hash'];hashes={p:store.digest(p) for p in frames.rglob('*.png')};assert len(hashes)==96
    detail=c.get('/api/cinematics/assets/'+saved['asset_id']).json();video=next(a for a in detail['artifacts'] if a['role']=='cinematic_video')
    assert store.digest(Path(video['metadata']['delivery']))==video['sha256']
    library=c.get('/api/library',params={'project_id':'runavelle'}).json();row=next(v for v in library['items'] if v['id']==saved['asset_id'])
    assert row['production_status']=='completed' and row['art_review_status']=='not_reviewed' and row['thumbnail_kind']=='generated_video'
    # A real retry reuses all checked frames; no inference or model regeneration.
    retried=jobs.retry(job['id'])
    with jobs.resource_slot('cpu'):jobs.Worker().execute(retried)
    assert jobs.get(retried['id'])['status']=='REVIEW_REQUIRED',jobs.get(retried['id']).get('error')
    resumed=json.loads((store.DATA/'jobs'/retried['id']/'output/render_report.json').read_text())
    assert resumed['reused_frames']==96 and resumed['rendered_frames']==0
    assert all(store.digest(p)==sha for p,sha in hashes.items())
