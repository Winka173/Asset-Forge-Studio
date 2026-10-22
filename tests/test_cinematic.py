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
    scene['objects'][0]['tag']='crystal';scene['objects'][1]['tag']='boss';scene['shots'][1]['target_id']='object1'
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
    frames=store.DATA/'cinematic-shot-cache';hashes={p:store.digest(p) for p in frames.rglob('*.png')};assert len(hashes)==96
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
    # Real frame-scoped revisions, not a mocked render or invented reuse count.
    original_video=store.digest(Path(video['metadata']['delivery']))
    current=saved['scene_id']
    for index,(prompt,expected_rendered,expected_reused,expected_duration) in enumerate([
        ('Zoom into the crystal at seconds 3-5',24,72,8),
        ('Cut seconds 6-8',0,72,6),
        ('Make boss reveal more epic',48,48,8),
    ]):
        body=dict(scene_id=saved['scene_id'],base_scene_id=current,prompt=prompt,request_id='actual-cinematic-revision-'+str(index))
        count=len(jobs.listing());planned=c.post('/api/cinematics/refinements/plan',json=body);assert planned.status_code==200,planned.text
        assert len(jobs.listing())==count
        assert Scene.model_validate(planned.json()['scene']).objects==Scene.model_validate(scene).objects and planned.json()['scene']['samples']==8
        revised=c.post('/api/cinematics/refinements',json=body);assert revised.status_code==201,revised.text
        assert c.post('/api/cinematics/refinements',json=body).json()==revised.json()
        current=revised.json()['scene_id'];render=c.post('/api/cinematics/render',json=dict(scene_id=current,request_id='render-real-revision-'+str(index))).json()
        with jobs.resource_slot('cpu'):jobs.Worker().execute(render)
        assert jobs.get(render['id'])['status']=='REVIEW_REQUIRED',jobs.get(render['id']).get('error')
        revised_output=store.DATA/'jobs'/render['id']/'output'
        render_report=json.loads((revised_output/'render_report.json').read_text());qa=json.loads((revised_output/'video_qa.json').read_text())
        assert render_report['rendered_frames']==expected_rendered and render_report['reused_frames']==expected_reused
        assert qa['duration_seconds']==pytest.approx(expected_duration,abs=.01)
        assert qa['source_hashes']==report['source_hashes']
        if index==1:assert [r['sha256'] for r in qa['frame_hashes']]==[r['sha256'] for r in report['frame_hashes'][:72]]
        assert all(store.digest(p)==sha for p,sha in hashes.items())
        assert store.digest(Path(video['metadata']['delivery']))==original_video
    before=len(jobs.listing())
    invalid=c.post('/api/cinematics/refinements',json=dict(scene_id=saved['scene_id'],base_scene_id=current,prompt='Zoom into the crystal at seconds 3-5 and delete the boss',request_id='unsupported-edit-must-not-run'))
    assert invalid.status_code==422 and len(jobs.listing())==before
    detail=c.get('/api/cinematics/assets/'+saved['asset_id']).json()
    assert len(detail['scenes'])==4 and detail['asset']['original_prompt']==scene.get('prompt','')
    # A modified game-facing manifest is rejected even on a cache-only retry.
    manifest_path=Path(video['metadata']['delivery']).parent/'manifest.json';original_manifest=manifest_path.read_bytes()
    modified=json.loads(original_manifest);modified['scene_id']='externally-edited';manifest_path.write_text(json.dumps(modified))
    rejected=jobs.retry(job['id'])
    with jobs.resource_slot('cpu'):jobs.Worker().execute(rejected)
    assert jobs.get(rejected['id'])['status']=='FAILED' and 'manifest differs' in jobs.get(rejected['id'])['error']
    assert json.loads(manifest_path.read_text())['scene_id']=='externally-edited'
    assert store.digest(Path(video['metadata']['delivery']))==original_video
    manifest_path.write_bytes(original_manifest)


def test_exact_timeline_edits_validate_and_preserve_motion(tmp_path,monkeypatch,qa_project):
    from apps.api.cinematic_edits import plan
    from engines.cinematic import shot_caches
    _,data=setup(tmp_path,monkeypatch,qa_project);data['objects'][0]['tag']='crystal'
    scene=Scene.model_validate(data);config=dict(script_sha256='renderer-test',blender='actual-path-is-not-used-for-this-plan-test')
    original=shot_caches(scene,config)
    result=plan(scene,'Cắt giây 2 đến 3');edited=Scene.model_validate(result['scene']);caches=shot_caches(edited,config)
    assert sum(round(s.duration*scene.fps) for s in edited.shots)==84
    assert caches[edited.shots[0].id]['key']==original[scene.shots[0].id]['key']
    assert caches[edited.shots[1].id]['start_frame']==36
    assert caches[edited.shots[1].id]['key']==original[scene.shots[0].id]['key']
    # An edit of an already trimmed timeline still maps back to original frames.
    again=Scene.model_validate(plan(edited,'Cut 00:02-00:03')['scene'])
    assert again.shots[1].id==scene.shots[1].id and sum(round(s.duration*12) for s in again.shots)==72
    for prompt in ('Cut seconds 0-8','Cut seconds 5-2','Cut seconds 8-10','Zoom into unknown at seconds 1-2','Make it better'):
        with pytest.raises(ValueError):plan(scene,prompt)


def test_shared_frame_cache_lease_waits_and_stops_without_writing(tmp_path,monkeypatch,qa_project):
    import threading,time
    from engines.cinematic import shot_caches
    c,data=setup(tmp_path,monkeypatch,qa_project)
    saved=c.post('/api/cinematics/scenes',json=dict(scene=data,request_id='frame-lease-scene')).json()
    response=c.post('/api/cinematics/render',json=dict(scene_id=saved['scene_id'],request_id='frame-lease-render'))
    if response.status_code!=201:pytest.skip('Real configured Blender/media tools unavailable')
    job=response.json();cache=shot_caches(Scene.model_validate(data),job['payload']['effective_config'])
    key=min(value['key'] for value in cache.values());worker=jobs.Worker()
    with jobs.file_lock(store.DATA/'cinematic-frame-locks'/(key+'.lock')):
        thread=threading.Thread(target=worker.execute,args=(job,));thread.start()
        log=store.DATA/'jobs'/job['id']/'worker.log'
        try:
            for _ in range(100):
                if log.exists() and 'Waiting for shared frame cache' in log.read_text():break
                time.sleep(.05)
            assert log.exists() and 'Waiting for shared frame cache' in log.read_text()
            assert not (log.parent/'process.json').exists()
        finally:worker.stop.set();thread.join(timeout=10)
    assert not thread.is_alive() and jobs.get(job['id'])['status']=='BLOCKED'
    assert not list((store.DATA/'cinematic-shot-cache').rglob('*.png'))
