"""Actual TRELLIS inference, then a real server-stop at its saved finishing boundary."""
import json,os,sys,time,threading
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'.local/native-checkpoint-real'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');RUN.mkdir(parents=True)
os.environ['AFS_DATA']=str(RUN/'Library');sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from apps.api import store,studio,jobs,native_checkpoint
from apps.api.main import app
client=TestClient(app)
project=client.post('/api/projects',json=dict(name='Native checkpoint recovery QA',art_bible=json.loads((ROOT/'presets/runavelle.json').read_text('utf-8')))).json()
asset=studio.create_asset(studio.AssetInput(project_id=project['id'],name='Archer Tower / checkpoint recovery',prompt='Reconstruct the supplied tower. Preserve the original replay profile.'))
source=ROOT/'.local/fixtures/ArcherTowerSource.png'
with source.open('rb') as stream:response=client.post('/api/import/reference',params=dict(project_id=project['id'],asset_id=asset['id']),files=dict(file=(source.name,stream,'image/png')))
assert response.status_code==201,response.text
reference=response.json();started=time.monotonic()
submitted=studio.generate(studio.Generate(asset_id=asset['id'],artifact_id=reference['id'],request_id='real-native-checkpoint-interruption',quality='Maximum',engine='trellis2_community',steps=24,pipeline_type='1024_cascade',texture_size=4096,seeds=[43],auto_blender=True))
job=submitted['jobs'][0];folder=store.DATA/'jobs'/job['id']
report=dict(status='RUNNING_REAL_INFERENCE',run=str(RUN),job_id=job['id'],asset_id=asset['id'],project_id=project['id'],source_sha256=reference['sha256'],scope='Historical tower profile replay (24 steps explicitly), not a reduction of the current 32-step Maximum default. Real server-stop at decoded geometry/PBR boundary; no simulated model success.')
(RUN/'report.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(dict(run=str(RUN),job_id=job['id'])),flush=True)
def run_when_slot_available():
    while jobs.get(job['id'])['status']=='QUEUED' and not jobs.worker.stop.is_set():
        jobs.worker.managed(job,'gpu')
        if jobs.get(job['id'])['status']=='QUEUED':
            print('WAITING_FOR_SHARED_GPU_SLOT',flush=True);time.sleep(3)
thread=threading.Thread(target=run_when_slot_available);thread.start()
try:
    stopped=False
    while thread.is_alive():
        try:
            value=json.loads((folder/'output/generation.json').read_text('utf-8'))
            if value.get('native_checkpoint'):
                jobs.worker.stop.set();stopped=True;print('REAL_SERVER_STOP_AFTER_NATIVE_CHECKPOINT',flush=True);break
        except (OSError,ValueError):pass
        time.sleep(.1)
    thread.join();actual=jobs.get(job['id'])
    assert stopped and actual['status']=='BLOCKED',actual
    checkpoint=native_checkpoint.checkpoint_for(actual)
    assert not (folder/'output/raw.glb').exists(),'Stop missed the finishing boundary'
    report.update(status='VERIFIED_REAL_INTERRUPTED_NATIVE_CHECKPOINT',seconds=time.monotonic()-started,job=actual,checkpoint={k:str(v) if isinstance(v,Path) else v for k,v in checkpoint.items()})
finally:
    jobs.worker.stop.set();thread.join();report['seconds']=time.monotonic()-started
    if report['status']=='RUNNING_REAL_INFERENCE':report.update(status='FAILED_OR_NOT_RUN',job=jobs.get(job['id']))
    (RUN/'report.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
