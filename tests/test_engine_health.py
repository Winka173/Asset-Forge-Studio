"""Real missing-environment execution, not fabricated successful GPU results."""
import io
from PIL import Image
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs,engine_health
from apps.api.main import app
from engines.adapters import ADAPTERS


def test_real_missing_environment_quarantines_exact_route_and_probe_is_idempotent(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    model=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Missing engine test',prompt='Castle'))
    image=io.BytesIO();Image.new('RGBA',(16,16),(30,60,90,128)).save(image,format='PNG')
    source=client.post('/api/import/reference',params=dict(project_id='runavelle',asset_id=model['id']),files=dict(file=('source.png',image.getvalue()))).json()
    monkeypatch.setattr(ADAPTERS['trellis2_community'],'paths',lambda:(tmp_path/'absent-engine',tmp_path/'absent-env/python.exe'))
    # This negative case cannot launch an engine (both executable/source are
    # absent). Isolate its admission lock so a real user GPU job cannot make
    # an environment-failure assertion spuriously observe QUEUED instead.
    # Production and actual CUDA/native acceptance retain the machine lock.
    monkeypatch.setattr(jobs,'WORKER_LOCK',tmp_path/'negative-environment-gpu.lock')
    runner=jobs.Worker()  # Previous TestClient shutdown may have stopped the global worker.
    payload=dict(kind='inference',engine='trellis2_community',project_id='runavelle',asset_id=model['id'],artifact_id=source['id'],seed=42,steps=50,pipeline_type='512',texture_size=4096)
    for _ in range(2):
        job=jobs.enqueue(payload);runner.managed(job,'gpu')
        assert jobs.get(job['id'])['status']=='FAILED'
    records=engine_health.listing()['records'];assert len(records)==1
    record=records[0];assert record['circuit']=='open' and record['root_cause']=='MODEL_DEPENDENCY_MISSING'
    third=jobs.enqueue(payload);runner.managed(third,'gpu');assert jobs.get(third['id'])['status']=='QUEUED'
    assert engine_health.waiting(payload,third['id'])['code']=='ENGINE_ROUTE_QUARANTINED'
    assert engine_health.waiting(dict(kind='prompt_analysis')) is None
    changed=dict(payload,effective_config=dict(inference_steps=32))
    assert engine_health.waiting(changed) is None  # Separate profile, not a global engine ban.
    response=client.post('/api/engine-health/'+record['key']+'/probe',json=dict(request_id='same-probe-request'))
    assert response.status_code==200,response.text
    probe=response.json();assert probe['payload']['seed']==42 and probe['payload']['steps']==50
    assert client.post('/api/engine-health/'+record['key']+'/probe',json=dict(request_id='same-probe-request')).json()['id']==probe['id']
    runner.managed(probe,'gpu');assert jobs.get(probe['id'])['status']=='FAILED'
    assert engine_health.read(record['key'])['circuit']=='open'
    assert not list(tmp_path.rglob('raw.glb'))


def test_taxonomy_distinguishes_environment_content_integrity_and_export():
    assert engine_health.classify('CUDA out of memory')[0]=='CUDA_OOM'
    assert engine_health.classify('process exit 1','DLL load failed')[0]=='CUDA_ABI_CONFLICT'
    assert engine_health.classify('decoder returned empty mesh')[0]=='EMPTY_GEOMETRY'
    assert engine_health.classify('Immutable source checksum changed')[0]=='INPUT_OR_CONFIG_INTEGRITY'
    assert engine_health.classify('GLB export reopen error')[0]=='EXPORT_VALIDATION'


def test_timeout_termination_is_retryable_but_explicit_cancel_remains_cancelled(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    for reason,expected in [('TIMEOUT; EffectiveGenerationConfig unchanged','BLOCKED'),('User cancelled','CANCELLED')]:
        job=jobs.enqueue(dict(kind='concept',effective_config_hash='unchanged'))
        jobs.transition(job['id'],'RUNNING');jobs.transition(job['id'],'CANCELLED',reason);jobs.reconcile_timeout(job['id'])
        actual=jobs.get(job['id']);assert actual['status']==expected and actual['payload']['effective_config_hash']=='unchanged'
