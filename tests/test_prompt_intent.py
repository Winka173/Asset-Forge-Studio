import hashlib
import json
import pytest
from pydantic import ValidationError
from apps.api import store,studio,jobs,prompt_intent
from engines import intent_adapter


def test_interpretation_schema_rejects_untrusted_fields_and_missing_translation():
    with pytest.raises(ValidationError):intent_adapter.Interpretation.model_validate(dict(requested_subject_en='castle',reference_role='style'))
    with pytest.raises(ValidationError):intent_adapter.Interpretation.model_validate(dict(translated_prompt_en='Castle',requested_subject_en='castle',reference_role='style',shell_command='execute me'))


def test_cpu_analysis_admission_is_separate_from_gpu_generation(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    model=studio.create_asset(studio.AssetInput(project_id='runavelle',name='Castle',prompt='Castle, height 12 m'))
    item=dict(interpret_prompt=True,asset_id=model['id'],prompt=model['prompt'],attempt=0,intent_reference_ids=[],intent_reference_usage='auto')
    value=dict(id='analysis-only-batch',project_id='runavelle',style_snapshot=studio.project('runavelle'));auto={}
    assert prompt_intent.admit(value,item,[],auto)
    current=jobs.listing();assert len(current)==1
    assert current[0]['payload']['kind']=='prompt_analysis'
    assert jobs.resource_class(current[0]['payload'])=='cpu'
    assert current[0]['payload']['source_prompt_sha256']==hashlib.sha256(model['prompt'].encode()).hexdigest()
    assert prompt_intent.admit(value,item,current,auto)
    assert len(jobs.listing())==1
    assert studio.asset(model['id'])['prompt']==model['prompt']
    # No engine result/QA is fabricated: an unavailable local model fails before any output.
    monkeypatch.setattr(intent_adapter.intent_runtime,'installed',lambda:False)
    jobs.worker.execute(current[0])
    assert jobs.get(current[0]['id'])['status']=='FAILED'
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]==0
