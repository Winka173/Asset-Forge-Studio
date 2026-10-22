"""Limited existing-clip Unity bridge; no rigging, retargeting or motion synthesis."""
import json
import shutil
from pathlib import Path
from apps.api import store
from apps.api.inspection import glb_document
from engines.animation_clip import clips
from engines.quality import fingerprint
from engines.unity_editor import VERSION,probe

PACKAGE='integrations/unity/Packages/com.assetforge.animation'

def package_hashes():
    return {p.relative_to(store.ROOT).as_posix():store.digest(p) for p in sorted((store.ROOT/PACKAGE).rglob('*')) if p.is_file()}

OUTPUT_ARTIFACTS=[('AFS_Animation.unitypackage','engine_package'),('unity_report.json','qa_report'),('unity_reopen_report.json','qa_report'),('unity_clean_import_report.json','qa_report'),('fbx_qa.json','qa_report')]

def effective_config(record,render=False):
    from apps.api.local_tools import executable
    if render:raise ValueError('Animation profile uses CPU deformation validation; GPU animation captures are not implemented')
    if not probe()['installed'] or not executable('blender'):raise ValueError('Validated local Blender and pinned Unity Editor are required')
    source=store.safe_path(record['relative_path'])
    if store.digest(source)!=record['sha256']:raise ValueError('Source checksum changed')
    doc=glb_document(source);motion=clips(source)
    if len(motion['clips'])!=1 or not motion['skins'] or motion['clips'][0]['start_seconds']!=0 or not motion['clips'][0]['retime_supported']:
        raise ValueError('This Unity animation profile requires one skinned LINEAR/STEP clip starting at zero')
    if doc.get('images') or any(p.get('targets') or 'WEIGHTS_1' in p.get('attributes',{}) for m in doc.get('meshes',[]) for p in m['primitives']):
        raise ValueError('Textured, morph-target and >4-influence animation profiles are not validated; source GLB remains available')
    duration=motion['clips'][0]['duration_seconds']
    if not 0<duration<=120:raise ValueError('Verified clip duration range: 0 to 120 seconds')
    return dict(stage='unity_animation',source_artifact_id=record['id'],source_sha256=record['sha256'],version=VERSION,
        render_pipeline='Built-in',toolchain=package_hashes()|{'scripts/blender_animation_fbx.py':store.digest(store.ROOT/'scripts/blender_animation_fbx.py')},
        blender=executable('blender'),duration_seconds=duration,bones=motion['bones'],bake_fps=120,render_gpu=False,
        source_quality='Original GLB unchanged; FBX bridge sampled at 120 fps; no motion/rig synthesis',artistic_approval='not_given')

def prepare(payload,record,folder):
    locked=effective_config(record,payload['use_gpu'])
    if locked!=payload['effective_config'] or fingerprint(locked)!=payload['effective_config_hash']:raise ValueError('Animation source/toolchain changed after enqueue')
    project=folder/'editor_project';clean=folder/'clean_project';output=folder/'output'
    if project.exists() or clean.exists() or output.exists():raise ValueError('Retry requires a new immutable validation attempt')
    output.mkdir();fbx=output/'Animation.fbx'
    request=dict(source=str(store.safe_path(record['relative_path'])),fbx=str(fbx),duration=locked['duration_seconds'],report=str(output/'fbx_qa.json'))
    (folder/'fbx_request.json').write_text(json.dumps(request))
    for location in (project,clean):
        for directory in ('Assets/AFS/Output','Packages','ProjectSettings'):(location/directory).mkdir(parents=True,exist_ok=True)
        shutil.copytree(store.ROOT/PACKAGE,location/'Packages/com.assetforge.animation')
        (location/'Packages/manifest.json').write_text(json.dumps({'dependencies':{f'com.unity.modules.{m}':'1.0.0' for m in ('animation','jsonserialize','physics','imageconversion')}}))
        (location/'ProjectSettings/ProjectVersion.txt').write_text(f'm_EditorVersion: {VERSION}\n')
        (location/'AnimationRequest.json').write_text(json.dumps(dict(outputPath=str(output),fbxPath=str(fbx),sourcePath=request['source'],duration=locked['duration_seconds'],bones=locked['bones'],effectiveConfigHash=payload['effective_config_hash'],packagePath=str(output/'AFS_Animation.unitypackage'))))
    blender=[locked['blender'],'-b','-t','4','--factory-startup','--python-exit-code','1','--python',str(store.ROOT/'scripts/blender_animation_fbx.py'),'--',str(folder/'fbx_request.json')]
    def command(location,method,log):return [probe()['editor'],'-batchmode','-nographics','-projectPath',str(location),*(['-quit'] if method!='CleanImport' else []),'-executeMethod','AssetForgeAnimation.'+method,'-logFile',str(folder/log)]
    return [(blender,'animation_fbx_and_deformation'),(command(project,'Run','unity.log'),'animation_native_import'),(command(project,'Reopen','unity_reopen.log'),'animation_cold_reopen'),(command(clean,'CleanImport','unity_clean.log'),'animation_clean_package_import')]

def validate(payload,folder):
    output=folder/'output';reports=[json.loads((output/name).read_text(encoding='utf-8-sig')) for name in ('unity_report.json','unity_reopen_report.json','unity_clean_import_report.json')]
    if any(not r.get('checks_passed') or r.get('unity_version')!=VERSION or r.get('effective_config_hash')!=payload['effective_config_hash'] for r in reports):raise ValueError('Animation Unity validation/reopen/clean import did not pass')
    fbx=json.loads((output/'fbx_qa.json').read_text())
    if fbx.get('status')!='PASS_FBX_DEFORMATION':raise ValueError('FBX deformation comparison failed')
    native=folder/'editor_project/Assets/AFS/Output'
    if any(not (native/name).is_file() for name in ('AFS_Animated.prefab','AFS_Animation.unity','AFS_Animation.controller')):raise ValueError('Serialized animated native output missing')
    package=output/'AFS_Animation.unitypackage'
    if not package.is_file() or package.stat().st_size==0:raise ValueError('Native animation package missing')
    return dict(status='PASS_EDITOR_VALIDATION',profile='existing_single_clip_animation',engine='unity',version=VERSION,reports=reports,fbx_deformation=fbx,
        native_files=[dict(path=p.relative_to(store.DATA).as_posix(),sha256=store.digest(p)) for p in sorted(native.rglob('*')) if p.is_file()],
        effective_config_hash=payload['effective_config_hash'],game_ready=False,artistic_approval='not_given',root_motion_quality='not_evaluated',foot_contact_quality='not_evaluated')
