"""Deterministic terrain plus native Unity level assembly. No missing-prop AI jobs."""
import json
import shutil
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from apps.api import store
from apps.api.world_plan import WorldPlan,terrain
from . import unity_editor
from .quality import fingerprint

VERSION=unity_editor.VERSION
OUTPUT_ARTIFACTS=[('AFS_World.unitypackage','engine_package'),('world_sources.zip','world_source'),('world_unity_report.json','qa_report'),('world_unity_reopen.json','qa_report'),('world_qa.json','qa_report'),('height.png','heightmap'),('height.raw','heightfield'),('roads.png','mask'),('build_zones.png','mask')]


def code_hashes():
    result=unity_editor.package_hashes()
    for name in ['engines/world_editor.py','apps/api/world_plan.py','engines/unity_editor.py','integrations/unity/Templates/AFSWorldNavigation.cs']:
        result[name]=store.digest(store.ROOT/name)
    return result


def prop_sources(plan):
    from apps.api import jobs,studio
    result={}
    for prop in plan.props:
        identifier=prop.package_artifact_id
        if identifier in result:continue
        record=studio.scoped_artifact(identifier,plan.project_id)
        if record['role']!='engine_package':raise ValueError('Map props require actual validated Unity prefab packages from the same game')
        job=jobs.get(record['metadata']['job_id'])
        if job['status']!='REVIEW_REQUIRED' or job['payload']['kind']!='unity_import':raise ValueError('Selected prop does not have a passing static Unity import')
        folder=store.safe_path('jobs/'+job['id']);report=json.loads((folder/'manifest.json').read_text())
        if report.get('status')!='PASS_EDITOR_VALIDATION':raise ValueError('Prop import report did not pass')
        native=folder/'editor_project/Assets/AFS'
        if not (native/'Output/AFS_Validated.prefab').is_file():raise ValueError('Editable native prop source is missing')
        paths=[p for p in sorted(native.rglob('*')) if p.is_file() and not p.name.startswith('AFS_Validation.unity')]
        result[identifier]=dict(record=record,folder=native,files={p.relative_to(native).as_posix():store.digest(p) for p in paths},bounds=report['reports'][0]['bounds_m']['size'])
    footprints=[]
    for prop in plan.props:
        bounds=result[prop.package_artifact_id]['bounds'];w,d=float(bounds[0])*prop.scale,float(bounds[2])*prop.scale
        angle=np.deg2rad(prop.yaw_degrees);w,d=abs(np.cos(angle))*w+abs(np.sin(angle))*d,abs(np.sin(angle))*w+abs(np.cos(angle))*d
        if not any(abs(prop.x-z.x)+w/2<=z.width_m/2 and abs(prop.z-z.z)+d/2<=z.depth_m/2 for z in plan.build_zones):raise ValueError('Library prop footprint must fit an explicit build zone; no road/nav overlap substitution')
        for x,z,ow,od in footprints:
            if abs(prop.x-x)<(w+ow)/2 and abs(prop.z-z)<(d+od)/2:raise ValueError('Library prop footprints overlap')
        footprints.append((prop.x,prop.z,w,d))
    return result


def effective_config(record,render):
    if not unity_editor.probe()['installed']:raise ValueError('Pinned Unity Editor is missing')
    plan=WorldPlan.model_validate_json(store.safe_path(record['relative_path']).read_text())
    terrain(plan)  # Validate real quantized layout before GPU admission.
    props=prop_sources(plan)
    return dict(schema_version=1,stage='world_native_build',tool='unity_world',version=VERSION,render_pipeline='Built-in',generator_version='1.0',
        source_plan_sha256=record['sha256'],source_plan_id=record['id'],toolchain_sha256=code_hashes(),seed=plan.seed,resolution=plan.resolution,
        bit_depth=16,render_gpu=render,props={key:dict(package_sha256=value['record']['sha256'],native_files=value['files']) for key,value in props.items()},
        child_generation_jobs=0,child_generation_policy='BLOCK_MISSING_PROPS',qa=['quantized_source_connectivity','zone_overlap','native_terrain_collision','native_navmesh_paths','cold_editor_reopen'],
        performance='NOT_TESTED_IN_PLAYER',artistic_quality='NEEDS_HUMAN_REVIEW')


