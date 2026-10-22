"""Actual Blender/Unity import, cold reopen and clean package import; no fake native success."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs
from apps.api.main import app
from engines.animation_clip import retime


def test_real_single_clip_unity_package_shared_cpu_queue_and_exact_version_export(tmp_path,monkeypatch,qa_project):
    from apps.api.local_tools import executable
    from engines.unity_editor import probe
    source=store.ROOT/'.local/fixtures/RiggedFigure.glb'
    if not source.is_file() or not probe()['installed'] or not executable('blender'):pytest.skip('Actual licensed fixture, Blender and pinned Unity required')
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Existing animated rig Unity QA',prompt='Preserve the original character')).json()
    original_hash=store.digest(source)
    imported=client.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=model['id']),files={'file':(source.name,source.read_bytes(),'model/gltf-binary')}).json()
    prefix='/api/platform/assets/'+model['id']
    assert client.get(prefix+'/animation-unity',params={'artifact_id':imported['id']}).json()['supported']
    body=dict(artifact_id=imported['id'],profile='6000.4.8f1:Built-in:Animation',render_gpu=False,request_id='actual-unity-animation-validation')
    rejected=client.post(prefix+'/unity-import',json=body|dict(render_gpu=True));assert rejected.status_code==409 and not jobs.listing()
    response=client.post(prefix+'/unity-import',json=body);assert response.status_code==201,response.text
    job=response.json();assert client.post(prefix+'/unity-import',json=body).json()==job
    assert len(jobs.listing())==1 and jobs.resource_class(job['payload'])=='cpu'
    with jobs.resource_slot('cpu'):jobs.Worker().execute(job)
    result=jobs.get(job['id']);assert result['status']=='REVIEW_REQUIRED',result.get('error')
    folder=store.DATA/'jobs'/job['id'];report=json.loads((folder/'manifest.json').read_text())
    assert len(report['reports'])==3 and report['reports'][2]['clean_package_import']
    for evidence in report['reports']:
        assert evidence['checks_passed'] and evidence['bone_count']==19 and evidence['weighted_vertices']>0
        assert evidence['sampled_motion_m']==pytest.approx(evidence['source_motion_m'],abs=.005)
        assert evidence['playable_graph_motion_m']>1e-6
        assert evidence['clip_duration_seconds']==pytest.approx(1.25,abs=1/120)
    exported=client.post('/api/export-profiles/assets/'+model['id'],json=dict(artifact_id=imported['id'],settings=dict(preset='custom',unity_package=True)))
    assert exported.status_code==200,exported.text
    assert any(f['name'].endswith('.unitypackage') for f in exported.json()['files'])
    # A package from v1 must not be offered for v2 of the same stable asset.
    revised=tmp_path/'retimed.glb';retime(source,revised,0,.75)
    v2=client.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=model['id']),files={'file':(revised.name,revised.read_bytes(),'model/gltf-binary')}).json()
    capability=client.get('/api/export-profiles/assets/'+model['id']+'/capabilities',params={'artifact_id':v2['id']}).json()
    assert capability['available']['unity_package'] is False
    detail=client.get('/api/production/assets/'+model['id']).json()
    assert detail['asset']['art_review_status']=='not_reviewed' and store.digest(source)==original_hash
