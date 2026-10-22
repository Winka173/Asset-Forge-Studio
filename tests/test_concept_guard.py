import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from apps.api import store,jobs,concept_guard
from apps.api.main import app
from engines.concept_guard import Assessment,checked_assessment


def test_maximum_concept_avoids_negated_layout_keywords_without_rewriting_source():
    from engines.concept_prompt import compose
    original='A castle with 4 towers, height 12 m. No surrounding scenery, panels, or poster layouts are included.'
    positive,negative=compose(original,'ivory limestone and navy slate','Maximum')
    assert '4 towers' in positive and '12 m' in positive
    assert 'panels' not in positive and 'poster' not in positive
    assert 'poster' in negative and 'collage' in negative
    assert 'finely resolved surface relief' in positive
    assert 'No surrounding' in original  # Source text is untouched.


def test_layout_check_admission_is_cpu_only_and_does_not_start_3d(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    model=client.post('/api/assets',json=dict(project_id='runavelle',name='Castle',prompt='One castle')).json()
    stream=io.BytesIO();Image.new('RGB',(16,16),'navy').save(stream,format='PNG')
    image=client.post('/api/import/concept',params=dict(project_id='runavelle',asset_id=model['id']),files=dict(file=('source.png',stream.getvalue()))).json()
    item=dict(asset_id=model['id'],interpret_prompt=True,reference_ids=[],prompt='One castle',attempt=0)
    value=dict(id='layout-admission-test',project_id='runavelle');auto={}
    assert concept_guard.filter_choices(value,item,[],[image],auto) is None
    queued=jobs.listing();assert len(queued)==1 and jobs.resource_class(queued[0]['payload'])=='cpu'
    assert queued[0]['payload']['kind']=='concept_layout'
    assert concept_guard.filter_choices(value,item,queued,[image],auto) is None
    assert len(jobs.listing())==1
    # Corrupt source cannot be submitted to a model, treated as passed or forwarded to 3D.
    store.safe_path(image['relative_path']).write_bytes(b'changed')
    jobs.worker.execute(queued[0]);assert jobs.get(queued[0]['id'])['status']=='FAILED'
    assert not any(j['payload']['kind']=='inference' for j in jobs.listing())


def test_concept_layout_schema_does_not_accept_an_artistic_score():
    with pytest.raises(ValidationError):Assessment.model_validate(dict(suitable_single_asset_image=True,observed_subject_en='castle',artistic_score=100))


def test_observed_defects_override_a_model_suitable_boolean():
    # Schema enforcement is essential even when a model returns contradictory fields.
    answer=checked_assessment(Assessment(suitable_single_asset_image=True,observed_subject_en='castle',
        background_is_plain=False,border_or_text_visible=True,entire_main_asset_visible=False,issues=[]))
    assert not answer.suitable_single_asset_image
    assert set(answer.issues)=={'background_scene','border_or_text','cropped_main_object'}


def test_manual_concept_retry_is_idempotent_and_preserves_quality(tmp_path,monkeypatch,qa_project):
    from apps.api import batch
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- One castle')).json()
    stored=batch.batch(value['id']);item=stored['items'][0]
    item.update(started=True,attempt=0,automation=dict(status='blocked',stage='Needs Attention / concept layout'))
    stored['paused']=False;batch.save(stored)
    body=dict(scope='asset',group_id=stored['id'],asset_id=item['asset_id'],action='retry_concept',request_id='idempotent-concept-retry')
    first=client.post('/api/production/control',json=body);assert first.status_code==200,first.text
    second=client.post('/api/production/control',json=body);assert second.status_code==200,second.text
    assert first.json()['job']['id']==second.json()['job']['id']
    assert len(jobs.listing())==1 and jobs.listing()[0]['payload']['kind']=='concept'
    assert jobs.listing()[0]['payload']['user_prompt']==item['prompt']
    assert jobs.listing()[0]['payload']['effective_config']['quality']==item['quality']
    stored=batch.batch(stored['id']);stored['paused']=True;batch.save(stored)
    assert client.post('/api/production/control',json=body|dict(request_id='different-paused-retry')).status_code==409