def prepare(payload,record,folder):
    expected=effective_config(record,payload['use_gpu'])
    if expected!=payload['effective_config'] or fingerprint(expected)!=payload['effective_config_hash']:raise ValueError('World Plan, library props or generator changed since approval/enqueue; no automatic substitution')
    plan=WorldPlan.model_validate_json(store.safe_path(record['relative_path']).read_text());raw,roads,zones,qa=terrain(plan)
    project=folder/'editor_project';output=folder/'output'
    if project.exists() or output.exists():raise ValueError('World build requires a fresh immutable attempt')
    sources=project/'Assets/AFS/World/Sources';sources.mkdir(parents=True);output.mkdir()
    (project/'Packages').mkdir();(project/'ProjectSettings').mkdir();(project/'Assets/AFS/Runtime').mkdir()
    shutil.copytree(store.ROOT/unity_editor.PACKAGE,project/'Packages/com.assetforge.editor')
    shutil.copyfile(store.ROOT/'integrations/unity/Templates/AFSWorldNavigation.cs',project/'Assets/AFS/Runtime/AFSWorldNavigation.cs')
    (project/'ProjectSettings/ProjectVersion.txt').write_text(f'm_EditorVersion: {VERSION}\n')
    modules=['imageconversion','jsonserialize','physics','ai','terrain','terrainphysics']
    (project/'Packages/manifest.json').write_text(json.dumps(dict(dependencies={f'com.unity.modules.{m}':'1.0.0' for m in modules}),indent=2))
    (sources/'world_plan.json').write_text(plan.model_dump_json(indent=2));raw.tofile(sources/'height.raw');Image.fromarray(raw).save(sources/'height.png')
    # PNG top row is north in overview; RAW and mask rows are explicit z indices.
    (roads*255).astype('uint8').tofile(sources/'roads.raw');Image.fromarray((roads*255).astype('uint8')).save(sources/'roads.png');Image.fromarray((zones*255).astype('uint8')).save(sources/'build_zones.png')
    rng=np.random.default_rng(plan.seed)
    for name,color in [('grass',plan.grass_color),('road',plan.road_color)]:
        rgb=np.array([int(color[i:i+2],16) for i in (1,3,5)])
        pixels=np.clip(rgb[None,None,:]+rng.integers(-9,10,(256,256,1)),0,255).astype('uint8');Image.fromarray(pixels).save(sources/(name+'.png'))
    overview=np.where(roads[:,:,None],np.array([145,123,88]),np.array([80,115,65])).astype('uint8');overview[zones]=[90,170,110];Image.fromarray(overview[::-1]).resize((768,768)).save(output/'layout_overview.png')
    (output/'world_qa.json').write_text(json.dumps(qa,indent=2))
    for name in ['height.raw','height.png','roads.png','build_zones.png','world_plan.json']:shutil.copyfile(sources/name,output/name)
    with zipfile.ZipFile(output/'world_sources.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sources.iterdir():archive.write(path,path.name)
    props=prop_sources(plan)
    for identifier,value in props.items():
        target=project/'Assets/AFS/Props'/identifier;target.mkdir(parents=True)
        for name,checksum in value['files'].items():
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(value['folder']/name,destination)
            if store.digest(destination)!=checksum:raise ValueError('Native library prop changed during copy')
    request=dict(outputPath=str(output),configHash=payload['effective_config_hash'],render=payload['use_gpu'],props=[dict(x=p.x,z=p.z,yaw_degrees=p.yaw_degrees,scale=p.scale,prefab_path=f'Assets/AFS/Props/{p.package_artifact_id}/Output/AFS_Validated.prefab') for p in plan.props])
    (project/'WorldRequest.json').write_text(json.dumps(request,indent=2))
    common=[unity_editor.probe()['editor'],'-batchmode','-projectPath',str(project),'-quit','-accept-apiupdate']
    return [(common+['-executeMethod','AFSWorldBuilder.Run','-logFile',str(folder/'unity.log')]+(['-force-d3d11'] if payload['use_gpu'] else ['-nographics']),'terrain_scene_navmesh_build'),
            (common+['-nographics','-executeMethod','AFSWorldBuilder.Reopen','-logFile',str(folder/'unity_reopen.log')],'cold_world_editor_reopen')]


def validate(payload,folder):
    reports=[json.loads((folder/'output'/name).read_text(encoding='utf-8-sig')) for name in ['world_unity_report.json','world_unity_reopen.json']]
    if any(r.get('checks_passed') is not True or r.get('unity_version')!=VERSION or r.get('config_hash')!=payload['effective_config_hash'] for r in reports):raise ValueError('Native World/Terrain/NavMesh build or cold reopen did not pass')
    root=folder/'editor_project/Assets/AFS/World'
    for name in ['RunavelleWorld.unity','TerrainData.asset','Navigation.asset']:
        if not (root/name).is_file():raise ValueError('Native world file missing: '+name)
    if not (folder/'output/AFS_World.unitypackage').is_file():raise ValueError('Native World package missing')
    if payload['use_gpu']:
        for name in ['world_overview.png','world_gameplay_preview.png']:
            with Image.open(folder/'output'/name) as image:
                if np.asarray(image.convert('RGB')).std()<1:raise ValueError('World GPU preview is blank')
    with Image.open(folder/'output/height.png') as image:
        if image.mode not in ['I;16','I'] or image.size!=(payload['effective_config']['resolution'],)*2:raise ValueError('Source heightmap bit depth/size mismatch')
    return dict(status='PASS_EDITOR_VALIDATION',engine='unity',version=VERSION,asset_type='map_environment',render_pipeline='Built-in',reports=reports,
        native_files=[dict(path=p.relative_to(store.DATA).as_posix(),sha256=store.digest(p),bytes=p.stat().st_size) for p in sorted(root.glob('*.asset'))]+[dict(path=(root/'RunavelleWorld.unity').relative_to(store.DATA).as_posix(),sha256=store.digest(root/'RunavelleWorld.unity'))],
        effective_config_hash=payload['effective_config_hash'],source_height_bit_depth=16,missing_prop_ai_jobs=0,artistic_quality='NEEDS_HUMAN_REVIEW',game_ready=False)
