"""Bounded concept repair before admitting heavyweight 3D inference."""
import json
import hashlib
from fastapi import HTTPException
from . import store,studio,jobs
from .held_items import concept_conditioning as hand_conditioning


def retry_blocked(value,item,request_id):
    """Explicit idempotent concept-only retry; preserve all previous stages and outputs."""
    if not request_id:raise HTTPException(422,'A persistent concept retry request ID is required')
    key='concept-retry:'+hashlib.sha256(f'{value["id"]}:{item["asset_id"]}:{item["attempt"]}:{request_id}'.encode()).hexdigest()
    with store.connect() as db:
        previous=db.execute('SELECT response FROM studio_requests WHERE id=?',(key,)).fetchone()
    if previous:return dict(ok=True,job=json.loads(previous['response']),reused=True)
    auto=item.get('automation',{})
    if auto.get('status')!='blocked' or 'concept' not in auto.get('stage','').lower():raise HTTPException(409,'Only an asset blocked by concept screening can retry its concept')
    from .production import global_paused
    if value.get('paused') or item.get('production_paused') or global_paused():raise HTTPException(409,'Resume this asset and its containing queue before requesting a new concept')
    current=[j for j in jobs.listing() if j['payload'].get('batch_id')==value['id'] and j['payload'].get('asset_id')==item['asset_id'] and j['payload'].get('batch_attempt',0)==item['attempt']]
    if any(j['status'] not in jobs.TERMINAL for j in current):raise HTTPException(409,'This asset already has pending work; a second concept was not submitted')
    if any(j['payload']['kind']=='inference' for j in current):raise HTTPException(409,'3D generation already exists; use a versioned revision instead')
    count=sum(j['payload']['kind']=='concept' for j in current)
    prompt=repair_prompt(item)
    job=studio.concept(studio.ConceptInput(asset_id=item['asset_id'],request_id=key,prompt=item['prompt'],interpreted_prompt=prompt,directives=[REPAIR_FRAMING,*hand_conditioning(item)[0]],negative_terms=hand_conditioning(item)[1],
        style_reference_ids=item.get('style_reference_ids',[]),quality=item['quality'],seed=42+count,batch_id=value['id'],batch_attempt=item['attempt']))
    auto.pop('error',None);auto.pop('concept_selection',None)
    auto.update(status='queued',stage='New concept requested; original prompt and quality preserved')
    # One explicit retry adds one source. It never resets an unlimited automatic retry loop.
    item.setdefault('concept_retry_history',[]).append(dict(request_id=request_id,job_id=job['id'],seed=42+count,at=store.now()))
    from . import batch
    batch.save(batch.stored(value))
    return dict(ok=True,job=job,reused=False)


# Subject-neutral: architectural wording here turned trees and fountains into buildings.
REPAIR_FRAMING='Exactly ONE connected standalone asset, full silhouette visible, one three-quarter camera view. Plain neutral studio background, generous clear space around every extremity and the base.'


def repair_prompt(item):
    """The description a repair concept is conditioned on; framing and repair instructions travel as directives."""
    interpretation=item.get('prompt_interpretation',{})
    prompt=interpretation.get('generation_prompt_en',item['prompt'])
    if interpretation.get('schema_version',0)<4 and interpretation.get('chunks'):
        prompt='\n'.join(r['interpretation']['translated_prompt_en'] for r in interpretation['chunks'])
        subject=interpretation['chunks'][0]['interpretation'].get('requested_subject_en','game asset')
        prompt='A complete '+subject+'. '+prompt
    return prompt


def execute(job,folder):
    from engines.concept_guard import assess
    p=job['payload'];source=studio.scoped_artifact(p['artifact_id'],p['project_id'],p['asset_id'])
    path=store.safe_path(source['relative_path'])
    if store.digest(path)!=p['source_sha256'] or source['sha256']!=p['source_sha256']:raise ValueError('Concept check source changed')
    with (folder/'worker.log').open('a',encoding='utf-8') as log:
        def progress(message):log.write('STAGE '+message+'\n');log.flush()
        try:result=assess(path,p['subject_en'],p['original_prompt'],progress)
        except (OSError,ValueError,TimeoutError) as exc:
            from .inspection import inspect_image
            measured=inspect_image(path)
            result=dict(schema_version=3,screening_policy=p['screening_policy'],suitable_single_asset_image=None,issues=[],
                evaluation_status='NOT_EVALUATED',observations=[],limitations=['Local semantic evaluation unavailable: '+str(exc)[:500]],
                deterministic_checks=measured,artistic_approval=False,execution='not_evaluated')
    if jobs.get(job['id'])['status']=='CANCELLED':return
    result.update(source_artifact_id=source['id'],source_sha256=source['sha256'])
    target=folder/'concept_layout.json';part=folder/'concept_layout.json.part';part.write_text(json.dumps(result,indent=2),encoding='utf-8');part.replace(target)
    artifact=store.add_artifact(target,'concept_layout_report','Concept layout suitability',dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],
        parent_id=source['id'],source_sha256=source['sha256'],model=result.get('model'),artistic_approval=False))
    (folder/'manifest.json').write_text(json.dumps(dict(concept_layout_artifact=artifact['id'],sha256=artifact['sha256'])),encoding='utf-8')
    # A finished CHECK can report an unsuitable image; it is not a successful model.
    jobs.transition(job['id'],'GENERATED');jobs.transition(job['id'],'VALIDATING');jobs.transition(job['id'],'REVIEW_REQUIRED')


