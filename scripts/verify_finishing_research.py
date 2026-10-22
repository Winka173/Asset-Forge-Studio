"""Explicit isolated native-finishing research, never a production/default profile change.

Use --source-job with a retained job beneath workspace/.local only.
The copied worker changes only remesh_project, keeps the bound native checkpoint,
model/config/texture/triangle target, and runs under existing host GPU/RAM locks.
No diffusion or installed-engine edits. A finished GLB is not a quality approval.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-job',required=True)
    parser.add_argument('--projection',type=float,choices=[0.,.5,1.],required=True);args=parser.parse_args()
    source=Path(args.source_job).resolve();allowed=(ROOT/'.local').resolve()
    if not source.is_relative_to(allowed):raise ValueError('Research accepts isolated retained workspace/.local jobs only')
    run=allowed/'finishing-research'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');run.mkdir(parents=True)
    os.environ['AFS_DATA']=str(allowed);sys.path.insert(0,str(ROOT))
    from apps.api import jobs,store,host_resources
    from apps.api.inspection import inspect_glb
    original=json.loads((source/'request.json').read_text('utf-8'));request=dict(original)
    checkpoint=source/'output/mesh_checkpoint.json';native=source/'output/raw_master.npz'
    hashes={str(p):store.digest(p) for p in (checkpoint,native,source/'request.json')}
    request.update(output=str(run/'output'),resume_mesh_checkpoint=str(checkpoint),resume_checkpoint_sha256=store.digest(checkpoint),
        research_finishing_delta=dict(remesh_project=dict(baseline=0,experiment=args.projection),quality_default_changed=False))
    worker=ROOT/'.local'/('finishing-research-worker-'+run.name+'.py')
    text=(ROOT/'engines/trellis2_worker.py').read_text('utf-8');assert text.count('remesh_project=0')==1
    worker.write_text(text.replace('remesh_project=0','remesh_project='+str(args.projection)),'utf-8')
    request_path=run/'request.json';request_path.write_text(json.dumps(request,indent=2),'utf-8')
    report=dict(status='RUNNING_RESEARCH_ONLY',run=str(run),source_hashes=hashes,worker_sha256=store.digest(worker),
        delta=request['research_finishing_delta'],scope='Explicit native-finishing experiment; no production capability, default change, source mutation, AI regeneration or artistic approval.')
    started=time.monotonic()
    try:
        payload=dict(kind='inference',engine='trellis2_community',resume_mesh_checkpoint=str(checkpoint),effective_config=request.get('effective_config'))
        claim=dict(id='finishing-research-'+run.name,payload=payload)
        with jobs.resource_slot('gpu'),host_resources.reserve(claim,'gpu') as admission,(run/'worker.log').open('w',encoding='utf-8') as log:
            report['admission']=admission
            if not admission['allowed']:raise RuntimeError(admission['reason'])
            result=subprocess.run([str(Path(request['engine_path'])/'venv/Scripts/python.exe'),'-B','-u',str(worker),'--request',str(request_path),'--allow-community-evaluation'],cwd=request['engine_path'],stdout=log,stderr=subprocess.STDOUT,timeout=1200)
        if result.returncode:raise RuntimeError('Actual finishing failed; see worker.log')
        generation=json.loads((run/'output/generation.json').read_text('utf-8'));assert generation['inference_reused']
        assert all(store.digest(Path(p))==h for p,h in hashes.items())
        report.update(status='FINISHED_RESEARCH_REQUIRES_COMPARISON',generation=generation,technical_inspection=inspect_glb(run/'output/raw.glb'),sources_preserved=True)
    except Exception as exc:report.update(status='FAILED_RESEARCH',error=str(exc));raise
    finally:
        report['seconds']=time.monotonic()-started;(run/'report.json').write_text(json.dumps(report,indent=2),'utf-8')
        print(json.dumps(dict(status=report['status'],run=str(run))),flush=True)


if __name__=='__main__':main()
