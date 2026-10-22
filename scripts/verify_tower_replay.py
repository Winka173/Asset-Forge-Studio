"""Real isolated tower replay through existing jobs, Blender and GLB export.

Uses the recovered exact historical sampling settings, not an invented quality
equivalence. External local AI install must already be present and authorized.
"""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'.local/tower-replay'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
RUN.mkdir(parents=True)
os.environ['AFS_DATA']=str(RUN/'Library')
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs
from apps.api.main import app
from apps.api.export_profiles import export_asset

client=TestClient(app)
project=client.post('/api/projects',json=dict(name='Tower quality replay',art_bible=json.loads((ROOT/'presets/runavelle.json').read_text('utf-8')))).json()
asset=studio.create_asset(studio.AssetInput(project_id=project['id'],name='Archer Tower / preserved source',prompt='Reconstruct the tower shown in the source image.'))
baseline=json.loads((ROOT/'docs/evidence/tower_quality_preservation.json').read_text('utf-8'))
source=Path(baseline['source']);assert store.digest(source)==baseline['source_sha256']
with source.open('rb') as stream:r=client.post('/api/import/reference',params=dict(project_id=project['id'],asset_id=asset['id']),files=dict(file=('ArcherTowerSource.png',stream,'image/png')))
assert r.status_code==201,r.text
ref=r.json();request=baseline['original_request'];started=time.monotonic()
submitted=studio.generate(studio.Generate(asset_id=asset['id'],artifact_id=ref['id'],request_id='golden-tower-profile-replay',engine='trellis2_community',quality='Maximum',steps=request['steps'],pipeline_type=request['pipeline_type'],texture_size=request['texture_size'],seeds=[request['seed']],auto_blender=True))
report=dict(status='RUNNING',run=str(RUN),baseline=baseline['raw_glb_sha256'],request=submitted,source_sha256=ref['sha256'],scope='Real replay, technical inventory and render evidence; human quality comparison pending')
try:
    while True:
        pending=[j for j in jobs.listing() if j['status']=='QUEUED']
        if not pending:break
        for job in reversed(pending):
            print('RUN_STAGE',job['payload']['kind'],job['id'],flush=True)
            jobs.worker.managed(job,jobs.resource_class(job['payload']))
            actual=jobs.get(job['id']);assert actual['status']=='REVIEW_REQUIRED',actual
    records=studio.studio(project['id'])['artifacts']
    final=next(a for a in records if a['metadata'].get('stage')=='blender_processed' and 'LOD0' in a['name'])
    delivery=export_asset(project['id'],asset['id'],artifact_id=final['id'],settings=dict(preset='glb_only',manifest=True))
    report.update(status='VERIFIED_REAL_REPLAY_GLB_EXPORT',seconds=time.monotonic()-started,jobs=jobs.listing(),delivery=delivery,artifact=final)
except Exception as exc:
    report.update(status='FAILED',error=str(exc));raise
finally:
    (RUN/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
