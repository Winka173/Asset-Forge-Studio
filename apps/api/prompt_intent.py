"""Persistent optional prompt interpretation stage in the existing shared queue."""
import json
import hashlib
from . import store,studio,jobs
from engines import intent_adapter


def capability():
    return dict(available=intent_adapter.available(),model='qwen3-vl:4b-instruct-q4_K_M',
        input_modalities=['text','image'],execution='CPU only / shared queue',
        verification='Local interpretation is inferred, not artistic approval. Critical constraints remain reviewable.',
        reason=None if intent_adapter.available() else 'Local Qwen3-VL weights/runtime not available. No paid/cloud fallback or automatic download.')


def execute(job,folder):
    payload=job['payload'];identifier=job['id'];model=studio.asset(payload['asset_id'])
    text=payload['original_prompt']
    if hashlib.sha256(text.encode()).hexdigest()!=payload['source_prompt_sha256']:raise ValueError('Original intent prompt checksum changed')
    references=[studio.scoped_artifact(r,model['project_id']) for r in payload.get('reference_ids',[])]
    if [r['sha256'] for r in references]!=payload['reference_hashes']:raise ValueError('Intent reference hashes changed')
    prior=None
    if payload.get('retry_of'):
        source=store.DATA/'jobs'/payload['retry_of']/'intent-checkpoint.json'
        receipt=source.with_suffix('.sha256')
        if source.is_file() and receipt.is_file() and store.digest(source)==receipt.read_text().strip():prior=json.loads(source.read_text(encoding='utf-8'))
    def checkpoint(value):
        target=folder/'intent-checkpoint.json';temporary=folder/'intent-checkpoint.json.part'
        temporary.write_text(json.dumps(value,indent=2),encoding='utf-8');temporary.replace(target)
        receipt=target.with_suffix('.sha256');temp_receipt=receipt.with_suffix('.part')
        temp_receipt.write_text(store.digest(target));temp_receipt.replace(receipt)
    with (folder/'worker.log').open('a',encoding='utf-8') as log:
        def progress(message):log.write('STAGE '+message+'\n');log.flush()
        try:
            result=intent_adapter.interpret(text,references,payload['project_style_snapshot'],payload.get('reference_usage','auto'),progress,
                cancelled=lambda:jobs.get(identifier)['status']=='CANCELLED',checkpoint=checkpoint,prior=prior)
        except (OSError,ValueError,TimeoutError) as exc:
            import re
            usage=payload.get('reference_usage','auto')
            from engines.intent_adapter import MATCH_PHRASES
            # Without the model, only an explicit wish to match the image (or style words) makes it a style reference.
            from .size_rules import english_hint
            # CLIP cannot read Vietnamese: lead with a deterministic English subject ('giant red dragon'); the original stays after it.
            hint=english_hint(text)
            role='none' if not references else usage if usage in ('source','style') else 'style' if re.search(r'style|phong cách|màu|giống',text,re.I) or MATCH_PHRASES.search(text) else 'source'
            result=dict(schema_version=4,status='not_evaluated',model=None,model_digest=None,execution='deterministic_fallback',
                source_prompt_sha256=payload['source_prompt_sha256'],references=[dict(artifact_id=r['id'],sha256=r['sha256']) for r in references],
                chunks=[],reference_role=role,generation_prompt_en=(hint+'. '+text) if hint else text,provenance='defaulted_original_text'+('_with_english_subject_hint' if hint else ''),artistic_approval=False,qa_status='not_run',
                warnings=['Local interpretation unavailable; original request preserved: '+str(exc)[:500]])
    if jobs.get(identifier)['status']=='CANCELLED':return
    target=folder/'intent.json';temporary=folder/'intent.json.part'
    temporary.write_text(json.dumps(result,indent=2),encoding='utf-8');temporary.replace(target)
    artifact=store.add_artifact(target,'prompt_interpretation','Local prompt interpretation',dict(
        project_id=model['project_id'],asset_id=model['id'],job_id=identifier,source_prompt_sha256=result['source_prompt_sha256'],
        model=result['model'],model_digest=result['model_digest'],origin='local_qwen3_vl',artistic_approval=False))
    (folder/'manifest.json').write_text(json.dumps(dict(interpretation_artifact=artifact['id'],sha256=artifact['sha256'])),encoding='utf-8')
    jobs.transition(identifier,'GENERATED');jobs.transition(identifier,'VALIDATING')
    if store.digest(target)!=artifact['sha256']:raise ValueError('Saved interpretation checksum mismatch')
    jobs.transition(identifier,'REVIEW_REQUIRED')


def admit(value,item,current,auto):
    """Returns True while the interpretation stage is pending. Never enqueues twice on refresh."""
    if not item.get('interpret_prompt'):return False
    completed=[j for j in current if j['payload']['kind']=='prompt_analysis' and j['status']=='REVIEW_REQUIRED']
    if not completed:
        if not any(j['payload']['kind']=='prompt_analysis' for j in current):
            refs=list(dict.fromkeys(item.get('intent_reference_ids',[])))
            records=[studio.scoped_artifact(r,value['project_id']) for r in refs]
            jobs.enqueue(dict(kind='prompt_analysis',engine='qwen3_vl_local_cpu',project_id=value['project_id'],asset_id=item['asset_id'],
                batch_id=value['id'],batch_attempt=item['attempt'],original_prompt=item['prompt'],source_prompt_sha256=hashlib.sha256(item['prompt'].encode()).hexdigest(),
                reference_ids=refs,reference_hashes=[r['sha256'] for r in records],reference_usage=item.get('intent_reference_usage','auto'),
                project_style_snapshot=value['style_snapshot'],use_gpu=False,timeout_seconds=1800,priority=item.get('priority',0)))
        auto.update(status='queued',stage='Understand prompt and reference / local CPU')
        return True
    record_path=store.DATA/'jobs'/completed[-1]['id']/'manifest.json'
    receipt=json.loads(record_path.read_text(encoding='utf-8'))
    artifact=studio.scoped_artifact(receipt['interpretation_artifact'],value['project_id'],item['asset_id'])
    path=store.safe_path(artifact['relative_path'])
    if store.digest(path)!=receipt['sha256'] or artifact['sha256']!=receipt['sha256']:raise ValueError('Interpretation checkpoint checksum changed')
    result=json.loads(path.read_text(encoding='utf-8'))
    if result['source_prompt_sha256']!=hashlib.sha256(item['prompt'].encode()).hexdigest():raise ValueError('Interpretation no longer matches original prompt')
    if item.get('intent_reference_scope')=='palette_only':
        result['generation_prompt_en']='\n'.join(r['interpretation']['translated_prompt_en'] for r in result['chunks']) or item['prompt']
        result['style_application']='Measured palette only by explicit user selection; semantic traits were not applied'
    item['prompt_interpretation']=result
    # The interpreted subject ('giant red dragon boss') sizes provisional dimensions better than the raw prompt.
    subject=(result.get('chunks') or [{}])[0].get('interpretation',{}).get('requested_subject_en')
    if subject:
        from .size_rules import apply as apply_size_rule
        if apply_size_rule(item,subject):studio.patch_resolved_specification(item['asset_id'],dict(dimensions={k:item.get(k) for k in ('target_width_m','target_depth_m','target_height_m')}))
    refs=item.get('intent_reference_ids',[])
    item['reference_ids']=refs if result['reference_role']=='source' else []
    item['style_reference_ids']=refs if result['reference_role']=='style' else []
    studio.patch_resolved_specification(item['asset_id'],dict(prompt_interpretation=result,generation_prompt_en=result['generation_prompt_en']))
    return False
