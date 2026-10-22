import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from pydantic import ValidationError
from apps.api import store,jobs,concept_guard
from apps.api.main import app
from engines.concept_guard import Assessment,checked_assessment


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
