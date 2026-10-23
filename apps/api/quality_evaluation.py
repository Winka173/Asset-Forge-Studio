"""Four independent, hash-bound QA layers. Unknown is not a pass."""
import json
from typing import Literal
from pydantic import BaseModel,ConfigDict
from . import store,studio
from .inspection import inspect_glb,glb_document
from engines.quality import fingerprint
VERSION=3


def validator_hash():
    # Cached technical passes must expire when a dependent inspector changes too.
    return fingerprint({name:store.digest(store.ROOT/'apps/api'/name) for name in
        ('quality_evaluation.py','inspection.py','surface_diagnostics.py','texture_diagnostics.py')})


def compare_component_geometry(source,target,required,scale,tolerance):
    import numpy as np
    import trimesh
    original=trimesh.load(source,force='scene',process=False);actual=trimesh.load(target,force='scene',process=False);checks=[]
    for name in sorted(required):
        if name not in original.graph.nodes_geometry or name not in actual.graph.nodes_geometry:continue
        tf,key=original.graph[name];base=original.geometry[key];expected=trimesh.transform_points(base.vertices,tf)*scale
        tf,key=actual.graph[name];mesh=actual.geometry[key];vertices=trimesh.transform_points(mesh.vertices,tf)
        def distances(left,right):
            grid={}
            for point in np.unique(right,axis=0):grid.setdefault(tuple(np.floor(point/tolerance).astype(np.int64)),[]).append(point)
            maximum=0.
            for point in np.unique(left,axis=0):
                cell=np.floor(point/tolerance).astype(np.int64)
                near=[p for x in (-1,0,1) for y in (-1,0,1) for z in (-1,0,1) for p in grid.get(tuple(cell+(x,y,z)),[])]
                if not near:return None
                nearest=float(np.linalg.norm(np.asarray(near)-point,axis=1).min());maximum=max(maximum,nearest)
                if nearest>tolerance:return maximum
            return maximum
        forward=distances(expected,vertices);reverse=distances(vertices,expected)
        error=max(forward,reverse) if forward is not None and reverse is not None else None
        checks.append(dict(component=name,triangle_count_unchanged=len(base.faces)==len(mesh.faces),max_vertex_distance_m=error,
            tolerance_m=tolerance,passed=len(base.faces)==len(mesh.faces) and error is not None and error<=tolerance))
    return checks


