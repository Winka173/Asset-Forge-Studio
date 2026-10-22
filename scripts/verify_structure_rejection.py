"""Remove a real castle component, prove technical validity cannot bypass structure."""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);args=parser.parse_args();run=Path(args.run).resolve()
os.environ['AFS_DATA']=str(run/'Library')
import trimesh
from fastapi import HTTPException
from apps.api import store,batch,quality_evaluation,export_profiles,studio
from apps.api.inspection import inspect_glb

original=json.loads((run/'report.json').read_text(encoding='utf-8'));value=batch.batch(original['batch_id']);item=value['items'][0]
parent=store.get_artifact(item['automation']['export']['artifact_id']);source=store.safe_path(parent['relative_path'])
scene=trimesh.load(source,force='scene',process=False);node=next(n for n in scene.graph.nodes_geometry if n=='corner_tower_nw')
_,geometry=scene.graph[node];scene.delete_geometry(geometry)
folder=store.DATA/'acceptance-negative-structure'/uuid.uuid4().hex;folder.mkdir(parents=True);path=folder/'missing-tower.glb';scene.export(path)
technical=inspect_glb(path);assert technical['triangles']>0
bad=store.add_artifact(path,'candidate','Negative acceptance / deliberately missing NW tower',parent['metadata']|dict(acceptance_failure_injection=True))
evaluation=quality_evaluation.evaluate(item,bad);assert not evaluation['eligible']
structural=next(g for g in evaluation['gates'] if g['layer']=='structure');assert structural['outcome']=='BLOCKED' and 'corner_tower_nw' in structural['evidence']['missing']
published=studio.asset(item['asset_id']).get('published_artifact_id')
try:export_profiles.export_asset(value['project_id'],item['asset_id'],bad['id']);raise AssertionError('Invalid structure was exported')
except HTTPException as exc:assert exc.status_code==409
assert studio.asset(item['asset_id']).get('published_artifact_id')==published
report=dict(status='VERIFIED_REAL_GLB_MISSING_MANDATORY_TOWER_REJECTED',source_sha256=parent['sha256'],negative_sha256=bad['sha256'],
    technical_integrity='PASS',structural_gate=structural,export_blocked=True,original_delivery_preserved=True,scope='Deliberate geometry mutation for acceptance; not an engine failure or a real OOM')
(root/'docs/evidence/adaptive_structure_rejection.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(report['status'])
