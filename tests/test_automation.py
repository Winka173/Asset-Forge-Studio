import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs,batch,automation
from apps.api.main import app


@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)


def test_actual349_dry_plan_and_bounded_automatic_queue(client):
    source=Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md'
    if not source.is_file():pytest.skip('Actual Runavelle source unavailable')
    response=client.post('/api/batches/import',files=dict(file=(source.name,source.read_bytes())),data=dict(project_id='runavelle',mode='Maximum Quality Batch'))
    assert response.status_code==201,response.text[:500]
    value=response.json();prefix='/api/batches/'+value['id']
    assert len(value['items'])==349 and sum(i['selected'] for i in value['items'])==349
    dry=client.post(prefix+'/run-all',json=dict(dry_run=True)).json()
    assert dry['plan']['total']==349 and dry['plan']['future']==37 and jobs.listing()==[]
    assert all(i['spec_provenance'] for i in dry['items'])
    assert dry['items'][0]['spec_provenance']['target_width_m']['kind']=='explicit'
    last=dry['items'][-1]['spec_provenance']['target_width_m']  # a recognised type gets a provisional type-based size, otherwise the category default
    assert last['kind']=='defaulted' or (last['kind']=='inferred' and last['source'].startswith('Asset-type size rule') and last['provisional'])
    response=client.post(prefix+'/run-all',json={});assert response.status_code==200,response.text[:500]
    assert 0<len(jobs.listing())<=2
    persisted=batch.batch(value['id']);assert sum(i['started'] for i in persisted['items'])==349
    assert all(not i['confirmed'] for i in persisted['items'])
    before={j['id'] for j in jobs.listing()};client.post(prefix+'/control',json=dict(action='pause'));automation.advance(value['id']);assert before=={j['id'] for j in jobs.listing()}
    assert batch.batch(value['id'])['paused']
    client.post(prefix+'/control',json=dict(action='resume'));assert before=={j['id'] for j in jobs.listing()}
    automation.startup_recovery();assert batch.batch(value['id'])['paused']


def test_recovery_opt_in_and_explicit_pause_remain_durable(client):
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Tower')).json();identifier=value['id']
    settings=automation.Workflow(auto_resume=True).model_dump()
    automation.start(identifier,workflow=settings)
    automation.startup_recovery();assert not batch.batch(identifier)['paused']
    client.post('/api/batches/'+identifier+'/control',json=dict(action='pause'))
    automation.startup_recovery();assert batch.batch(identifier)['paused']
    assert not app.openapi()['paths']['/api/automation/single']['post'].get('deprecated',False)


def test_single_auto_idempotency_and_source_seeds(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Tower',prompt='A tall stone archer tower')).json()
    body=dict(asset_id=model['id'],request_id='single-auto-durable-test',quality='Maximum',engine='trellis2_community',seeds=[91,92])
    first=client.post('/api/automation/single',json=body);assert first.status_code==201,first.text[:500]
    second=client.post('/api/automation/single',json=body);assert second.status_code==201,second.text[:500]
    assert first.json()['batch_id']==second.json()['batch_id']
    row=batch.batch(first.json()['batch_id'])['items'][0]
    assert row['seeds']==[91,92] and row['quality_lock'] and row['candidates']==2
    assert not row['automation']['human_approved']
    assert len(jobs.listing())==1
    bad=dict(body,seeds=[1]);assert client.post('/api/automation/single',json=bad).status_code==409


def test_explicit_engine_policy_not_silently_changed(client):
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt=json.dumps([dict(name='Shape only',prompt='Tower',preferred_engine='triposg')]),format='json')).json()
    result=automation.start(value['id'])
    # The explicit engine is kept (never swapped for the default); it cuts the subject out itself, so no alpha is required.
    assert result['items'][0]['automation']['engines']==['triposg']