def roof_color_check(path,hex_color):
    import numpy as np
    import trimesh
    scene=trimesh.load(path,force='scene',process=False);expected=np.array([int(hex_color[i:i+2],16) for i in (1,3,5)],dtype=float);checks=[];seen=set()
    for node in scene.graph.nodes_geometry:
        if not (node.startswith('roof_') or node.endswith('_roof')):continue
        _,key=scene.graph[node];mat=getattr(scene.geometry[key].visual,'material',None)
        if mat is None:continue
        name=getattr(mat,'name',node)
        if name in seen:continue
        seen.add(name);texture=getattr(mat,'baseColorTexture',None);raw_factor=getattr(mat,'baseColorFactor',None)
        factor=np.array(raw_factor if raw_factor is not None else [1]*4,dtype=float)[:3]
        if factor.max()>1:factor/=255
        measured=np.array(texture.convert('RGB').resize((64,64)),dtype=float).mean(axis=(0,1))*factor if texture is not None else factor*255
        checks.append(dict(material=name,expected_srgb=expected.tolist(),measured_mean_srgb=measured.tolist(),tolerance_per_channel=12,
            passed=bool(np.max(np.abs(expected-measured))<=12)))
    return dict(requested_hex=hex_color,materials=checks,passed=bool(checks) and all(c['passed'] for c in checks),
        method='Embedded basecolor pixel mean/factor check, not rendered lighting or perceptual style approval')


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
    qa=inspect_glb(path);gates=[Gate(layer='technical',outcome='PASS',mandatory=True,tool='AFS glTF/trimesh inspector with embedded image validation',
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
        source=candidate if candidate['metadata'].get('assembly_report') else store.get_artifact(candidate['metadata']['parent_id']);seen=set()
        while not source['metadata'].get('assembly_report'):
            if source['id'] in seen or not source['metadata'].get('parent_id'):raise ValueError('Assembly provenance missing')
            seen.add(source['id']);source=store.get_artifact(source['metadata']['parent_id'])
        report_path=store.safe_path(source['metadata']['assembly_report'])
        assembly=json.loads(report_path.read_text(encoding='utf-8'))
        manifest=json.loads((store.DATA/'jobs'/source['metadata']['job_id']/'manifest.json').read_text(encoding='utf-8'))
        if store.digest(report_path)!=manifest['assembly_report_sha256'] or assembly['spec_sha256']!=(item.get('structural_parent_spec_hash') or spec_hash):raise ValueError('Assembly structural receipt changed')
        raw=store.safe_path(source['relative_path'])
        if store.digest(raw)!=source['sha256'] or assembly.get('output_sha256',source['sha256'])!=source['sha256']:raise ValueError('Assembly raw checkpoint checksum changed')
        baseline=assembly.get('spec',{}).get('bounds_m') or expected
        ratios=[a/b for a,b in zip(expected,baseline)]
        uniform=max(ratios)-min(ratios)<1e-5
        geometry=compare_component_geometry(raw,path,required,ratios[0],max(expected)*1e-5) if not missing and uniform else []
        color_checks=[roof_color_check(path,r['value']) for r in spec.get('requirements',[]) if r['id']=='roof_color' and r.get('hard_gate')]
        counts=dict(corner_towers=sum(n.startswith('corner_tower_') for n in names),curtain_walls=sum(n.startswith('curtain_wall_') for n in names),keep=sum(n=='keep' for n in names),gate=sum(n=='gate_arch' for n in names))
        passed=not missing and match and counts==dict(corner_towers=4,curtain_walls=5,keep=1,gate=1) and all(assembly['checks'].values()) and uniform and len(geometry)==len(required) and all(g['passed'] for g in geometry) and all(c['passed'] for c in color_checks)
        structure=Gate(layer='structure',outcome='PASS' if passed else 'BLOCKED',mandatory=True,tool='AFS named assembly validator v3 / '+assembly['blender_version'],
            evidence=dict(missing=missing,counts=counts,measured_bounds_xyz_m=dimensions,expected_bounds_xyz_m=expected_yup,assembly_report_sha256=manifest['assembly_report_sha256'],
                checks=assembly['checks'],wall_contacts=assembly['contacts'],gate_clearance=assembly['portal_clearance'],component_geometry=geometry,uniform_scale=ratios[0],explicit_roof_colors=color_checks),
            limitations=['Connector contact uses measured AABBs, not exact intersection-free CSG or navigation testing. LOD silhouette error remains unmeasured.'])
    gates.append(structure)
    gates.append(Gate(layer='visual',outcome='NOT_EVALUATED' if not visual or visual.get('evaluation_status')=='NOT_EVALUATED' else 'FLAGGED_UNCERTAIN',mandatory=False,
        tool=(visual or {}).get('model') or 'Local visual evaluator unavailable',evidence=visual or {},limitations=['Uncalibrated VLM observations are not an artistic pass. No fixed numerical art score is used.']))
    from engines.concept_prompt import rig_class,subject_anchor
    subject=((item.get('prompt_interpretation') or {}).get('chunks') or [{}])[0].get('interpretation',{}).get('requested_subject_en') or subject_anchor(item.get('resolved_prompt') or item.get('prompt',''))
    kind=rig_class(subject);integration={}
    if kind:
        # Characters/creatures will almost always be animated next: record measured rig-readiness evidence (non-blocking).
        from .rig_readiness import measure as rig_measure
        integration['rig_readiness']=rig_measure(path,kind)
    flagged=kind=='humanoid' and not integration['rig_readiness'].get('limbs_clear')
    gates.append(Gate(layer='game_integration',outcome='FLAGGED_UNCERTAIN' if flagged else 'NOT_EVALUATED',mandatory=False,tool='AFS rig-readiness heuristics' if kind else 'No target Editor run for this artifact',evidence=integration,
        limitations=['No Unity/Unreal, target-camera or performance acceptance is implied.']+(['Arms are not clear of the torso; auto-rigging will likely need cleanup.'] if flagged else [])))
    report=dict(schema_version=VERSION,validator_sha256=validator,cache_key=key,spec_hash=spec_hash,parent_spec_hash=item.get('structural_parent_spec_hash'),artifact_id=candidate['id'],artifact_sha256=candidate['sha256'],at=store.now(),
        gates=[g.model_dump() for g in gates],eligible=all(g.outcome=='PASS' for g in gates if g.mandatory),artistic_approval=False)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM assets WHERE id=?',(item['asset_id'],)).fetchone();latest=json.loads(row['payload'])
        evaluations=latest.setdefault('quality_evaluations',[])
        if not any(r['cache_key']==key for r in evaluations):evaluations.append(report)
        db.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(latest),item['asset_id']))
    return report
