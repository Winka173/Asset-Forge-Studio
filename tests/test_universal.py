import json
import io
import pytest
import trimesh
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from apps.api import store,jobs
from apps.api.main import app
from apps.api.asset_contract import AssetManifest,ArtifactFile
from engines.plugin_sdk import Stage,StageGraph,Plugin,Operation,generation_plugin


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    return TestClient(app)


def stage(identifier,deps=()):
    return Stage(id=identifier,plugin='qa',operation=Operation.validate,depends_on=list(deps),resource='cpu',checkpoint='qa.json',acceptance=['Real files parse'])


def test_dag_and_manifest_safety_contracts():
    with pytest.raises(ValidationError):StageGraph(stages=[stage('a',['b'])])
    with pytest.raises(ValidationError):StageGraph(stages=[stage('a',['b']),stage('b',['a'])])
    with pytest.raises(ValidationError):StageGraph(stages=[stage('a'),stage('a')])
    with pytest.raises(ValidationError):ArtifactFile(path='../outside.glb',sha256='a'*64,bytes=1,role='candidate')
    with pytest.raises(ValidationError):AssetManifest(project_id='p',asset_id='a',version='1',status='game_ready',graph=StageGraph(stages=[]))
    assert Plugin('qa',{Operation.validate:lambda value:value+1}).invoke(Operation.validate,2)==3
    with pytest.raises(ValueError):Plugin('qa',{}).invoke(Operation.generate,{})


def test_real_manifest_file_immutable_master_and_legacy_preserved(client):
    asset=client.post('/api/assets',json=dict(project_id='runavelle',name='Imported QA mesh, not AI generation')).json()
    original=trimesh.creation.box(extents=[2,3,4]).export(file_type='glb')
    imported=client.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=asset['id']),files=dict(file=('qa.glb',original))).json()
    approval=client.post(f'/api/assets/{asset["id"]}/approve',json=dict(artifact_id=imported['id'],reviewer='Technical fixture, not artist approval')).json()
    response=client.post(f'/api/platform/assets/{asset["id"]}/manifest')
    assert response.status_code==201,response.text
    snapshot=response.json();path=store.safe_path(snapshot['relative_path']);manifest=AssetManifest.model_validate_json(path.read_text())
    assert manifest.schema_version=='2.0' and manifest.source_master.sha256==imported['sha256']
    assert manifest.status=='draft'  # Library import is not a successful AI generation or game-ready certification.
    assert manifest.source_master.integrity=='verified'
    assert store.safe_path(imported['relative_path']).read_bytes()==original
    again=client.post(f'/api/platform/assets/{asset["id"]}/manifest').json()
    assert again['id']!=snapshot['id'] and again['relative_path']!=snapshot['relative_path']
    assert path.read_bytes()==client.get(f'/api/artifacts/{snapshot["id"]}/file').content
    with store.connect() as db:
        saved=json.loads(db.execute('SELECT payload FROM assets WHERE id=?',(asset['id'],)).fetchone()[0])
    assert saved['master_artifact_id']==imported['id'] and saved['approvals']==approval['approvals']
    store.safe_path(imported['relative_path']).write_bytes(b'corrupt')
    assert client.post(f'/api/platform/assets/{asset["id"]}/manifest').status_code==409


def test_output_routing_gaps_and_no_gpu_submission(client):
    image=io.BytesIO();Image.new('RGBA',(32,32),(120,90,60,100)).save(image,format='PNG')
    ref=client.post('/api/import/reference',files=dict(file=('qa.png',image.getvalue()))).json()
    request=dict(project_id='runavelle',reference_ids=[ref['id']],input_mode='Image',engine='triposg',desired_outputs=['glb'])
    routed=client.post('/api/platform/route',json=request).json()
    assert not any(s['id']=='concept' for s in routed['graph']['stages'])
    assert routed['dry_run'] and routed['enqueued_jobs']==0 and not jobs.listing()
    pbr=client.post('/api/platform/route',json=request|dict(desired_outputs=['basecolor'])).json()
    assert pbr['status']=='blocked' and any('Shape-only' in s for s in pbr['capability_gaps'])
    audio=client.post('/api/platform/route',json=request|dict(asset_type='audio',desired_outputs=['wav'])).json()
    assert audio['status']=='blocked' and audio['graph']['stages']==[]  # No universal Blender chain.
    commercial=client.post('/api/platform/route',json=request|dict(commercial=True)).json()
    assert commercial['status']=='blocked' and any('Commercial' in s for s in commercial['capability_gaps'])
    other=client.post('/api/projects',json=dict(name='Separate game')).json()
    assert client.post('/api/platform/route',json=request|dict(project_id=other['id'])).status_code==400


def test_project_engine_targets_round_trip(client):
    project=client.post('/api/projects',json=dict(name='Aetherward',target_engines=['unity'],engine_profiles={'unity':{'version':'6000.4.8f1','render_pipeline':'Built-in'}})).json()
    assert project['target_engines']==['unity']
    assert client.post('/api/projects/'+project['id'],json=project|dict(description='Preserved targets')).json()['engine_profiles']==project['engine_profiles']


def test_persistent_dependency_admission_does_not_change_config(client):
    parent=jobs.enqueue(dict(kind='concept',test_fixture='scheduler admission only; no inference result claimed'))
    payload=dict(kind='blender',depends_on=[parent['id']],effective_config={'sentinel':'immutable'})
    child=jobs.enqueue(payload)
    assert jobs.dependency_readiness(child)==('waiting',None)
    jobs.transition(parent['id'],'BLOCKED','Fixture dependency failure')
    state,reason=jobs.dependency_readiness(child)
    assert state=='blocked' and parent['id'] in reason
    assert jobs.get(child['id'])['payload']==payload


def test_native_unity_requires_real_processed_inputs_and_scoped_rights(client):
    asset=client.post('/api/assets',json=dict(project_id='runavelle',name='Unprocessed input')).json()
    mesh=trimesh.creation.box().export(file_type='glb')
    ref=client.post('/api/import/candidate',params=dict(asset_id=asset['id']),files=dict(file=('qa.glb',mesh))).json()
    url=f'/api/platform/assets/{asset["id"]}/unity-import';body=dict(artifact_id=ref['id'],request_id='native-negative-test',render_gpu=True)
    result=client.post(url,json=body)
    assert result.status_code==409 and 'processed LOD0' in result.json()['detail']
    assert client.post(url,json=body|dict(commercial=True)).status_code==409
    assert client.post(url,json=body|dict(profile='unverified-URP')).status_code==422
    assert jobs.listing()==[]
    assert jobs.resource_class(dict(kind='unity_import',use_gpu=True))=='gpu'
    assert jobs.resource_class(dict(kind='unity_import',use_gpu=False))=='cpu'
    assert jobs.resource_class(dict(kind='blender',use_gpu=True))=='gpu'
