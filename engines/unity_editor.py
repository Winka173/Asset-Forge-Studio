"""Unity Editor adapter: AFS-owned validation projects only, no production game writes."""
import json
import os
import shutil
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from apps.api import store
from .quality import fingerprint

VERSION='6000.4.8f1'
PIPELINE='Built-in'
PACKAGE='integrations/unity/Packages/com.assetforge.editor'


def probe():
    editor=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Unity/Hub/Editor'/VERSION/'Editor/Unity.exe'
    package=store.ROOT/PACKAGE
    return dict(id='unity_editor',installed=editor.is_file() and (package/'Editor/AssetForgeImport.cs').is_file(),
        editor=str(editor),version=VERSION,render_pipeline=PIPELINE,importer_version='0.1.0',
        outputs=['unity_prefab','unity_scene','unitypackage','material','lod_group','box_collider','import_report','gpu_previews'],
        constraints=['Only pinned Built-in Editor profile tested','AFS-owned project; no arbitrary target game path','Four validated FBX LODs and real basecolor/MR source maps required','Editor import is not artistic or target-platform performance approval'],
        engine_license='User installed Unity Editor license; no activation or license modification',asset_rights='Separate source/model/input provenance review required')


def package_hashes():
    return {p.relative_to(store.ROOT).as_posix():store.digest(p) for p in sorted((store.ROOT/PACKAGE).rglob('*')) if p.is_file()}


def source_files(record):
    from apps.api import jobs
    if record['metadata'].get('stage')!='blender_processed':raise ValueError('Select a validated Blender processed LOD0 first; raw GLB is not this native import profile')
    identifier=record['metadata']['job_id'];job=jobs.get(identifier)
    if job['payload']['kind']!='blender' or job['status']!='REVIEW_REQUIRED':raise ValueError('Blender stage has not passed validation')
    source=store.safe_path(f'jobs/{identifier}/output')
    report=json.loads((source/'report.json').read_text(encoding='utf-8'))
    if report['checks'].get('export_reopen')!='PASS':raise ValueError('Blender export reopen did not pass')
    names=[f'LOD{i}.fbx' for i in range(4)]+['textures/texture_000.png','textures/texture_001.png','report.json']
    if any(not (source/name).is_file() for name in names):raise ValueError('Native Unity PBR profile requires four real FBXs, basecolor and MR textures; no missing maps will be invented')
    materials=report.get('materials',[])
    if len(materials)!=1:raise ValueError('This tested profile supports exactly one material; additional material translations need validation')
    for name in ['textures/texture_000.png','textures/texture_001.png']:
        with Image.open(source/name) as image:
            if max(image.size)>4096:raise ValueError('Source texture exceeds tested 4K Unity profile; blocked instead of resizing Quality Lock')
    return source,names,report


def effective_config(record,render):
    if not probe()['installed']:raise ValueError('Pinned Unity Editor or importer missing')
    source,names,report=source_files(record)
    return dict(schema_version=1,stage='import_test',tool='unity_editor',version=VERSION,render_pipeline=PIPELINE,
        importer_version='0.1.0',importer_sha256=package_hashes(),source_artifact_id=record['id'],source_artifact_sha256=record['sha256'],
        source_files={name:store.digest(source/name) for name in names},render_gpu=render,
        material_conversion='glTF metallic B -> Unity R; smoothness=255-roughness G -> Unity A; no new channels',
        qa=dict(reopen_in_separate_editor=True,mesh_counts=True,uv_normals=True,metric_scale=True,pivot=True,materials=True,lod=True,collision=True),
        source_quality='preserve existing FBX/texture bytes; no decimation or regeneration',game_ready=False)


