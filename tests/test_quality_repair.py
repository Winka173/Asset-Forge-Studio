"""Negative execution, real receipts and durable admission; no mock AI success."""
import json
import pytest
from PIL import Image
from apps.api import store,studio,jobs,quality_repair,automation,concept_guard,model_guard


@pytest.fixture
def context(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    asset=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Recovery fixture',prompt='Original tower'))
    value=dict(id='repair-test',project_id='runavelle',automation=dict(settings=automation.Workflow().model_dump()))
    item=dict(asset_id=asset['id'],attempt=0,automation={})
    return value,item


def failed_stage(value,item,error):
    job=jobs.enqueue(dict(kind='inference',engine='triposg',asset_id=item['asset_id'],batch_id=value['id'],batch_attempt=0,effective_config_hash='unchanged',steps=50,seed=42))
    jobs.transition(job['id'],'RUNNING');jobs.transition(job['id'],'FAILED',error)
    return jobs.get(job['id'])


def test_interruption_retry_is_atomic_idempotent_and_cause_bounded(context):
    value,item=context;first=failed_stage(value,item,'Server stopped; interrupted')
    plan=quality_repair.planner.stage(value,item,first,jobs.listing())
    assert plan['action']=='retry_stage' and plan['quality_preserved']
    child=quality_repair.submit_stage_retry(plan,first)
    assert child['payload']['seed']==42 and child['payload']['steps']==50
    assert child['payload']['effective_config_hash']=='unchanged'
    assert quality_repair.submit_stage_retry(plan,first)['id']==child['id']
    jobs.transition(child['id'],'RUNNING');jobs.transition(child['id'],'FAILED','Server stopped; interrupted')
    next_plan=quality_repair.planner.stage(value,item,jobs.get(child['id']),jobs.listing())
    assert next_plan['action']=='needs_attention' and 'budget' in next_plan['reason'].lower()
    assert len(jobs.listing())==2


@pytest.mark.parametrize('error',['CUDA out of memory','No module named missing','DLL load failed','TIMEOUT; unchanged','Empty mesh','Checksum mismatch'])
def test_unchanged_failure_conditions_never_trigger_blind_retry(context,error):
    value,item=context;job=failed_stage(value,item,error)
    plan=quality_repair.planner.stage(value,item,job,jobs.listing())
    assert plan['action']=='needs_attention'
    assert quality_repair.submit_stage_retry(plan,job) is None
    assert len(jobs.listing())==1


def test_elapsed_resource_and_disk_budgets_use_real_receipts(context):
    value,item=context;job=failed_stage(value,item,'Server stopped')
    folder=store.DATA/'jobs'/job['id'];folder.mkdir(parents=True)
    (folder/'resources.json').write_text(json.dumps(dict(duration_seconds=8)))
    value['automation']['settings']['repair_budget']['gpu_seconds']=10
    plan=quality_repair.planner.stage(value,item,job,jobs.listing())
    assert plan['action']=='needs_attention' and 'time budget' in plan['reason']
    assert plan['budget']['used']['gpu_seconds']==8
    assert plan['predicted_cost']['seconds']==8


def test_concept_repair_changes_only_relevant_conditioning_and_stops_no_progress(context):
    value,item=context;item['prompt']='One complete tower'
    rejected=[dict(source_sha256='source-one',issues=['cropped_main_object'])]
    plan=quality_repair.planner.concept(value,item,[],rejected)
    assert plan['action']=='repair_concept'
    assert any('camera back' in s for s in plan['instructions'])
    assert item['prompt']=='One complete tower' and not jobs.listing()
    plan['executed_job_id']='receipt-only-negative-test'
    same=quality_repair.planner.concept(value,item,[],[dict(source_sha256='source-two',issues=['cropped_main_object'])])
    assert same['action']=='needs_attention' and 'no-progress' in same['reason']


def test_unavailable_local_evaluator_retains_truthful_receipts(context,monkeypatch):
    from engines import intent_adapter
    value,item=context
    def unavailable():raise ValueError('Injected unavailable local runtime; no AI response fabricated')
    monkeypatch.setattr(intent_adapter,'model',unavailable)
    path=store.DATA/'source.png';Image.new('RGBA',(32,32),(30,60,90,128)).save(path)
    source=store.add_artifact(path,'concept','Actual image fixture',dict(project_id='runavelle',asset_id=item['asset_id']))
    payload=dict(project_id='runavelle',asset_id=item['asset_id'],artifact_id=source['id'],source_sha256=source['sha256'],subject_en='tower',original_prompt='Tower',screening_policy=3)
    check=jobs.enqueue(payload|dict(kind='concept_layout'));folder=store.DATA/'jobs'/check['id'];folder.mkdir(parents=True)
    jobs.transition(check['id'],'RUNNING');concept_guard.execute(check,folder)
    result=concept_guard.receipt(jobs.get(check['id']))
    assert result['evaluation_status']=='NOT_EVALUATED' and result['suitable_single_asset_image'] is None
    assert jobs.get(check['id'])['status']=='REVIEW_REQUIRED'
    views=[dict(view=v,relative_path=source['relative_path'],sha256=source['sha256']) for v in ('front','back','side')]
    check=jobs.enqueue(payload|dict(kind='model_visual_check',renders=views));folder=store.DATA/'jobs'/check['id'];folder.mkdir(parents=True)
    jobs.transition(check['id'],'RUNNING');model_guard.execute(check,folder)
    result=model_guard.receipt(jobs.get(check['id']))
    assert result['evaluation_status']=='NOT_EVALUATED' and not result['artistic_approval']
    assert jobs.get(check['id'])['status']=='REVIEW_REQUIRED'


def test_exhausted_concept_repairs_continue_with_least_defective_concept_without_user_input(context,monkeypatch):
    value,item=context;value['automation']['settings']['retry_limit']=0
    item.update(prompt='Original tower',interpret_prompt=True,reference_ids=[],quality='Maximum')
    images=[]
    for index,colour in enumerate(('navy','teal')):
        path=store.DATA/f'concept{index}.png';Image.new('RGB',(32,32),colour).save(path)
        images.append(store.add_artifact(path,'concept',f'Concept {index}',dict(project_id='runavelle',asset_id=item['asset_id'])))
    issues={images[0]['id']:['missing_requested_subject'],images[1]['id']:['multiple_views_or_panels','missing_requested_subject']}
    def verdict(job):
        image=next(i for i in images if i['id']==job['payload']['artifact_id'])
        return dict(source_artifact_id=image['id'],source_sha256=image['sha256'],screening_policy=job['payload']['screening_policy'],suitable_single_asset_image=False,issues=issues[image['id']])
    monkeypatch.setattr(concept_guard,'receipt',verdict)
    for _ in images:  # one check is admitted per tick; complete it like the worker would
        assert concept_guard.filter_choices(value,item,jobs.listing(),images,{}) is None
        for check in [j for j in jobs.listing() if j['payload']['kind']=='concept_layout' and j['status']=='QUEUED']:
            for state in ('RUNNING','GENERATED','VALIDATING','REVIEW_REQUIRED'):jobs.transition(check['id'],state)
    auto={}
    kept=concept_guard.filter_choices(value,item,jobs.listing(),images,auto)
    assert [k['id'] for k in kept]==[images[0]['id']]
    assert auto.get('status')!='blocked' and auto['auto_decisions'][0]['stage']=='concept_layout'
    assert auto['auto_decisions'][0]['artistic_approval'] is False
    assert not any(j['payload']['kind']=='concept' for j in jobs.listing())  # no extra repair beyond the limit
