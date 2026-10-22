"""Real local image+text -> Qwen -> SDXL -> Qwen -> 3D -> Blender -> Qwen -> GLB.

Explicit acceptance runner, never a unit test. Creates an isolated Library and
uses installed offline engines; no mock responses or writes to the user's data.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--case',choices=['castle','shape'],default='castle');args=parser.parse_args()
run=Path(args.run).resolve();run.mkdir(parents=True,exist_ok=True)
os.environ['AFS_DATA']=str(run/'Library');os.environ['AFS_INTENT_ENABLED']='1'
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store,studio,jobs,batch,automation
from apps.api.inspection import inspect_glb

client=TestClient(app);started=time.monotonic()
prompt='tạo cho tôi 1 lâu đài, style giống hình ảnh ref này' if args.case=='castle' else 'Reconstruct the supplied masked castle. Geometry-only evaluation; no texture equivalence claim.'
report=dict(status='RUNNING',run=str(run),prompt=prompt,original_prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),artistic_approval=False)

def request(url,**kwargs):
    response=client.post(url,**kwargs)
    response.raise_for_status();return response.json()

try:
    project=request('/api/projects',json=dict(name='Isolated castle quality acceptance'))
    asset=request('/api/assets',json=dict(project_id=project['id'],name='Castle text + tower style',prompt=prompt))
    source=root/('.local/fixtures/ArcherTowerSource.png' if args.case=='castle' else '.local/castle-reference-acceptance/Library/jobs/2b925f3bef044ceea8eb57fe999e147b/output/source_alpha.png')
    image=request('/api/import/reference',params=dict(project_id=project['id'],asset_id=asset['id']),files=dict(file=('ArcherTowerSource.png',source.read_bytes(),'image/png')))
    result=request('/api/automation/single',json=dict(asset_id=asset['id'],request_id='castle-quality-acceptance',reference_id=image['id'],reference_usage='auto' if args.case=='castle' else 'source',quality='Maximum',seeds=[42],
        **(dict(engine='triposg',workflow=dict(prompt_interpretation=False)) if args.case=='shape' else {})))
    identifier=result['batch_id'];report.update(project_id=project['id'],asset_id=asset['id'],batch_id=identifier,reference_sha256=image['sha256'])
    (run/'started.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    while time.monotonic()-started<2700:
        value=batch.batch(identifier);state=value['items'][0]['automation']
        print(json.dumps(dict(seconds=round(time.monotonic()-started,1),status=state['status'],stage=state.get('stage'),error=state.get('error'))),flush=True)
        if state['status'] in ('exported','failed','blocked'):break
        queued=[j for j in jobs.listing() if j['payload'].get('batch_id')==identifier and j['status']=='QUEUED']
        if queued:
            job=queued[-1];jobs.worker.managed(job,jobs.resource_class(job['payload']))
        else:time.sleep(2)
        automation.advance(identifier)
    state=batch.batch(identifier)['items'][0]['automation']
    report.update(status=state['status'],duration_seconds=time.monotonic()-started,automation=state,
        jobs=[dict(id=j['id'],kind=j['payload']['kind'],engine=j['payload'].get('engine'),status=j['status'],error=j.get('error'),effective_config_hash=j['payload'].get('effective_config_hash')) for j in jobs.listing()])
    assert studio.asset(asset['id'])['original_prompt']==prompt
    assert state['status']=='exported',state
    exported=state['export'];glb=Path(exported['export_directory'])/exported['filename'];qa=inspect_glb(glb)
    entry=next(f for f in exported['files'] if f['name']==glb.name)
    assert store.digest(glb)==entry['sha256']
    report.update(status='PASS_REAL_MAXIMUM_TEXT_IMAGE_TO_GLB',glb=str(glb),glb_sha256=entry['sha256'],qa=qa)
    if args.case=='castle':assert any(j['kind']=='model_visual_check' and j['status']=='REVIEW_REQUIRED' for j in report['jobs'])
    print(report['status'],flush=True)
finally:
    (run/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