def test_project_edit_preserves_workflow_and_delivery_preferences(client):
    assert client.post('/api/automation/projects/runavelle',json=automation.Workflow(auto_resume=True).model_dump()).status_code==200
    assert client.post('/api/export-profiles/projects/runavelle',json=dict(manifest=False)).status_code==200
    response=client.post('/api/projects/runavelle',json=dict(name='Renamed Runavelle',description='Preserve saved presets'))
    assert response.status_code==200,response.text
    assert automation.project_workflow('runavelle')['auto_resume']
    from apps.api.export_profiles import resolve_project_settings
    assert not resolve_project_settings('runavelle')['manifest']


def test_batch_style_snapshot_survives_project_edit(client):
    client.post('/api/projects/runavelle',json=dict(name='Runavelle',default_style='Original navy and ivory'))
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Tower')).json()
    client.post('/api/projects/runavelle',json=dict(name='Runavelle',default_style='Future project style'))
    automation.start(value['id'])
    concept=jobs.listing()[0]
    assert concept['payload']['project_style_snapshot']['default_style']=='Original navy and ivory'
    assert 'Future project style' not in concept['payload']['prompt']


def test_blocked_concepts_do_not_starve_independent_asset(client,monkeypatch):
    from apps.api import concept_guard
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Rejected A\n- Rejected B\n- Independent prop')).json()
    def reject(value,item,current,choices,auto):
        if item['name'].startswith('Rejected'):
            auto.update(status='blocked',stage='concept QA',error='Injected negative outcome; no successful AI result mocked')
            return None
        return choices
    monkeypatch.setattr(concept_guard,'filter_choices',reject)
    automation.start(value['id'],workflow=automation.Workflow(prompt_interpretation=False).model_dump())
    queued=jobs.listing()
    assert len(queued)==1
    assert queued[0]['payload']['asset_id']==value['items'][2]['asset_id']
    assert queued[0]['payload']['kind']=='concept'
    automation.advance(value['id']);assert len(jobs.listing())==1


def test_engine_hold_does_not_admit_jobs_or_starve_other_route(client,monkeypatch):
    from apps.api import engine_health
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Held A\n- Held B\n- Independent prop')).json()
    held={i['asset_id'] for i in value['items'][:2]}
    monkeypatch.setattr(engine_health,'waiting',lambda payload,job_id=None:dict(code='ENGINE_ROUTE_QUARANTINED',reason='Injected environment hold',health_key='fixture') if payload.get('asset_id') in held else None)
    automation.start(value['id'],workflow=automation.Workflow(prompt_interpretation=False).model_dump())
    for _ in range(3):automation.advance(value['id'])
    assert len(jobs.listing())==1
    assert jobs.listing()[0]['payload']['asset_id']==value['items'][2]['asset_id']
    states=batch.batch(value['id'])['items']
    assert all(i['automation']['status']=='queued' for i in states[:2])
    # Existing quarantined queued stages also must not consume the window.
    for i in states[:2]:jobs.enqueue(dict(kind='concept',asset_id=i['asset_id'],batch_id=value['id'],batch_attempt=0))
    third=next(j for j in jobs.listing() if j['payload']['asset_id']==value['items'][2]['asset_id']);jobs.transition(third['id'],'CANCELLED')
    current=batch.batch(value['id']);current['items'][2]['attempt']=1;batch.save(batch.stored(current))
    automation.advance(value['id'])
    assert len(jobs.listing())==4
    fresh=[j for j in jobs.listing() if j['payload'].get('batch_attempt')==1]
    assert len(fresh)==1 and fresh[0]['payload']['asset_id']==value['items'][2]['asset_id']


def test_resolved_specification_merge_preserves_versions_and_review(client):
    from apps.api import studio
    model=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Immutable',prompt='Original prompt'))
    model.update(art_review_status='approved',publication_history=[dict(artifact_id='retained')],resolved_specification=dict(existing='kept'))
    studio.save_asset(model)
    studio.patch_resolved_specification(model['id'],dict(strategy='new metadata'))
    updated=studio.asset(model['id'])
    assert updated['prompt']=='Original prompt' and updated['art_review_status']=='approved'
    assert updated['publication_history']==model['publication_history']
    assert updated['resolved_specification']==dict(existing='kept',strategy='new metadata')


