"""Measure actual retained tower LOD geometry, no AI inference or user Library writes."""
import json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'.local/lod-quality-real'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');RUN.mkdir(parents=True)
os.environ['AFS_DATA']=str(RUN/'Library');sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs
from apps.api.main import app
client=TestClient(app)
previous=json.loads((ROOT/'docs/evidence/native_checkpoint_desktop_v094.json').read_text('utf-8'))
delivery=previous['checks'][0]['delivery'];file=next(f for f in delivery['files'] if f['name'].endswith('.glb'));source=Path(delivery['export_directory'])/file['name'];assert store.digest(source)==file['sha256']
project=client.post('/api/projects',json=dict(name='Tower LOD geometry retention QA')).json()
asset=studio.create_asset(studio.AssetInput(project_id=project['id'],name='Archer Tower / measured LOD quality',prompt='Retained real tower; measured LOD geometry only, not new AI inference.'))
copy=store.DATA/'imports/retained-tower.glb';copy.parent.mkdir(parents=True,exist_ok=True)
import shutil
shutil.copyfile(source,copy)
from apps.api.inspection import inspect_glb
record=store.add_artifact(copy,'candidate','Actual retained tower',inspect_glb(copy)|dict(project_id=project['id'],asset_id=asset['id'],license='EVALUATION_ONLY_PENDING_AUDIT',source_sha256=file['sha256']))
response=client.post('/api/jobs/blender',json=dict(artifact_id=record['id'],render=False));assert response.status_code==201,response.text
job=response.json();started=time.monotonic();jobs.worker.managed(job,'cpu');actual=jobs.get(job['id']);assert actual['status']=='REVIEW_REQUIRED',actual
output=store.DATA/'jobs'/job['id']/'output';processing=json.loads((output/'report.json').read_text('utf-8'));candidate=next(a for a in studio.studio(project['id'])['artifacts'] if a['metadata'].get('job_id')==job['id'] and a['role']=='candidate')
assert len(candidate['metadata']['lod_surface_quality'])==3
assert all(row['surface_error']['samples_per_direction']==8192 for row in processing['lods'])
assert store.digest(source)==file['sha256']
report=dict(status='VERIFIED_REAL_TOWER_LOD_SURFACE_MEASUREMENTS',run=str(RUN),project_id=project['id'],asset_id=asset['id'],job_id=job['id'],seconds=time.monotonic()-started,artifact=candidate,lods=processing['lods'],source_sha256=file['sha256'],source_preserved=True,scope='Real previously generated tower, unchanged master and real LOD export/reopen. Sampled geometry measurements, not global Hausdorff, visual/artistic or target-game approval.')
(RUN/'report.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
