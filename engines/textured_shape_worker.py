"""Shape engine + MV-Adapter texturing as one inference job, so every engine delivers a textured GLB.

The shape worker (TripoSG, TRELLIS v1 or Hunyuan3D-2.1, each in its own environment) writes output/shape/;
MV-Adapter then textures that mesh from the same alpha concept into output/texture/. The textured mesh becomes
output/raw.glb (the usual candidate contract); the untextured shape stays as output/shape/raw.glb for provenance.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def run(command, cwd, log):
    with log.open('w', encoding='utf-8') as out:
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        for line in process.stdout:
            out.write(line); out.flush()
            if line.startswith('STAGE '): print(line.rstrip(), flush=True)  # progress for the job log
        if process.wait(): raise RuntimeError(f'{command[2] if len(command) > 2 else command[0]} exited {process.returncode}; see {log.name}')


def cut_out(source, output, u2net_home):
    """Shape engines need an alpha cut-out. Concepts from SDXL have none, so separate the subject offline with the
    local u2net model (the same kind of automatic cut-out TRELLIS.2 performs internally); real alpha is kept as is."""
    from PIL import Image
    image = Image.open(source)
    if image.mode == 'RGBA' and image.getchannel('A').getextrema()[0] < 255: return source
    import os
    if u2net_home: os.environ['U2NET_HOME'] = u2net_home
    from rembg import new_session, remove
    print('STAGE Cut out the subject (local u2net)', flush=True)
    target = output / 'input_alpha.png'; remove(image.convert('RGB'), session=new_session('u2net')).save(target)
    return target


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--request', required=True)
    req = json.loads(Path(parser.parse_args().request).read_text(encoding='utf-8-sig'))
    output = Path(req['output']).resolve()
    if output.exists(): raise ValueError('Require a new immutable output directory')
    output.mkdir(parents=True)
    image = cut_out(Path(req['image']), output, req.get('u2net_home'))
    shape_request = dict(req['shape_request'], output=str(output / 'shape'), image=str(image), seed=req['seed'])
    (output / 'shape_request.json').write_text(json.dumps(shape_request, indent=2), encoding='utf-8')
    run([*req['shape_command'], '--request', str(output / 'shape_request.json')], req['shape_cwd'], output / 'shape.log')
    shape = json.loads((output / 'shape/generation.json').read_text(encoding='utf-8'))
    if shape.get('status') != 'GENERATED_NEEDS_REVIEW': raise ValueError('Shape stage did not report a real generation')
    alpha = output / 'shape/source_alpha.png'
    if not alpha.is_file(): alpha = image  # TripoSG keeps no copy of its input
    texture_request = dict(engine_path=req['texture_engine_path'], mesh=str(output / 'shape/raw.glb'), image=str(alpha),
                           output_dir=str(output / 'texture'), seed=req['seed'], uv_size=req.get('uv_size', 4096), steps=req.get('texture_steps', 50))
    (output / 'texture_request.json').write_text(json.dumps(texture_request, indent=2), encoding='utf-8')
    run([req['texture_python'], '-B', '-u', req['texture_worker'], '--request', str(output / 'texture_request.json')], req['texture_engine_path'], output / 'texture.log')
    texture = json.loads((output / 'texture/texture_report.json').read_text(encoding='utf-8'))
    shutil.copyfile(texture['textured_glb'], output / 'raw.glb')
    shutil.copyfile(alpha, output / 'source_alpha.png')
    report = dict(shape, engine=req['engine'], shape_engine=shape.get('engine'), texture=texture, pbr='basecolor projected by MV-Adapter (no metallic/roughness maps)',
                  status='GENERATED_NEEDS_REVIEW', duration_seconds=round(shape.get('duration_seconds', 0) + texture['seconds'], 1))
    (output / 'generation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('RESULT ' + json.dumps(dict(engine=req['engine'], seconds=report['duration_seconds'], texture_vram_gib=texture['peak_vram_gib'])), flush=True)


if __name__ == '__main__':
    sys.exit(main())