def test_permanent_admission_error_waits_for_explicit_retry(client,monkeypatch):
    from apps.api import studio
    from fastapi import HTTPException
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Prop')).json()
    calls=[]
    def blocked(body):
        calls.append(body.request_id)
        raise HTTPException(409,'Injected configuration blocker, no generated output')
    monkeypatch.setattr(studio,'concept',blocked)
    automation.start(value['id'],workflow=automation.Workflow(prompt_interpretation=False).model_dump())
    for _ in range(3):automation.advance(value['id'])
    assert len(calls)==1 and not jobs.listing()
    assert batch.batch(value['id'])['items'][0]['automation']['retry_required']
    batch.item_action(value['id'],value['items'][0]['asset_id'],batch.Control(action='retry'))
    assert len(calls)==2


def test_explicit_regeneration_replans_legacy_attempt_without_mutating_history(client):
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Procedural blockout castle')).json()
    legacy=value['items'][0];legacy.update(started=True,attempt=0)
    legacy.pop('planner_version',None)
    legacy['automation']=dict(enabled=True,engines=['trellis2_community'],attempt=0,status='blocked',stage='Old concept',checkpoints={})
    batch.save(batch.stored(value))
    old=jobs.enqueue(dict(kind='concept',project_id='runavelle',batch_id=value['id'],asset_id=legacy['asset_id'],batch_attempt=0))
    jobs.transition(old['id'],'CANCELLED')
    result=automation.start(value['id'],workflow=automation.Workflow(prompt_interpretation=False).model_dump())
    assert not batch.batch(value['id'])['items'][0].get('planner_version')
    batch.item_action(value['id'],legacy['asset_id'],batch.Control(action='regenerate'))
    current=batch.batch(value['id'])['items'][0]
    assert current['attempt']==1 and current['planner_version']==1
    assert current['prompt']==legacy['prompt'] and current['asset_id']==legacy['asset_id']
    assert current['asset_generation_spec']['route']=='procedural_castle'
    assert jobs.get(old['id'])['status']=='CANCELLED'


def test_single_uses_confirmed_size_preview_dimensions(client):
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Barrel',prompt='A wooden supply barrel')).json()
    body=dict(asset_id=model['id'],request_id='size-preview-single',quality='Fast',engine='trellis2_community',seeds=[42],target_width_m=0.8,target_depth_m=0.8,target_height_m=1.1)
    group=client.post('/api/automation/single',json=body).json()['batch_id']
    item=batch.batch(group)['items'][0]
    assert (item['target_width_m'],item['target_depth_m'],item['target_height_m'])==(0.8,0.8,1.1)
    assert item['spec_provenance']['target_height_m']['kind']=='explicit' and 'Size & scale' in item['spec_provenance']['target_height_m']['source']


def test_auto_uses_the_default_engine_and_ticked_engines_run_each(monkeypatch):
    from apps.api.automation import plan_engines
    from engines.adapters import ADAPTERS
    for adapter in ADAPTERS.values(): monkeypatch.setattr(adapter, 'probe', lambda: dict(installed=True))
    alpha = dict(metadata=dict(has_transparency=True))
    item = dict(preferred_engine='auto', quality='Maximum')
    assert plan_engines(item, alpha) == ['trellis2_community']
    assert plan_engines(dict(item, engines=['trellis2_community', 'hunyuan3d21', 'triposg']), alpha) == ['trellis2_community', 'hunyuan3d21', 'triposg']
    # Shape engines cut the subject out themselves, so an image without alpha (or a concept still to come) keeps them.
    assert plan_engines(dict(item, engines=['trellis2_community', 'triposg']), None) == ['trellis2_community', 'triposg']
