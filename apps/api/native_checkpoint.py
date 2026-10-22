"""Resume only verified native mesh/PBR finishing in the existing GPU queue."""
import json
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import jobs,store,studio
from engines import mesh_checkpoint
from engines.quality import fingerprint

router=APIRouter(prefix='/api/production/jobs')


def checkpoint_for(job):
    payload=job['payload']
    if payload.get('kind')!='inference' or payload.get('engine')!='trellis2_community':raise ValueError('This engine has no verified native finishing checkpoint')
    if not payload.get('effective_config') or fingerprint(payload['effective_config'])!=payload.get('effective_config_hash'):raise ValueError('Native checkpoint locked config hash mismatch')
    source=jobs.get(payload['resume_mesh_checkpoint']) if payload.get('resume_mesh_checkpoint') else job
    original=source['payload']
    if any(payload.get(k)!=original.get(k) for k in ('project_id','asset_id','artifact_id','engine','effective_config_hash','seed','steps','pipeline_type','texture_size')):raise ValueError('Native checkpoint scope/config mismatch')
    source_record=studio.scoped_artifact(payload['artifact_id'],payload['project_id'],payload['asset_id'])
    if store.digest(store.safe_path(source_record['relative_path']))!=source_record['sha256']:raise ValueError('Native checkpoint input checksum changed')
    folder=store.DATA/'jobs'/source['id']/'output';receipt=folder/'mesh_checkpoint.json'
    generation=json.loads((folder/'generation.json').read_text('utf-8'))
    binding=generation.get('native_checkpoint')
    if not binding or not payload.get('effective_config_hash'):raise ValueError('No committed native checkpoint boundary; older unbound masters are preserved but cannot auto-resume')
    if payload.get('resume_checkpoint_sha256') and payload['resume_checkpoint_sha256']!=binding['sha256']:raise ValueError('Pinned native checkpoint checksum changed')
    expected=payload|dict(export_triangle_target=payload['effective_config']['geometry']['export_triangle_target'])
    metadata=mesh_checkpoint.verify(receipt,expected,source_record['sha256'],generation['model_revision'],binding['sha256'])
    if metadata['native_sha256']!=binding['native_sha256']:raise ValueError('Native master binding changed')
    return dict(path=receipt,sha256=binding['sha256'],source_job_id=source['id'],metadata=metadata)


@router.get('/{identifier}/native-checkpoint')
def inspect_checkpoint(identifier:str):
    try:
        value=checkpoint_for(jobs.get(identifier))
        return dict(available=True,source_job_id=value['source_job_id'],sha256=value['sha256'],geometry=value['metadata']['geometry'],resume_scope=value['metadata']['resume_scope'])
    except (ValueError,KeyError,OSError) as exc:return dict(available=False,reason=str(exc))


class Resume(BaseModel):
    request_id:str=Field(min_length=8,max_length=100)


@router.post('/{identifier}/resume-finishing',status_code=201)
def resume_finishing(identifier:str,body:Resume):
    original=jobs.get(identifier)
    if original['status'] not in ('FAILED','BLOCKED'):raise HTTPException(409,'Only an interrupted or failed stage can resume finishing. Existing completed versions remain unchanged.')
    try:checkpoint=checkpoint_for(original)
    except (ValueError,KeyError,OSError) as exc:raise HTTPException(409,str(exc))
    payload=original['payload']|dict(retry_of=identifier,resume_mesh_checkpoint=checkpoint['source_job_id'],resume_checkpoint_sha256=checkpoint['sha256'])
    key='finish:'+identifier+':'+body.request_id;digest=fingerprint(dict(payload=payload))
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');cached=studio.cached(db,key,digest)
        if cached:return cached
        for row in db.execute('SELECT * FROM jobs'):
            existing=jobs.decode(row)
            if existing['payload'].get('resume_mesh_checkpoint')==checkpoint['source_job_id']:
                if existing['status'] not in jobs.TERMINAL:
                    db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,digest,json.dumps(existing)))
                    return existing
                if existing['status']=='REVIEW_REQUIRED':raise HTTPException(409,'Finishing already completed. Use a versioned revision to change a delivered model.')
        result=jobs.enqueue(payload,db=db)
        db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,digest,json.dumps(result)))
    return result
