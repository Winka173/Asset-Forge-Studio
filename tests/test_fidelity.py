import hashlib
import json
from pathlib import Path
import pytest
import trimesh
from fastapi.testclient import TestClient
from apps.api import store,studio,fidelity
from apps.api.main import app

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def model(client):
    value=client.post('/api/assets',json=dict(project_id='runavelle',name='Tower',prompt='Stone archer tower, blue roof, ballista, height 9 m.')).json()
    path=store.DATA/'measured.glb';path.write_bytes(trimesh.creation.box(extents=[3,9,3]).export(file_type='glb'))
    record=store.add_artifact(path,'candidate','Measured test geometry',dict(project_id='runavelle',asset_id=value['id'],stage='blender_processed'))
    return value,record,path

def test_measured_checks_no_visual_or_artistic_approval_and_idempotent_report(client):
    value,record,path=model(client);url=f'/api/production/assets/{value["id"]}/requirements'
    original=studio.asset(value['id'])['prompt'];r=client.post(url+'/evaluate',json=dict(artifact_id=record['id']));assert r.status_code==200,r.text
    report=r.json();assert report['summary']==dict(measured=1,mismatches=0,unverified=4)
    assert not report['artistic_approval'] and report['visual_evaluation']=='unavailable'
    for requirement in report['contract']['requirements']:
        assert original[requirement['source_start']:requirement['source_end']]==requirement['excerpt']
    assert client.post(url+'/evaluate',json=dict(artifact_id=record['id'])).json()==report
    saved=studio.asset(value['id']);assert saved['prompt']==original and len(saved['fidelity_reports'])==1 and not saved.get('art_reviews')
    assert client.get(url+'?artifact_id='+record['id']).json()['report']['report_id']==report['report_id']
    path.write_bytes(path.read_bytes()+b'changed');assert client.post(url+'/evaluate',json=dict(artifact_id=record['id'])).status_code==409

def test_revision_delta_supersedes_dimension_and_report_is_version_bound(client):
    value,record,path=model(client);value=studio.asset(value['id']);value['revisions']=[dict(id='revision-check',artifact_id=record['id'],effective_prompt=value['prompt']+'\nRevision: Uniformly scale to height 18 m.')];studio.save_asset(value)
    result=fidelity.evaluate(value['id'],record['id']);assert result['summary']['mismatches']==1
    dimensions=[c for c in result['checks'] if c['evidence']];assert len(dimensions)==1 and dimensions[0]['evidence']['expected_m']==18
    assert any(c['status']=='superseded' for c in result['checks'])
    assert result['contract']['source']=='effective_revision_prompt'

def test_actual_runavelle_source_excerpts_remain_lossless():
    path=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    assert path.is_file(),'Actual Runavelle acceptance file is required; do not substitute generated text'
    raw=path.read_bytes();prompt=raw.decode('utf-8-sig');requirements=fidelity.extract(prompt)
    assert len(requirements)>349
    for r in requirements:assert prompt[r['source_start']:r['source_end']]==r['excerpt']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()
