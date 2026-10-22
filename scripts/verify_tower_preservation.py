"""Read-only checks of recovered real tower artifacts, not a new AI quality claim."""
import hashlib
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from apps.api.inspection import inspect_glb


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    base=ROOT/'.local/data-reset-backups/20261021T181054Z/workspace-data'
    run=base/'generation/trellis2/20261021T141104_43_d17ec2/output'
    receipt=json.loads((run/'generation.json').read_text('utf-8'))
    glb=run/'raw.glb';master=run/'raw_master.npz'
    reference=ROOT/'.local/fixtures/ArcherTowerSource.png'
    assert digest(glb)==receipt['output_sha256']
    assert digest(reference)==receipt['source_sha256']
    assert master.is_file()
    measured=inspect_glb(glb)
    assert measured['triangles']>0 and measured['images']
    assert any(m.get('base_color_texture') for m in measured['materials'])
    report=dict(status='VERIFIED_PRESERVED_REAL_OUTPUT',source=str(reference),source_sha256=digest(reference),
        raw_glb=str(glb),raw_glb_sha256=digest(glb),raw_master=str(master),raw_master_sha256=digest(master),
        generation_receipt=str(run/'generation.json'),generation_receipt_sha256=digest(run/'generation.json'),
        original_request=receipt['request'],model_revision=receipt['model_revision'],raw_native_triangles=receipt['raw_triangles'],measured_glb=measured,
        limitations=['Recovered original result, not a fresh inference benchmark.',
            'User recalled a high-quality tower; exact preferred seed is not independently confirmed.',
            'No artist approval or Meshy equivalence inferred from structural checks.',
            'Original profile is seed 43, 24 steps, 1024 cascade, 4096 textures; do not confuse with current Maximum 32-step preset.'])
    target=ROOT/'docs/evidence/tower_quality_preservation.json'
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(dict(status=report['status'],triangles=measured['triangles'],embedded_images=measured['images'],receipt=str(target))))


if __name__=='__main__':main()
