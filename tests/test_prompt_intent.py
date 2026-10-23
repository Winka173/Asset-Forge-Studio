import hashlib
import json
import pytest
from pydantic import ValidationError
from apps.api import store,studio,jobs,prompt_intent
from engines import intent_adapter


def interpretation_contract(monkeypatch,tmp_path,role):
    """Declared schema fixture only, not evidence of real AI understanding."""
    from PIL import Image
    monkeypatch.setattr(store,'DATA',tmp_path)
    source=tmp_path/'unit-reference.png';Image.new('RGBA',(32,32),(50,80,120,255)).save(source)
    record=store.add_artifact(source,'reference','Declared parser-test reference',{})
    monkeypatch.setattr(intent_adapter,'model',lambda:dict(name='declared-schema-fixture',digest='schema-only'))
    monkeypatch.setattr(intent_adapter.local_semantics,'probe',lambda:dict(models=[dict(name='declared-schema-fixture',digest='schema-only')]))
    answer=dict(translated_prompt_en='Reconstruct 1 tower, height 9 m.',requested_subject_en='tower',reference_role=role,
        appearance=dict(colors=['blue'],materials=['stone'],surface_treatment='stone',rendering_aesthetic='stylized'))
    calls=[]
    def request(route,body,timeout):
        calls.append(body)
        if len(calls)==1:content=answer
        else:
            assert role=='style','Source reconstruction must never request a new concept plan'
            content=dict(description_en='1 castle, height 9 m.',inferred_ordinary_details=[])
        return dict(done=True,done_reason='stop',message=dict(content=json.dumps(content)))
    monkeypatch.setattr(intent_adapter.local_semantics,'request',request)
    return record,answer,calls


def test_source_translation_survives_without_unused_concept_call(tmp_path,monkeypatch):
    record,answer,calls=interpretation_contract(monkeypatch,tmp_path,'source');saved=[]
    result=intent_adapter.interpret(answer['translated_prompt_en'],[record],{},'source',lambda _:None,checkpoint=saved.append)
    assert len(calls)==1 and result['generation_prompt_en']==answer['translated_prompt_en']
    assert result['chunks'][0]['concept_planning']['status']=='skipped'
    assert result['chunks'][0]['planning_duration_ns'] is None
    assert not result['chunks'][0]['generation_plan']['inferred_ordinary_details']
    calls.clear()
    resumed=intent_adapter.interpret(answer['translated_prompt_en'],[record],{},'source',lambda _:None,prior=saved[-1])
    assert not calls and resumed['chunks']==result['chunks']


def test_style_still_requires_independent_text_only_concept_plan(tmp_path,monkeypatch):
    record,answer,calls=interpretation_contract(monkeypatch,tmp_path,'style')
    result=intent_adapter.interpret(answer['translated_prompt_en'],[record],{},'style',lambda _:None)
    assert len(calls)==2 and result['reference_role']=='style'
    assert calls[0]['messages'][1]['images']
    assert 'images' not in calls[1]['messages'][1]
    assert 'concept_planning' not in result['chunks'][0]


def test_source_still_rejects_dropped_explicit_numbers(tmp_path,monkeypatch):
    record,answer,calls=interpretation_contract(monkeypatch,tmp_path,'source')
    with pytest.raises(ValueError,match='dropped explicit numbers'):
        intent_adapter.interpret('Reconstruct 1 tower, height 12 m.',[record],{},'source',lambda _:None)
    assert len(calls)==1


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
    # An unavailable OPTIONAL interpreter is explicit NOT_EVALUATED, never fake
    # understanding/QA or a mandatory blocker for deterministic supported routes.
    monkeypatch.setattr(intent_adapter.intent_runtime,'installed',lambda:False)
    jobs.worker.execute(current[0])
    assert jobs.get(current[0]['id'])['status']=='REVIEW_REQUIRED'
    manifest=json.loads((tmp_path/'jobs'/current[0]['id']/'manifest.json').read_text())
    report=json.loads(store.safe_path(store.get_artifact(manifest['interpretation_artifact'])['relative_path']).read_text())
    assert report['status']=='not_evaluated' and report['qa_status']=='not_run'
    assert report['generation_prompt_en']==model['prompt'] and not report['artistic_approval']
    assert len(jobs.listing())==1
