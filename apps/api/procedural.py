"""Validated data-only Blender assembly jobs in the shared queue, not a new pipeline."""
import hashlib
import json
import subprocess
from . import store,jobs,studio
from .inspection import inspect_glb
from engines.quality import fingerprint,resolve_procedural


def submit(value,item,spec):
    for seed in item.get('seeds') or range(42,42+item['candidates']):
        key='assembly:'+hashlib.sha256(f'{value["id"]}:{item["asset_id"]}:{item["attempt"]}:{seed}'.encode()).hexdigest()
        config=resolve_procedural(spec,seed,item['candidates'])
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');previous=studio.cached(db,key,fingerprint(config))
            if previous:continue
            from .engine_health import admit
            admit(dict(kind='procedural_geometry',effective_config=config))
            admit(dict(kind='blender',effective_config=config))
            result=jobs.enqueue(dict(kind='procedural_geometry',engine='blender_procedural',project_id=value['project_id'],asset_id=item['asset_id'],batch_id=value['id'],batch_attempt=item['attempt'],
                spec=spec,spec_sha256=fingerprint(spec),seed=seed,auto_blender=True,effective_config=config,effective_config_hash=fingerprint(config),
                use_gpu=False,timeout_seconds=900,priority=item.get('priority',0)),db=db)
            db.execute('INSERT INTO studio_requests VALUES (?,?,?)',(key,fingerprint(config),json.dumps(result)))


def execute(job,folder,worker):
    from .local_tools import executable
    p=job['payload'];config=p['effective_config'];blender=executable('blender')
    if not blender:raise ValueError('Blender executable not found')
    script=store.ROOT/'pipelines/blender/assemble_castle.py'
    if fingerprint(config)!=p['effective_config_hash'] or fingerprint(p['spec'])!=p['spec_sha256'] or store.digest(script)!=config['checkpoint']['script_sha256']:raise ValueError('Assembly config/script checksum changed')
    request=dict(spec=p['spec'],spec_sha256=p['spec_sha256'],seed=p['seed'],texture_size=config['texture']['size'],output=str(folder/'output'))
    request_path=folder/'request.json';request_path.write_text(json.dumps(request,indent=2),encoding='utf-8')
    jobs.transition(job['id'],'POSTPROCESSING');process=None
    try:
        with (folder/'worker.log').open('w',encoding='utf-8') as log:
            log.write('STAGE Blender / named castle structure and authored PBR\n');log.flush()
            process=subprocess.Popen([blender,'-b','-t','8','--factory-startup','--python-exit-code','1','--python',str(script),'--','--request',str(request_path)],stdout=log,stderr=subprocess.STDOUT)
            (folder/'process.json').write_text(json.dumps(dict(pid=process.pid,kind='procedural_geometry')))
            while process.poll() is None:
                if worker.stop.is_set() or jobs.get(job['id'])['status']=='CANCELLED':
                    jobs.kill_tree(process)
                    if jobs.get(job['id'])['status']!='CANCELLED':jobs.transition(job['id'],'BLOCKED','Server stopped; raw stage retained if complete, no mid-stage resume claimed')
                    return
                worker.stop.wait(.2)
        if process.returncode:raise RuntimeError('Procedural Blender exit '+str(process.returncode)+'; inspect worker.log')
        jobs.transition(job['id'],'VALIDATING')
        report=json.loads((folder/'output/assembly.json').read_text(encoding='utf-8'));glb=folder/'output/raw.glb';qa=inspect_glb(glb)
        if report['spec_sha256']!=p['spec_sha256'] or report['output_sha256']!=store.digest(glb) or report['export_reopen']!='PASS' or not all(report['checks'].values()):raise ValueError('Assembly structural/export validation failed')
        source=store.add_artifact(glb,'candidate','Authored castle / raw geometry',qa|dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],engine='blender_procedural',stage='raw_geometry',
            spec_sha256=p['spec_sha256'],assembly_report=str((folder/'output/assembly.json').relative_to(store.DATA)),license='AFS authored procedural profile; user references retained separately',artistic_approval=False))
        store.add_artifact(folder/'output/assembly.json','structural_report','Castle assembly measurements',dict(project_id=p['project_id'],asset_id=p['asset_id'],job_id=job['id'],parent_id=source['id']))
        (folder/'manifest.json').write_text(json.dumps(dict(candidate_artifact=source['id'],source_sha256=source['sha256'],assembly_report_sha256=store.digest(folder/'output/assembly.json'))),encoding='utf-8')
        jobs.transition(job['id'],'REVIEW_REQUIRED');jobs.ensure_blender(jobs.get(job['id']))
    finally:
        if process and process.poll() is None:jobs.kill_tree(process)
