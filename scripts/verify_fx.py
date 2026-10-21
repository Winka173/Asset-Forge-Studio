"""Real Unity FX acceptance, never simulated successful renderer output."""
import json
import os
import time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
RUN=ROOT/'.local/fx-real'/stamp
RUN.mkdir(parents=True)
os.environ['AFS_DATA']=str(RUN/'Library')

from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store

report=dict(status='RUNNING',run=str(RUN),purpose='Actual native Unity GPU build and cold reopen. No AI, no character-animation or artistic acceptance claim.')
try:
    with TestClient(app) as client:
        project=client.post('/api/projects',json=dict(name='Runavelle FX real local QA')).json()
        element=os.environ.get('AFS_FX_ELEMENT','fire')
        recipe=dict(project_id=project['id'],name=element.title()+' sword slash / real Unity QA',prompt='Three-swing '+element+' slash; procedural weapon demonstration.',element=element)
        report['element']=element
        response=client.post('/api/fx/build',json=dict(recipe=recipe,request_id='fx-real-'+stamp))
        assert response.status_code==201,response.text
        value=response.json();report.update(project_id=project['id'],asset_id=value['asset_id'],job_id=value['job']['id'])
        for count in range(1800):
            job=next(j for j in client.get('/api/jobs').json() if j['id']==report['job_id'])
            if count%12==0:print(json.dumps(dict(job=job['id'],status=job['status'])),flush=True)
            if job['status'] in ['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED']:break
            time.sleep(1)
        assert job['status']=='REVIEW_REQUIRED',job.get('error')
        folder=store.DATA/'jobs'/job['id']
        native=json.loads((folder/'manifest.json').read_text())
        assert native['status']=='PASS_EDITOR_VALIDATION'
        report.update(status='PASS_REAL_UNITY_FX',native_report=native,job=job)
except Exception as exc:
    report.update(status='FAILED',error=str(exc))
    raise
finally:
    (RUN/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
