"""Exit checkpoints control admission; no generation or successful QA is simulated."""
import pytest
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs,production,automation
from apps.api.main import app,shutdown_jobs

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def queued(client,name='Exit checkpoint'):
    asset=client.post('/api/assets',json=dict(project_id='runavelle',name=name,prompt='Original input')).json()
    job=jobs.enqueue(dict(kind='inference',project_id='runavelle',asset_id=asset['id']))
    return asset,job

def test_exit_holds_new_stages_without_cancelling_and_keep_open_restores_previous_queue(client,monkeypatch):
    asset,first=queued(client);second=jobs.enqueue(dict(kind='inference',project_id='runavelle',asset_id=asset['id']))
    jobs.transition(first['id'],'RUNNING');monkeypatch.setenv('AFS_API_TOKEN','local-exit-test-token');headers={'X-AFS-Token':'local-exit-test-token'}
    response=client.post('/api/desktop/prepare-exit',headers=headers);assert response.status_code==200
    assert response.json()['active_jobs']==1 and response.json()['cancelled_jobs']==0
    assert production.global_paused() and len(shutdown_jobs())==1
    assert jobs.get(first['id'])['status']=='RUNNING' and jobs.get(second['id'])['status']=='QUEUED'
    client.post('/api/desktop/prepare-exit',headers=headers)
    client.post('/api/desktop/cancel-exit',headers=headers)
    assert not production.global_paused() and production.eligible(jobs.get(second['id'])['payload'])
    assert studio.asset(asset['id'])['prompt']==asset['prompt'] and len(jobs.listing())==2

def test_exit_checkpoint_does_not_undo_a_later_explicit_user_pause(client):
    production.prepare_exit_checkpoint()
    client.post('/api/production/control',json=dict(scope='all',action='pause'))
    assert production.restore_exit_checkpoint() is False and production.global_paused()
    production.prepare_exit_checkpoint();production.restore_exit_checkpoint()
    assert production.global_paused()

def test_restart_releases_only_exit_hold_then_applies_project_gpu_recovery_policy(client):
    asset,first=queued(client)
    production.prepare_exit_checkpoint();automation.startup_recovery()
    assert not production.global_paused() and not production.eligible(jobs.get(first['id'])['payload'])
    client.post('/api/production/control',json=dict(scope='all',action='resume'))
    automation.save_project_workflow('runavelle',automation.Workflow(auto_resume=True))
    production.prepare_exit_checkpoint();automation.startup_recovery()
    assert not production.global_paused() and production.eligible(jobs.get(first['id'])['payload'])
    client.post('/api/production/control',json=dict(scope='all',action='pause'))
    production.prepare_exit_checkpoint();automation.startup_recovery()
    assert production.global_paused() and not production.eligible(jobs.get(first['id'])['payload'])

def test_partial_workflow_updates_keep_other_panels_constraints_and_validate_before_save(client):
    from concurrent.futures import ThreadPoolExecutor
    endpoint='/api/automation/projects/runavelle/patch'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda change:client.post(endpoint,json=change),[dict(auto_resume=True),dict(retry_limit=3)]))
    assert all(r.status_code==200 for r in responses)
    client.post(endpoint,json=dict(checkpoints=dict(concept=True)))
    client.post(endpoint,json=dict(checkpoints=dict(export=True),mode='assisted'))
    current=client.get('/api/automation/projects/runavelle').json()
    assert current['auto_resume'] is True and current['retry_limit']==3
    assert current['checkpoints']==dict(concept=True,candidate=False,export=True) and current['mode']=='assisted'
    for body in [dict(retry_limit=99),dict(auto_resume=None),dict(unknown=True),dict(checkpoints=dict(unknown=True))]:
        assert client.post(endpoint,json=body).status_code==422
        assert client.get('/api/automation/projects/runavelle').json()==current
    client.post('/api/production/projects/runavelle/review-policy',json=dict(review_policy='review_flagged'))
    after=client.get('/api/automation/projects/runavelle').json()
    assert after==current|dict(review_policy='review_flagged') and not jobs.listing()
