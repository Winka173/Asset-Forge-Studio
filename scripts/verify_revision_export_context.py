"""Real retained GLB checks with an in-memory stale-context failure injection.

No original prompt/specification or game delivery is mutated. This does not run
AI or invent output; the supplied native acceptance Library contains real GLBs.
"""
import argparse
import copy
import json
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--native-run',required=True);args=parser.parse_args()
run=Path(args.native_run).resolve();os.environ['AFS_DATA']=str(run/'Library');sys.path.insert(0,str(ROOT))
from fastapi import HTTPException
from apps.api import studio,store,export_profiles

receipt=json.loads((run/'report.json').read_text('utf-8'))
revision_check=next(c for c in receipt['checks'] if c['name']=='material_only_revision_no_AI_geometry_preserved_staged_promote_rollback')
original=studio.asset(revision_check['revision']['asset_id']);v2=revision_check['v2']
before=copy.deepcopy(original)
candidate=copy.deepcopy(original)
revision=next(r for r in candidate['revisions'] if r.get('artifact_id')==v2)
revision.pop('artifact_id')  # Simulates the real pre-export commit window.
candidate['resolved_specification']['asset_generation_spec']['bounds_m']=[999.,999.,999.]
record,path,qa=export_profiles._source(candidate,v2)
assert record['id']==v2 and qa['triangles']>0
# Same real red GLB must fail a contradictory explicit blue revision contract.
wrong=copy.deepcopy(candidate);r=next(r for r in wrong['revisions'] if r['id']==revision['id'])
r['plan']['material_edit']['color_hex']='#263b59'
blocked=False
try:export_profiles._source(wrong,v2)
except HTTPException as exc:
    assert exc.status_code==409;blocked=True
assert blocked,'Wrong roof color bypassed the pinned revision gate'
after=studio.asset(original['id'])
for field in ('original_prompt','original_prompt_sha256','resolved_specification','revisions','published_artifact_id','publication_history'):
    assert after.get(field)==before.get(field),field
assert store.digest(path)==record['sha256']
report=dict(status='PASS_REAL_INFLIGHT_REVISION_CONTEXT_AND_COLOR_REJECTION',native_run=str(run),asset_id=original['id'],artifact_id=v2,artifact_sha256=record['sha256'],
    checks=dict(inflight_revision_resolved=True,stale_original_not_used=True,contradictory_color_blocked=True,original_metadata_preserved=True),
    scope='Real GLB validation with in-memory negative context injection; no new inference or artistic claim')
(ROOT/'docs/evidence/revision_export_context.json').write_text(json.dumps(report,indent=2),'utf-8')
print(json.dumps(report))
