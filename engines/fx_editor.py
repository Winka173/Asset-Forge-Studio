"""Real native Unity FX adapter. Isolated project, editable sources and cold reopen."""
import json
import shutil
import zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from apps.api import store
from . import unity_editor
from .quality import fingerprint

VERSION=unity_editor.VERSION
OUTPUT_ARTIFACTS=[('AFS_Effect.unitypackage','engine_package'),('effect_sources.zip','effect_source'),('fx_report.json','qa_report'),('fx_reopen.json','qa_report'),('fx_package_reopen.json','qa_report')]

def config_for(recipe,checksum):
    if not unity_editor.probe()['installed']:raise ValueError('Pinned Unity Editor/importer is not installed')
    paths=['engines/fx_editor.py','apps/api/fx.py','integrations/unity/Templates/AFSFxBuilder.cs','integrations/unity/Templates/AFSFxPackageVerify.cs','integrations/unity/Templates/FX/AFSSlashEffect.cs','integrations/unity/Templates/FX/AFSSlash.shader']
    return dict(schema_version='1.0',engine='unity_fx',version=VERSION,render_pipeline='Built-in',recipe=recipe,source_sha256=checksum,toolchain={p:store.digest(store.ROOT/p) for p in paths},frames=24,width=1280,height=720,quality='Maximum',ai_inference=False,game_ready=False)

def prepare(payload,record,folder):
    recipe=json.loads(store.safe_path(record['relative_path']).read_text());actual=config_for(recipe,record['sha256'])
    if actual!=payload['effective_config'] or fingerprint(actual)!=payload['effective_config_hash']:raise ValueError('FX recipe or toolchain changed since admission; no automatic substitution')
    project=folder/'editor_project';output=folder/'output'
    if project.exists() or output.exists():raise ValueError('Use a fresh immutable FX retry project')
    for relative in ['Assets/AFS/FX/Runtime','Assets/Editor','Packages','ProjectSettings']:(project/relative).mkdir(parents=True,exist_ok=True)
    output.mkdir();shutil.copytree(store.ROOT/unity_editor.PACKAGE,project/'Packages/com.assetforge.editor')
    shutil.copytree(store.ROOT/'integrations/unity/Templates/FX',project/'Assets/AFS/FX/Runtime',dirs_exist_ok=True)
    shutil.copyfile(store.ROOT/'integrations/unity/Templates/AFSFxBuilder.cs',project/'Assets/Editor/AFSFxBuilder.cs')
    shutil.copyfile(store.safe_path(record['relative_path']),project/'Assets/AFS/FX/recipe.json')
    (project/'Packages/manifest.json').write_text(json.dumps(dict(dependencies={f'com.unity.modules.{m}':'1.0.0' for m in ['imageconversion','jsonserialize','physics','ai','terrain','terrainphysics']})))
    (project/'ProjectSettings/ProjectVersion.txt').write_text(f'm_EditorVersion: {VERSION}\n')
    (project/'FxRequest.json').write_text(json.dumps(dict(outputPath=str(output),configHash=payload['effective_config_hash'],frames=actual['frames'],width=actual['width'],height=actual['height'])))
    common=[unity_editor.probe()['editor'],'-batchmode','-projectPath',str(project),'-quit','-accept-apiupdate']
    imported=folder/'package_import_project'
    for relative in ['Assets/Editor','Packages','ProjectSettings']:(imported/relative).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(project/'Packages/manifest.json',imported/'Packages/manifest.json')
    shutil.copyfile(project/'ProjectSettings/ProjectVersion.txt',imported/'ProjectSettings/ProjectVersion.txt')
    shutil.copyfile(store.ROOT/'integrations/unity/Templates/AFSFxPackageVerify.cs',imported/'Assets/Editor/AFSFxPackageVerify.cs')
    shutil.copyfile(project/'FxRequest.json',imported/'FxRequest.json')
    return [(common+['-force-d3d11','-executeMethod','AFSFxBuilder.Run','-logFile',str(folder/'unity.log')],'fx_native_build_and_gpu_frames'),(common+['-nographics','-executeMethod','AFSFxBuilder.Reopen','-logFile',str(folder/'unity_reopen.log')],'fx_cold_editor_reopen'),
            ([unity_editor.probe()['editor'],'-batchmode','-nographics','-quit','-projectPath',str(imported),'-importPackage',str(output/'AFS_Effect.unitypackage'),'-logFile',str(folder/'unity_package_import.log')],'fx_import_package_into_empty_project'),
            ([unity_editor.probe()['editor'],'-batchmode','-nographics','-quit','-projectPath',str(imported),'-executeMethod','AFSFxPackageVerify.Run','-logFile',str(folder/'unity_package_verify.log')],'fx_verify_imported_package_in_separate_process')]

def validate(payload,folder):
    output=folder/'output';reports=[json.loads((output/name).read_text(encoding='utf-8-sig')) for name in ['fx_report.json','fx_reopen.json','fx_package_reopen.json']]
    if any(r.get('checks_passed') is not True or r.get('unity_version')!=VERSION or r.get('config_hash')!=payload['effective_config_hash'] for r in reports):raise ValueError('FX native build/reopen validation failed')
    if reports[0].get('effect_only_visible_pixels',0)<=50:raise ValueError('No visible effect in isolated GPU proof')
    native=folder/'editor_project/Assets/AFS/FX'
    for name in ['AFS_Effect.prefab','AFS_EffectPreview.unity','Runtime/AFSSlashEffect.cs','Runtime/AFSSlash.shader','recipe.json','Effect.mat','Steel.mat']:
        if not (native/name).is_file() or (native/name).stat().st_size==0:raise ValueError('Missing editable FX output: '+name)
    recipe=json.loads((native/'recipe.json').read_text(encoding='utf-8-sig'))
    if recipe.get('accent_color') and recipe.get('accent_strength',0)>0 and not (native/'Accent.mat').is_file():raise ValueError('Missing editable FX output: Accent.mat')
    frames=reports[0].get('renders',[])
    if len(frames)!=payload['effective_config']['frames']:raise ValueError('FX frame sequence incomplete')
    hashes=[]
    for frame in frames:
        p=output/frame['file']
        if p.parent!=output or p.suffix!='.png':raise ValueError('Invalid frame path')
        with Image.open(p) as image:
            if image.size!=(1280,720) or np.asarray(image.convert('RGB')).std()<1:raise ValueError('Blank/invalid native FX frame')
        hashes.append(store.digest(p))
    if len(set(hashes))<8:raise ValueError('FX sequence does not demonstrate changing frames')
    package=output/'AFS_Effect.unitypackage'
    if not package.is_file() or package.stat().st_size<1000:raise ValueError('Unity effect package missing')
    with zipfile.ZipFile(output/'effect_sources.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(native.rglob('*')):
            if p.is_file():archive.write(p,'Assets/AFS/FX/'+p.relative_to(native).as_posix())
    return dict(status='PASS_EDITOR_VALIDATION',engine='unity_fx',version=VERSION,effective_config_hash=payload['effective_config_hash'],reports=reports,frames=frames,frame_hashes=hashes,source_sha256=payload['effective_config']['source_sha256'],artistic_approval=False,game_ready=False,character_animation=False)
