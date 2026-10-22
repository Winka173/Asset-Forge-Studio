"""Real local castle request, immutable tower style reference, no procedural fallback."""
import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'.local/castle-quality-route'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');RUN.mkdir(parents=True)
os.environ['AFS_DATA']=str(RUN/'Library');os.environ['AFS_INTENT_ENABLED']='1'
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs,batch,automation
from apps.api.main import app
client=TestClient(app)
project=client.post('/api/projects',json=dict(name='Runavelle castle detailed AI quality',art_bible=json.loads((ROOT/'presets/runavelle.json').read_text('utf-8')))).json()
original='tạo cho tôi 1 lâu đài, style giống hình ảnh ref này'
asset=studio.create_asset(studio.AssetInput(project_id=project['id'],name='Castle / detailed AI route',prompt=original))
with (ROOT/'.local/fixtures/ArcherTowerSource.png').open('rb') as stream:
    r=client.post('/api/import/reference',params=dict(project_id=project['id'],asset_id=asset['id']),files=dict(file=('ArcherTowerSource.png',stream,'image/png')))
assert r.status_code==201,r.text
reference=r.json();started=time.monotonic()
response=automation.single(automation.Single(asset_id=asset['id'],request_id='castle-neural-detail-route',quality='Maximum',reference_id=reference['id'],reference_usage='auto',seeds=[43]))
identifier=response['batch_id']
report=dict(status='RUNNING',run=str(RUN),batch_id=identifier,asset_id=asset['id'],original_prompt=original,reference_sha256=reference['sha256'],scope='One real high-detail neural route experiment, not an artistic/Meshy acceptance claim')
try:
    for tick in range(35):
        value=batch.batch(identifier);auto=value['items'][0].get('automation',{});report.update(automation=auto,jobs=jobs.listing(),seconds=time.monotonic()-started)
        (RUN/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
        if auto.get('status') in ('exported','failed','blocked'):break
        pending=[j for j in jobs.listing() if j['payload'].get('batch_id')==identifier and j['status']=='QUEUED']
        for job in reversed(pending):
            assert job['payload']['kind']!='procedural_geometry','Detailed route was downgraded to blockout'
            print('REAL_STAGE',job['payload']['kind'],job['id'],flush=True)
            jobs.worker.managed(job,jobs.resource_class(job['payload']))
        automation.advance(identifier)
    value=batch.batch(identifier);item=value['items'][0]
    report.update(status='TECHNICALLY_DELIVERED_ART_NOT_REVIEWED' if item['automation']['status']=='exported' else 'NEEDS_ATTENTION',item=item,jobs=jobs.listing(),seconds=time.monotonic()-started)
    assert studio.asset(asset['id'])['original_prompt']==original
finally:
    (RUN/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