def receipt(job):
    manifest=json.loads((store.DATA/'jobs'/job['id']/'manifest.json').read_text(encoding='utf-8'))
    record=store.get_artifact(manifest['concept_layout_artifact']);path=store.safe_path(record['relative_path'])
    if store.digest(path)!=manifest['sha256'] or record['sha256']!=manifest['sha256']:raise ValueError('Concept layout receipt changed')
    return json.loads(path.read_text(encoding='utf-8'))


def filter_choices(value,item,current,choices,auto):
    """None means still checking/repairing/blocked; otherwise only hash-bound accepted sources."""
    if not item.get('interpret_prompt'):return choices
    from engines.concept_guard import POLICY_VERSION
    allowed=[];rejected=[]
    for image in choices:
        if image['role']!='concept' or image['id'] in item.get('reference_ids',[]):allowed.append(image);continue
        from .quality_evaluation import evaluator_key
        from engines.concept_prompt import subject_anchor
        from engines.quality import fingerprint
        # Deterministic interpretations carry no chunks; the prompt's readable heading names the subject better than a generic label.
        subject=(item.get('prompt_interpretation',{}).get('chunks') or [{}])[0].get('interpretation',{}).get('requested_subject_en') or subject_anchor(item['prompt']) or 'game asset'
        # The checked subject is part of the question, so a verdict for another subject is never reused.
        key=fingerprint(dict(evaluator=evaluator_key(image,item['prompt'],item.get('asset_generation_spec',{}).get('reference_hashes',[]),'concept_guard.py'),subject_en=subject))
        reports=[j for j in current if j['payload']['kind']=='concept_layout' and j['payload']['artifact_id']==image['id'] and j['payload'].get('evaluation_key')==key]
        if not reports:
            jobs.enqueue(dict(kind='concept_layout',engine='qwen3_vl_local_cpu',project_id=value['project_id'],asset_id=item['asset_id'],
                batch_id=value['id'],batch_attempt=item['attempt'],artifact_id=image['id'],source_sha256=image['sha256'],subject_en=subject,
                original_prompt=item['prompt'],screening_policy=POLICY_VERSION,use_gpu=False,timeout_seconds=900,priority=item.get('priority',0),evaluation_key=key))
            auto.update(status='queued',stage='Check concept layout before 3D');return None
        if not all(j['status']=='REVIEW_REQUIRED' for j in reports):auto.update(status='queued',stage='Check concept layout before 3D');return None
        result=receipt(reports[-1])
        if result['source_sha256']!=image['sha256'] or result['source_artifact_id']!=image['id']:raise ValueError('Concept layout bound to a different image')
        if result.get('screening_policy')!=POLICY_VERSION:raise ValueError('Concept screening policy changed; recheck the source before 3D')
        # Soft issues: a corner watermark is removed with the background before image-to-3D (measured: it rejected both red
        # dragons that matched the request); full borders are still caught by the frame-edge check in the tournament.
        if result['suitable_single_asset_image'] is not False or set(result.get('issues',[]))<={'uncertain_source','border_or_text'}:allowed.append(image)
        else:rejected.append(result)
    rejected_ids={r['source_artifact_id'] for r in rejected}
    if rejected_ids:
        studio.patch_resolved_specification(item['asset_id'],dict(concept_layout_checks=rejected))
    if allowed or not rejected:return allowed
    # Only repair concepts count against the limit; the concept tournament's originals are the first attempt.
    count=1+len([j for j in current if j['payload']['kind']=='concept' and j['payload'].get('quality_repair')])
    limit=min(2,value['automation']['settings'].get('retry_limit',1))
    from .quality_repair import planner
    images={image['id']:image for image in choices}
    latest=max(rejected,key=lambda r:images[r['source_artifact_id']].get('created_at',''))
    plan=planner.concept(value,item,current,[latest])
    if count<=limit and plan['action']=='repair_concept':
        job=studio.concept(studio.ConceptInput(asset_id=item['asset_id'],request_id=plan['id'],
            prompt=item['prompt'],interpreted_prompt=repair_prompt(item),directives=[REPAIR_FRAMING,*plan['instructions'],*hand_conditioning(item)[0]],negative_terms=hand_conditioning(item)[1],style_reference_ids=item.get('style_reference_ids',[]),quality=item['quality'],seed=42+count,
            batch_id=value['id'],batch_attempt=item['attempt'],quality_repair=plan))
        plan['executed_job_id']=job['id']
        auto.update(status='queued',stage=f'Concept layout repair {count}/{limit}; quality preserved');return None
    # Auto production never waits for a person: continue with the least-defective concepts and record why.
    fewest=min(len(r.get('issues',[])) for r in rejected)
    kept=sorted(r['source_artifact_id'] for r in rejected if len(r.get('issues',[]))==fewest)
    record_decision(auto,dict(stage='concept_layout',decision='Continued with the least-defective concepts after bounded repairs',reason=plan['reason'],
        kept_artifact_ids=kept,issues=sorted({i for r in rejected if r['source_artifact_id'] in kept for i in r.get('issues',[])})))
    return [image for image in choices if image['id'] in kept]


def record_decision(auto,decision):
    """Idempotent provenance for an automatic decision that replaced a human checkpoint; never an artistic approval."""
    decisions=auto.setdefault('auto_decisions',[])
    if not any(d['stage']==decision['stage'] and d.get('kept_artifact_ids')==decision.get('kept_artifact_ids') for d in decisions):
        decisions.append(dict(decision,at=store.now(),artistic_approval=False))
