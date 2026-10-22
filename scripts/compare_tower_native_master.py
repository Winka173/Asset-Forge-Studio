"""Compare recovered original vs a real replay, without changing either file."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--replay',required=True);args=parser.parse_args()
baseline=json.loads((ROOT/'docs/evidence/tower_quality_preservation.json').read_text('utf-8'))
original=Path(baseline['raw_master']);replay=Path(args.replay).resolve()
targets=list((replay/'Library/jobs').glob('*/output/raw_master.npz'))
assert len(targets)==1,'Choose one isolated replay with one inference'
with np.load(original) as first,np.load(targets[0]) as second:
    assert set(first.files)==set(second.files)
    checks=[dict(field=k,original_shape=list(first[k].shape),replay_shape=list(second[k].shape),array_equal=bool(np.array_equal(first[k],second[k])),
        original_sha256=hashlib.sha256(first[k].tobytes()).hexdigest(),replay_sha256=hashlib.sha256(second[k].tobytes()).hexdigest()) for k in first.files]
report=dict(status='PASS_EXACT_NATIVE_MASTER_REPLAY' if all(c['array_equal'] for c in checks) else 'NEEDS_REVIEW_NATIVE_MASTER_DIFFERS',
    original=str(original),replay=str(targets[0]),checks=checks,
    limitations=['Exact native geometry and sparse PBR field equality, not a generic art/Meshy quality score.',
        'GLB remeshing, UV packing, raster textures and finishing are separate outputs and need their own checks.'])
(replay/'native-master-comparison.json').write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report))
assert report['status']=='PASS_EXACT_NATIVE_MASTER_REPLAY'
