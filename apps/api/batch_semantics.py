"""Checkpointed semantic suggestions remain separate from immutable imported source and generation."""
import json
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import store,jobs,batch
from engines import local_semantics as adapter

router=APIRouter(prefix='/api/batch-analysis')


@router.get('/local-models')
def models():return adapter.probe()


class Analyze(BaseModel):
    model:str=Field(min_length=1,max_length=200)
    selected_ids:list[str]=Field(min_length=1,max_length=1000)


@router.post('/{identifier}',status_code=201)
def analyze(identifier:str,body:Analyze):
    value=batch.batch(identifier);probe=adapter.probe()
    model=next((m for m in probe['models'] if m['name']==body.model),None)
    if not model:raise HTTPException(503,probe['reason'] or 'Select an installed local model; no automatic download')
    if set(body.selected_ids)-{i['asset_id'] for i in value['items']}:raise HTTPException(400,'Unknown batch asset IDs')
    if not value.get('source_file'):raise HTTPException(409,'Reimport with source retention before semantic analysis')
    return jobs.enqueue(dict(kind='batch_semantics',import_batch_id=identifier,project_id=value['project_id'],model=body.model,
        model_digest=model.get('digest'),selected_ids=list(dict.fromkeys(body.selected_ids)),use_gpu=False,timeout_seconds=7200))


def execute(job,folder):
    payload=job['payload'];identifier=payload['import_batch_id'];value=batch.batch(identifier)
    current=next((m for m in adapter.probe()['models'] if m['name']==payload['model']),None)
    if not current or current.get('digest')!=payload.get('model_digest'):raise ValueError('Local model unavailable or changed; submit a new analysis')
    source=value['source_file'];file=store.safe_path(source['relative_path']).parent/'decoded.txt'
    if store.digest(file)!=source['text_sha256']:raise ValueError('Original source checksum changed')
    original=file.read_bytes().decode('utf-8');known={i['source_asset_id'] or i['asset_id'] for i in value['items']}
    failures=[]
    for item in value['items']:
        if item['asset_id'] not in payload['selected_ids']:continue
        if jobs.get(job['id'])['status']=='CANCELLED':return
        start,end=item.get('source_char_start'),item.get('source_char_end')
        text=original[start:end] if start is not None and end is not None else item['prompt']
        if adapter.fingerprint(text)!=item['source_sha256']:raise ValueError('Original prompt hash changed')
        source_id=item['source_asset_id'] or item['asset_id']
        prior=item.get('semantic_metadata',{})
        records=list(prior.get('chunks',[])) if prior.get('source_sha256')==item['source_sha256'] and prior.get('model_digest')==payload.get('model_digest') and prior.get('model')==payload['model'] else []
        metadata=dict(status='Needs Review',source_sha256=item['source_sha256'],model=payload['model'],model_digest=payload.get('model_digest'),chunks=records,applied_to_generation=False)
        try:
            for offset,stop,chunk in adapter.chunks(text):
                if jobs.get(job['id'])['status']=='CANCELLED':return
                digest=adapter.fingerprint(chunk)
                if not any(c['sha256']==digest and c['start']==offset for c in records):
                    suggestions=adapter.analyze_chunk(chunk,source_id,payload['model'],known)
                    records.append(dict(start=offset,end=stop,sha256=digest,suggestions=suggestions))
                with batch.LOCK:
                    latest=batch.batch(identifier);target=next(i for i in latest['items'] if i['asset_id']==item['asset_id']);target['semantic_metadata']=metadata;batch.save(latest)
            metadata['status']='Needs Review'
        except Exception as exc:
            metadata['status']='Failed';metadata['error']=type(exc).__name__+': semantic extraction failed validation or local runtime. See job report.';failures.append(item['asset_id'])
        with batch.LOCK:
            latest=batch.batch(identifier);target=next(i for i in latest['items'] if i['asset_id']==item['asset_id']);target['semantic_metadata']=metadata
            latest['import_diagnostics']['local_ai_used']=bool(records) or latest['import_diagnostics'].get('local_ai_used',False);batch.save(latest)
    (folder/'semantic_report.json').write_text(json.dumps(dict(selected=len(payload['selected_ids']),failed_asset_ids=failures,model=payload['model'],metadata_only=True),indent=2),encoding='utf-8')
    jobs.transition(job['id'],'FAILED' if failures else 'REVIEW_REQUIRED','Some asset metadata failed; validated checkpoints retained' if failures else None)
