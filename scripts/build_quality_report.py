"""Assemble measured local run evidence; never invent human scores or Meshy comparisons."""
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from apps.api import store


def main():
    evidence = store.ROOT / 'docs/evidence'; evidence.mkdir(parents=True,exist_ok=True)
    paths = list(store.DATA.glob('generation/*/*/output/generation.json')) + list(store.DATA.glob('jobs/*/output/generation.json'))
    runs = []
    for path in sorted(paths):
        data = json.loads(path.read_text(encoding='utf-8'))
        folder = path.parent.parent
        sample_path = folder/'gpu_samples.json'
        samples = json.loads(sample_path.read_text()) if sample_path.exists() else []
        memory, watts = [], []
        for sample in samples:
            values = sample.get('all_gpu_memory_mib_and_power_w','').split(',')
            try: memory.append(float(values[0])); watts.append((float(sample['seconds']),float(values[1])))
            except (ValueError,IndexError): pass
        # Entire GPU incl desktop; excludes CPU/system power. No tariff has been assumed.
        energy = sum((watts[i][0]-watts[i-1][0])*(watts[i][1]+watts[i-1][1])/2 for i in range(1,len(watts)))/3_600_000
        engine = data.get('engine') or 'trellis2_community'
        old_torch = engine == 'trellis2_community' and not data.get('peak_scope')
        runs.append({'run':folder.relative_to(store.DATA).as_posix(),'engine':engine,'seed':data.get('request',{}).get('seed'),
            'status':data['status'],'error':data.get('error'),'duration_seconds':data.get('duration_seconds'),
            'native_triangles':data.get('raw_triangles',data.get('triangles')),
            'torch_memory_bytes':data.get('peak_allocated_bytes'),'torch_memory_scope':'end-phase lower bound (upstream resets)' if old_torch else data.get('peak_scope','whole worker Torch allocated'),
            'sampled_whole_gpu_peak_mib':max(memory) if memory else None,'gpu_energy_kwh_proxy':energy,
            'energy_scope':'whole GPU sampled, excludes CPU/system; no monetary tariff assumed',
            'input_sha256':data.get('input_sha256',data.get('source_sha256')),
            'output_sha256':data.get('output_sha256'),'model_revision':data.get('model_revision'),
            'provenance_file':str(path.relative_to(store.ROOT)),'mesh_quality_parity':'NOT_TESTED','human_score':None})
    with store.connect() as db:
        jobs = [dict(r)|{'payload':json.loads(r['payload'])} for r in db.execute('SELECT * FROM jobs ORDER BY created_at')]
    summary = {'runs':runs,'jobs':jobs,'meshy_golden_glb':'NOT_AVAILABLE_USER_CONFIRMED_IMAGE_ONLY',
        'unity':'NOT_TESTED','production_approval':'NEEDS_REVIEW','all_model_outputs_retained':True}
    (evidence/'all_runs.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    tiles = [
        ('Concept / image-only reference',store.ROOT/'doc/852446485_1648007553499526_667194451249758572_n.png'),
        ('TRELLIS.2 1024 / 4K / seed 42',store.DATA/'jobs/3d917d68e585402aaa981d9918d63008/output/mobile_three_quarter.png'),
        ('TRELLIS.2 1024 / 4K / seed 43',store.DATA/'jobs/ffab269f281a4ee18d7e9e0231c435d3/output/mobile_three_quarter.png'),
        ('TRELLIS seed 43 / neutral clay geometry',store.DATA/'diagnostics/clay_v1/trellis43/mobile_three_quarter.png'),
        ('TripoSG seed 42 / neutral clay geometry',store.DATA/'diagnostics/clay_v1/triposg42/mobile_three_quarter.png'),
        ('TripoSG seed 43 / neutral clay geometry',store.DATA/'diagnostics/clay_v1/triposg43/mobile_three_quarter.png')]
    sheet = Image.new('RGB',(1920,1000),'#111923'); draw=ImageDraw.Draw(sheet)
    try:
        font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',22); title=ImageFont.truetype('C:/Windows/Fonts/segoeuib.ttf',30)
    except OSError: font=title=ImageFont.load_default()
    draw.text((22,15),'ACTUAL LOCAL ARCHER TOWER OUTPUTS',font=title,fill='#dfc4a2')
    draw.text((22,57),'No Meshy GLB / no Unity evidence / no parity claim. Local renders use locked camera and lighting.',font=font,fill='#a9b9cc')
    for i,(label,path) in enumerate(tiles):
        x=(i%3)*640; y=110+(i//3)*440
        draw.rectangle((x+8,y,x+632,y+425),fill='#202a36')
        draw.text((x+18,y+8),label,font=font,fill='#e2dfda')
        with Image.open(path) as image:
            display=ImageOps.contain(image.convert('RGB'),(624,370))
            sheet.paste(display,(x+8+(624-display.width)//2,y+48+(370-display.height)//2))
    sheet.save(evidence/'archer_tournament.png')
    shutil.copyfile(store.DATA/'masters/trellis1024_seed43_native_v1/report.json',evidence/'native_master.json')
    shutil.copyfile(store.DATA/'jobs/0cd41c06dfa040908ead8f880ff6593b/output/report.json',evidence/'textured_fbx_real.json')
    print(json.dumps({'generation_runs':len(runs),'job_count':len(jobs),'contact_sheet':str(evidence/'archer_tournament.png')}))


if __name__=='__main__': main()
