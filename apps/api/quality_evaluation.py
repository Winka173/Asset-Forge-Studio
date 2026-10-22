"""Four independent, hash-bound QA layers. Unknown is not a pass."""
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict
from . import store,studio
from .inspection import inspect_glb,glb_document
from engines.quality import fingerprint
VERSION=2


def validator_hash():return store.digest(store.ROOT/'apps/api/quality_evaluation.py')


def evaluator_key(artifact,prompt,references,module,renders=None):
    from engines import intent_runtime
    manifest=intent_runtime.MODELS/'manifests/registry.ollama.ai/library/qwen3-vl/4b-instruct-q4_K_M'
    return fingerprint(dict(artifact_sha256=artifact['sha256'],prompt_sha256=fingerprint(prompt),references=references,renders=renders or [],
        evaluator_script_sha256=store.digest(store.ROOT/'engines'/module),model=intent_runtime.MODEL,
        model_manifest_sha256=store.digest(manifest) if manifest.is_file() else None,execution=dict(num_gpu=0,num_ctx=8192,temperature=0)))


class Gate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    layer:Literal['technical','structure','visual','game_integration']
    outcome:Literal['PASS','REPAIRABLE','FLAGGED_UNCERTAIN','BLOCKED','NOT_EVALUATED']
    mandatory:bool
    tool:str
    evidence:dict
    limitations:list[str]


def evaluate(item,candidate):
    path=store.safe_path(candidate['relative_path'])
    if store.digest(path)!=candidate['sha256']:raise ValueError('QA candidate checksum changed')
    spec=item.get('asset_generation_spec') or {};spec_hash=fingerprint(spec)
    visual=next((v for v in item.get('automation',{}).get('visual_checks',[]) if v['source_artifact_id']==candidate['id']),None)
    validator=validator_hash()
    key=fingerprint(dict(artifact=candidate['sha256'],spec=spec_hash,parent_spec=item.get('structural_parent_spec_hash'),visual=visual,version=VERSION,validator=validator))
    model=studio.asset(item['asset_id'])
    cached=next((r for r in model.get('quality_evaluations',[]) if r['cache_key']==key),None)
    if cached:return cached
    qa=inspect_glb(path);gates=[Gate(layer='technical',outcome='PASS',mandatory=True,tool='AFS glTF/trimesh inspector v1',
        evidence=dict(artifact_sha256=candidate['sha256'],checks=qa['checks'],triangles=qa['triangles'],dimensions_xyz_m=qa['dimensions_xyz_m']),
        limitations=['Does not prove zero self-intersections or UV overlap. Nonwatertight foliage/planes are not universally rejected.'])]
    structure=Gate(layer='structure',outcome='NOT_EVALUATED',mandatory=False,tool='AFS named assembly validator v1',evidence={},limitations=['No verified named assembly contract for this route.'])
    if spec.get('route')=='procedural_castle':
        doc=glb_document(path);meshes=doc.get('meshes',[])
        names={n.get('name','') for n in doc.get('nodes',[]) if isinstance(n.get('mesh'),int) and 0<=n['mesh']<len(meshes) and meshes[n['mesh']].get('primitives')}
        required={'keep','gate_arch','corner_tower_nw','corner_tower_ne','corner_tower_sw','corner_tower_se',
            'curtain_wall_north','curtain_wall_west','curtain_wall_east','curtain_wall_south_west','curtain_wall_south_east'}
        missing=sorted(required-names);dimensions=qa['dimensions_xyz_m'];expected=spec['bounds_m'];expected_yup=[expected[0],expected[2],expected[1]]
        match=all(abs(a-b)<=max(.005,b*.002) for a,b in zip(dimensions,expected_yup))
        source=store.get_artifact(candidate['metadata']['parent_id']);seen=set()
        while not source['metadata'].get('assembly_report'):
            if source['id'] in seen or not source['metadata'].get('parent_id'):raise ValueError('Assembly provenance missing')
            seen.add(source['id']);source=store.get_artifact(source['metadata']['parent_id'])
        report_path=store.safe_path(source['metadata']['assembly_report'])
        assembly=json.loads(report_path.read_text(encoding='utf-8'))
        manifest=json.loads((store.DATA/'jobs'/source['metadata']['job_id']/'manifest.json').read_text(encoding='utf-8'))
        if store.digest(report_path)!=manifest['assembly_report_sha256'] or assembly['spec_sha256']!=item.get('structural_parent_spec_hash',spec_hash):raise ValueError('Assembly structural receipt changed')
        counts=dict(corner_towers=sum(n.startswith('corner_tower_') for n in names),curtain_walls=sum(n.startswith('curtain_wall_') for n in names),keep=sum(n=='keep' for n in names),gate=sum(n=='gate_arch' for n in names))
        passed=not missing and match and counts==dict(corner_towers=4,curtain_walls=5,keep=1,gate=1) and all(assembly['checks'].values())
        structure=Gate(layer='structure',outcome='PASS' if passed else 'BLOCKED',mandatory=True,tool='AFS named assembly validator v1 / '+assembly['blender_version'],
            evidence=dict(missing=missing,counts=counts,measured_bounds_xyz_m=dimensions,expected_bounds_xyz_m=expected_yup,assembly_report_sha256=manifest['assembly_report_sha256'],
                checks=assembly['checks'],wall_contacts=assembly['contacts'],gate_clearance=assembly['portal_clearance']),
            limitations=['Connector contact uses measured AABBs, not exact intersection-free CSG or navigation testing. LOD silhouette error remains unmeasured.'])
    gates.append(structure)
    gates.append(Gate(layer='visual',outcome='NOT_EVALUATED' if not visual or visual.get('evaluation_status')=='NOT_EVALUATED' else 'FLAGGED_UNCERTAIN',mandatory=False,
        tool=(visual or {}).get('model') or 'Local visual evaluator unavailable',evidence=visual or {},limitations=['Uncalibrated VLM observations are not an artistic pass. No fixed numerical art score is used.']))
    gates.append(Gate(layer='game_integration',outcome='NOT_EVALUATED',mandatory=False,tool='No target Editor run for this artifact',evidence={},limitations=['No Unity/Unreal, target-camera or performance acceptance is implied.']))
    report=dict(schema_version=VERSION,validator_sha256=validator,cache_key=key,spec_hash=spec_hash,artifact_id=candidate['id'],artifact_sha256=candidate['sha256'],at=store.now(),
        gates=[g.model_dump() for g in gates],eligible=all(g.outcome=='PASS' for g in gates if g.mandatory),artistic_approval=False)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM assets WHERE id=?',(item['asset_id'],)).fetchone();latest=json.loads(row['payload'])
        evaluations=latest.setdefault('quality_evaluations',[])
        if not any(r['cache_key']==key for r in evaluations):evaluations.append(report)
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(latest),item['asset_id']))
    return report