def prepare(payload,record,folder):
    locked=payload['effective_config']
    actual=effective_config(record,payload['use_gpu'])
    if fingerprint(actual)!=payload['effective_config_hash'] or actual!=locked:raise ValueError('Unity toolchain/source changed since enqueue; blocked without changing Quality Lock')
    source,names,report=source_files(record);project=folder/'editor_project';output=folder/'output'
    if project.exists() or output.exists():raise ValueError('Use a new immutable attempt, not an existing Unity project/output folder')
    for name in ['Assets/AFS/Input/textures','Assets/AFS/Output','Packages','ProjectSettings']:(project/name).mkdir(parents=True,exist_ok=True)
    output.mkdir()
    shutil.copytree(store.ROOT/PACKAGE,project/'Packages/com.assetforge.editor')
    modules=['imageconversion','jsonserialize','physics']
    (project/'Packages/manifest.json').write_text(json.dumps(dict(dependencies={f'com.unity.modules.{m}':'1.0.0' for m in modules}),indent=2))
    (project/'ProjectSettings/ProjectVersion.txt').write_text(f'm_EditorVersion: {VERSION}\n')
    for name in names:
        if name!='report.json':
            destination=project/'Assets/AFS/Input'/name
            shutil.copyfile(source/name,destination)
            if store.digest(destination)!=locked['source_files'][name]:raise ValueError('Copied Unity source checksum mismatch: '+name)
    mr=np.asarray(Image.open(project/'Assets/AFS/Input/textures/texture_001.png').convert('RGBA'))
    packed=np.zeros_like(mr);packed[:,:,0]=mr[:,:,2];packed[:,:,3]=255-mr[:,:,1]
    Image.fromarray(packed).save(project/'Assets/AFS/Input/textures/Unity_MetallicSmoothness.png')
    triangles=[sum(m['triangles'] for m in report['after'])]+[sum(m['triangles'] for m in lod['meshes']) for lod in report['lods']]
    if len(triangles)!=4:raise ValueError('Expected four source LOD levels')
    request=dict(outputPath=str(output),mode='render' if payload['use_gpu'] else 'import',expectedTriangles=triangles,
        expectedHeight=report['dimensions_xyz_m_blender'][2],effectiveConfigHash=payload['effective_config_hash'])
    (project/'QARequest.json').write_text(json.dumps(request,indent=2))
    (output/'source_manifest.json').write_text(json.dumps(dict(effective_config=locked,effective_config_hash=payload['effective_config_hash'],
        input_preserved=True,unity_project=str(project),expected_triangles=triangles),indent=2))
    # Include the editable importer source without requiring it in the runtime game.
    with zipfile.ZipFile(output/'AFS_Editor_Importer.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((store.ROOT/PACKAGE).rglob('*')):
            if path.is_file():archive.write(path,'com.assetforge.editor/'+path.relative_to(store.ROOT/PACKAGE).as_posix())
    editor=probe()['editor']
    common=[editor,'-batchmode','-projectPath',str(project),'-quit','-accept-apiupdate']
    first=common+['-executeMethod','AssetForgeImport.Run','-logFile',str(folder/'unity.log')]+(['-force-d3d11'] if payload['use_gpu'] else ['-nographics'])
    reopen=common+['-nographics','-executeMethod','AssetForgeImport.Reopen','-logFile',str(folder/'unity_reopen.log')]
    return [(first,'native_import_and_render' if payload['use_gpu'] else 'native_import'),(reopen,'cold_editor_reopen')]


def validate(payload,folder):
    output=folder/'output'
    reports=[json.loads((output/name).read_text(encoding='utf-8-sig')) for name in ['unity_report.json','unity_reopen_report.json']]
    if any(r.get('checks_passed') is not True or r.get('unity_version')!=VERSION or r.get('effective_config_hash')!=payload['effective_config_hash'] for r in reports):
        raise ValueError('Unity import/reopen checks did not pass the pinned profile')
    native=folder/'editor_project/Assets/AFS/Output'
    for name in ['AFS_Validated.prefab','AFS_Validation.unity','AFS_Standard.mat']:
        if not (native/name).is_file() or (native/name).stat().st_size==0:raise ValueError('Native serialized file missing: '+name)
    if not (output/'AFS_Asset.unitypackage').is_file():raise ValueError('Native package missing')
    if payload['use_gpu']:
        for capture in reports[0].get('renders',[]):
            path=output/capture['file']
            with Image.open(path) as image:
                if image.size!=(capture['width'],capture['height']) or np.asarray(image.convert('RGB')).std()<1:raise ValueError('Invalid/blank Unity GPU render')
        if len(reports[0].get('renders',[]))!=3:raise ValueError('Expected three actual Unity renders')
    files=[dict(path=p.relative_to(store.DATA).as_posix(),sha256=store.digest(p),bytes=p.stat().st_size) for p in sorted(native.rglob('*')) if p.is_file()]
    return dict(status='PASS_EDITOR_VALIDATION',engine='unity',version=VERSION,render_pipeline=PIPELINE,reports=reports,
        native_files=files,effective_config_hash=payload['effective_config_hash'],mesh_quality_parity='NOT_TESTED',human_quality_approval='NOT_GIVEN',game_ready=False)
