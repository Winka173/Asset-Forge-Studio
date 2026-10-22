"""Bounded concept repair before admitting heavyweight 3D inference."""
import json
from . import store,studio,jobs


def execute(job,folder):
    from engines.concept_guard import assess
    p=job['payload'];source=studio.scoped_artifact(p['artifact_id'],p['project_id'],p['asset_id'])
    path=store.safe_path(source['relative_path'])
    if store.digest(path)!=p['source_sha256'] or source['sha256']!=p['source_sha256']:raise ValueError('Concept check source changed')
    with (folder/'worker.log').open('a',encoding='utf-8') as log:
        def progress(message):log.write('STAGE '+message+'\n');log.flush()
        result=assess(path,p['subject_en'],p['original_prompt'],progress)
    if jobs.get(job['id'])['status']=='CANCELLED':return
    result.update(source_artifact_id=source['id'],source_sha256=source['sha256'])
    target=folder/'concept_layout.json';part=folder/'concept_layout.json.part';part.write_text(json.dumps(result,indent=2),encoding='utf-8');part.replace(target)
    artifact=store.add_artifact(target,'concept_layout_report','Concept layout suitability',dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],
        parent_id=source['id'],source_sha256=source['sha256'],model=result['model'],artistic_approval=False))
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
    allowed=[];rejected=[]
    for image in choices:
        if image['role']!='concept' or image['id'] in item.get('reference_ids',[]):allowed.append(image);continue
        reports=[j for j in current if j['payload']['kind']=='concept_layout' and j['payload']['artifact_id']==image['id']]
        if not reports:
            subject=item.get('prompt_interpretation',{}).get('chunks',[{}])[0].get('interpretation',{}).get('requested_subject_en','game asset')
            jobs.enqueue(dict(kind='concept_layout',engine='qwen3_vl_local_cpu',project_id=value['project_id'],asset_id=item['asset_id'],
                batch_id=value['id'],batch_attempt=item['attempt'],artifact_id=image['id'],source_sha256=image['sha256'],subject_en=subject,
                original_prompt=item['prompt'],use_gpu=False,timeout_seconds=900,priority=item.get('priority',0)))
            auto.update(status='queued',stage='Check concept layout before 3D');return None
        if not all(j['status']=='REVIEW_REQUIRED' for j in reports):auto.update(status='queued',stage='Check concept layout before 3D');return None
        result=receipt(reports[-1])
        if result['source_sha256']!=image['sha256'] or result['source_artifact_id']!=image['id']:raise ValueError('Concept layout bound to a different image')
        if result['suitable_single_asset_image']:allowed.append(image)
        else:rejected.append(result)
    rejected_ids={r['source_artifact_id'] for r in rejected}
    if rejected_ids:
        model=studio.asset(item['asset_id']);spec=model.setdefault('resolved_specification',{});spec['concept_layout_checks']=rejected;studio.save_asset(model)
    if allowed or not rejected:return allowed
    count=len([j for j in current if j['payload']['kind']=='concept'])
    limit=min(2,value['automation']['settings'].get('retry_limit',1))
    if count<=limit:
        prompt=item.get('prompt_interpretation',{}).get('generation_prompt_en',item['prompt'])
        prompt+='\nExactly ONE connected standalone asset, full silhouette visible, one three-quarter camera view. No concept sheet, inset panel, collage, alternate views, diagrams, borders or labels.'
        studio.concept(studio.ConceptInput(asset_id=item['asset_id'],request_id=f'{value["id"]}:{item["asset_id"]}:{item["attempt"]}:concept-layout-repair-{count}',
            prompt=item['prompt'],interpreted_prompt=prompt,style_reference_ids=item.get('style_reference_ids',[]),quality=item['quality'],seed=42+count,
            batch_id=value['id'],batch_attempt=item['attempt']))
        auto.update(status='queued',stage=f'Concept layout repair {count}/{limit}; quality preserved');return None
    auto.update(status='blocked',stage='Needs Attention / concept layout',error='Concept still unsuitable after bounded repair: '+', '.join(sorted({issue for r in rejected for issue in r['issues']}))+'. Try a different concept or seed; no 3D inference was started.')
    return None
