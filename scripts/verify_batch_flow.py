"""Observe existing REAL batch jobs, verify outputs; never generate or approve artwork."""
import argparse
import io
import json
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8766')
    parser.add_argument('--batch',required=True)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--timeout',type=int,default=1200)
    args=parser.parse_args();started=time.monotonic();observations=[]
    route=args.base+'/api/batches/'+args.batch
    def read(url):return json.load(urllib.request.urlopen(url,timeout=120))
    while True:
        batch=read(route);items=[i for i in batch['items'] if i['selected']]
        observations.append(dict(at=datetime.now().astimezone().isoformat(),items=[dict(name=i['name'],status=i['status'],jobs=[dict(id=j['id'],kind=j['payload']['kind'],status=j['status']) for j in i['jobs']]) for i in items]))
        if all(i['versions'] and i['jobs'] and all(j['status'] in ['REVIEW_REQUIRED','FAILED','BLOCKED','CANCELLED'] for j in i['jobs']) for i in items):break
        if time.monotonic()-started>args.timeout:raise TimeoutError('Real batch still incomplete; no success reported')
        time.sleep(10)
    assert len(batch['items'])==14 and len(items)>=2
    resources=[];outputs=[]
    for item in items:
        assert all(j['status']=='REVIEW_REQUIRED' for j in item['jobs']),item['name']
        for job in item['jobs']:
            folder=args.data/'jobs'/job['id']
            resource=folder/'resources.json'
            if resource.exists():resources.append(dict(id=job['id'],kind=job['payload']['kind'],**json.loads(resource.read_text())))
            if job['payload']['kind']=='blender':
                report=json.loads((folder/'output/report.json').read_text())
                assert report['checks']['export_reopen']=='PASS'
                files=[p for p in (folder/'output').rglob('*') if p.is_file()]
                assert any(p.suffix=='.glb' for p in files) and any(p.suffix=='.fbx' for p in files)
                outputs.append(dict(asset_id=item['asset_id'],job_id=job['id'],report=report,files=[dict(name=p.relative_to(folder/'output').as_posix(),bytes=p.stat().st_size) for p in files]))
    assert len(outputs)>=2
    def overlaps(a,b):return a['started_at']<b['finished_at'] and b['started_at']<a['finished_at']
    gpu=[r for r in resources if r['resource']=='gpu' and r['kind']=='inference']
    assert len(gpu)>=2 and not any(overlaps(a,b) for n,a in enumerate(gpu) for b in gpu[n+1:]),'Heavy GPU overlap detected'
    cpu=[r for r in resources if r['resource']=='cpu']
    overlap=[dict(cpu=a['id'],gpu=b['id']) for a in cpu for b in gpu if overlaps(a,b)]
    archive=zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(route+'/export?selection=selected&format=zip',timeout=180).read()))
    exported=json.loads(archive.read('export_report.json'))
    assert len(exported['included_assets'])>=2 and not exported['omitted_assets']
    result=dict(status='PASS_REAL_PIPELINE',batch_id=args.batch,manifest_count=len(batch['items']),selected_count=len(items),
                cpu_gpu_overlap=overlap,heavy_gpu_concurrency_max=1,resources=resources,outputs=outputs,observations=observations,
                export_report=exported,zip_files=archive.namelist(),production_art_approval='NOT_GIVEN',meshy_parity='NOT_TESTED',
                concept_rejections='Archer SDXL turnaround sheet and house-shaped result retained; supplied Archer reference used instead')
    target=Path('docs/evidence/batch_real_flow.json');target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],report=str(target),overlap_pairs=overlap)))


if __name__=='__main__':main()
