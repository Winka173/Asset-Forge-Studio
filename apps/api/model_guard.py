"""Hash-bound advisory render observations in the shared job graph."""
import json
from . import store,studio,jobs


def execute(job,folder):
    from engines.model_guard import assess
    p=job['payload'];candidate=studio.scoped_artifact(p['artifact_id'],p['project_id'],p['asset_id'])
    if candidate['sha256']!=p['source_sha256'] or store.digest(store.safe_path(candidate['relative_path']))!=p['source_sha256']:raise ValueError('Model review source changed')
    paths=[]
    for view in p['renders']:
        path=store.safe_path(view['relative_path'])
        if store.digest(path)!=view['sha256']:raise ValueError('Model review render changed')
        paths.append(path)
    if len(paths)!=3:raise ValueError('Model review requires three actual Blender views')
    reference=p.get('visual_reference')
    if reference:
        source=studio.scoped_artifact(reference['artifact_id'],p['project_id']);path=store.safe_path(source['relative_path'])
        if source['sha256']!=reference['sha256'] or store.digest(path)!=reference['sha256']:raise ValueError('Visual comparison source changed')
        paths.append(path)
    with (folder/'worker.log').open('a',encoding='utf-8') as log:
        def progress(message):log.write('STAGE '+message+'\n');log.flush()
        try:result=assess(paths,p['subject_en'],p['original_prompt'],progress,p.get('project_context'))
        except (OSError,ValueError,TimeoutError) as exc:
            result=dict(schema_version=1,screening_policy=p['screening_policy'],decision='flag',evaluation_status='NOT_EVALUATED',observations=[],
                limitations=['Local visual evaluation unavailable or invalid: '+str(exc)[:500]],artistic_approval=False,execution='not_evaluated')
    if jobs.get(job['id'])['status']=='CANCELLED':return
    result.update(source_artifact_id=candidate['id'],source_sha256=candidate['sha256'],renders=p['renders'])
    target=folder/'model_visual_check.json';part=target.with_suffix('.part')
    part.write_text(json.dumps(result,indent=2),encoding='utf-8');part.replace(target)
    record=store.add_artifact(target,'model_visual_report','Local model render observations',dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],
        parent_id=candidate['id'],source_sha256=candidate['sha256'],model=result.get('model'),artistic_approval=False))
    (folder/'manifest.json').write_text(json.dumps(dict(model_visual_artifact=record['id'],sha256=record['sha256'])),encoding='utf-8')
    jobs.transition(job['id'],'GENERATED');jobs.transition(job['id'],'VALIDATING');jobs.transition(job['id'],'REVIEW_REQUIRED')


def receipt(job):
    manifest=json.loads((store.DATA/'jobs'/job['id']/'manifest.json').read_text(encoding='utf-8'))
    record=studio.scoped_artifact(manifest['model_visual_artifact'],job['payload']['project_id'],job['payload']['asset_id'])
    path=store.safe_path(record['relative_path'])
    if record['sha256']!=manifest['sha256'] or store.digest(path)!=record['sha256']:raise ValueError('Model visual receipt changed')
    return json.loads(path.read_text(encoding='utf-8'))


def filter_candidates(value,item,current,candidates,auto):
    if not item.get('interpret_prompt') or item.get('processing_source') or item.get('revision_id'):return candidates
    from engines.model_guard import POLICY_VERSION
    accepted=[];reports=[]
    for candidate in candidates:
        renders=[]
        for view in ('three_quarter','back','side'):
            path=store.DATA/'jobs'/candidate['metadata']['job_id']/'output'/f'mobile_{view}_asset.png'
            if not path.is_file():raise ValueError('Actual Blender views missing; cannot perform local render review')
            renders.append(dict(view=view,relative_path=path.relative_to(store.DATA).as_posix(),sha256=store.digest(path)))
        from .quality_evaluation import evaluator_key
        source_id=auto.get('concept_selection',{}).get('artifact_id') or next(iter(item.get('style_reference_ids',[])),None)
        visual_reference=studio.scoped_artifact(source_id,value['project_id']) if source_id else None
        project=value['style_snapshot'];bible=project.get('art_bible') or {}
        context=dict(default_style=project.get('default_style'),materials=project.get('material_language'),palette=project.get('palette'),art_bible={k:bible.get(k) for k in ('materials','palette','constraints')})
        refs=dict(original_references=item.get('asset_generation_spec',{}).get('reference_hashes',[]),project_context=context,visual_reference=visual_reference['sha256'] if visual_reference else None)
        key=evaluator_key(candidate,item['prompt'],refs,'model_guard.py',renders)
        checks=[j for j in current if j['payload']['kind']=='model_visual_check' and j['payload']['artifact_id']==candidate['id'] and j['payload'].get('evaluation_key')==key]
        if not checks:
            subject=(item.get('prompt_interpretation',{}).get('chunks') or [{}])[0].get('interpretation',{}).get('requested_subject_en','game asset')
            jobs.enqueue(dict(kind='model_visual_check',engine='qwen3_vl_local_cpu',project_id=value['project_id'],asset_id=item['asset_id'],batch_id=value['id'],batch_attempt=item['attempt'],
                artifact_id=candidate['id'],source_sha256=candidate['sha256'],renders=renders,subject_en=subject,original_prompt=item['prompt'],screening_policy=POLICY_VERSION,
                use_gpu=False,timeout_seconds=900,priority=item.get('priority',0),evaluation_key=key,project_context=context,
                visual_reference=dict(artifact_id=visual_reference['id'],sha256=visual_reference['sha256']) if visual_reference else None))
            auto.update(status='queued',stage='Check processed 3D renders / local AI');return None
        if not all(j['status']=='REVIEW_REQUIRED' for j in checks):auto.update(status='queued',stage='Check processed 3D renders / local AI');return None
        result=receipt(checks[-1])
        if result['source_artifact_id']!=candidate['id'] or result['source_sha256']!=candidate['sha256']:raise ValueError('Visual review bound to different model')
        reports.append(result)
        # Uncalibrated visual judgments remain evidence flags. Technical and
        # deterministic structural gates, not a subjective score, control export.
        accepted.append(candidate)
    studio.patch_resolved_specification(item['asset_id'],dict(model_visual_checks=reports))
    auto['visual_checks']=reports
    return accepted
