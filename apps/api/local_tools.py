"""Bounded local tool discovery. Detection does not install or activate software."""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from . import store

router=APIRouter(prefix='/api/tools')
Tool=Literal['blender','unity','unreal']
LOCK=threading.RLock()
CACHE={}


def config():
    with store.connect() as db:row=db.execute('SELECT payload FROM drafts WHERE project_id=?',('__afs_local_tools__',)).fetchone()
    return json.loads(row['payload']) if row else {}


def candidates(kind,include_config=True):
    paths=[]
    if include_config and config().get(kind):paths.append(Path(config()[kind]))
    env=os.environ.get({'blender':'AFS_BLENDER','unity':'AFS_UNITY','unreal':'AFS_UNREAL'}[kind])
    if env:paths.append(Path(env))
    found=shutil.which({'blender':'blender','unity':'Unity','unreal':'UnrealEditor'}[kind])
    if found:paths.append(Path(found))
    program=Path(os.environ.get('ProgramFiles','C:/Program Files'))
    roots=[(Path.home()/'Tools','blender*/blender.exe'),(program/'Blender Foundation','Blender */blender.exe')] if kind=='blender' else [(program/'Unity/Hub/Editor','*/Editor/Unity.exe')] if kind=='unity' else [(program/'Epic Games','UE_*/Engine/Binaries/Win64/UnrealEditor.exe')]
    for root,pattern in roots:
        if root.is_dir():paths.extend(sorted(root.glob(pattern),reverse=True))
    if os.name=='nt':
        import winreg
        keys=[(winreg.HKEY_CURRENT_USER,r'Software\Epic Games\Unreal Engine\Builds')] if kind=='unreal' else []
        for hive,key in keys:
            try:
                with winreg.OpenKey(hive,key) as handle:
                    for i in range(min(winreg.QueryInfoKey(handle)[1],30)):
                        _,value,_=winreg.EnumValue(handle,i);paths.append(Path(value)/'Engine/Binaries/Win64/UnrealEditor.exe')
            except OSError:pass
    unique=list(dict.fromkeys(str(p.resolve()) for p in paths))
    return unique[:12]


def inspect(kind,path):
    p=Path(path);expected={'blender':'blender.exe','unity':'Unity.exe','unreal':'UnrealEditor.exe'}[kind]
    if not p.is_file():raise ValueError('File does not exist. Find again or choose the installed executable.')
    if os.name=='nt' and p.name.lower()!=expected.lower():raise ValueError('Choose '+expected+', not a launcher, shortcut or another application.')
    flags=dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name=='nt' else {}
    version=''
    if kind=='blender':
        run=subprocess.run([str(p),'--version'],capture_output=True,timeout=12,**flags)
        output=(run.stdout+run.stderr).decode('utf-8',errors='replace')
        match=re.search(r'Blender (\d+\.\d+(?:\.\d+)?)',output)
        if run.returncode or not match:raise ValueError('The selected file did not identify itself as Blender. Previous selection was kept.')
        version=match[1]
    elif kind=='unity':
        # Read PE version resources without opening an Editor or activating a license.
        if os.name!='nt':raise ValueError('Unity executable validation is currently supported on Windows.')
        script="[System.Diagnostics.FileVersionInfo]::GetVersionInfo($env:AFS_TOOL_PROBE).ProductVersion"
        run=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=os.environ|{'AFS_TOOL_PROBE':str(p)},capture_output=True,timeout=12,**flags)
        text=run.stdout.decode('utf-8',errors='replace').strip();match=re.match(r'(\d+\.\d+\.\d+[abfp]\d+)',text)
        if run.returncode or not match:raise ValueError('The executable has no recognized Unity Editor product version. Choose Unity.exe inside Editor.')
        version=match[1]
    else:
        metadata=p.parents[2]/'Build/Build.version'
        if not metadata.is_file():raise ValueError('Unreal Engine/Build/Build.version was not found next to this Editor. Choose an installed UnrealEditor.exe.')
        value=json.loads(metadata.read_text(encoding='utf-8-sig'))
        version='.'.join(str(value[k]) for k in ('MajorVersion','MinorVersion','PatchVersion'))
    supported=kind=='blender' or kind=='unity' and version=='6000.4.8f1'
    reason=('Headless executable identified; each exported asset still requires technical QA.' if kind=='blender' else 'Pinned Unity 6000.4.8f1 / Built-in profile.' if supported else 'Editor detected, but this version has not passed the AFS native import profile.' if kind=='unity' else 'Editor detected only. Native Unreal generation/import remains unavailable and has not been validated.')
    return dict(tool=kind,path=str(p.resolve()),version=version,installed=True,validated=True,pipeline_supported=supported,reason=reason)


def discover(force=False):
    with LOCK:
        key=str(store.DATA)
        if not force and key in CACHE:return CACHE[key]
        selected=config();results=[]
        for kind in ('blender','unity','unreal'):
            found=[];errors=[]
            for path in candidates(kind):
                try:found.append(inspect(kind,path))
                except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:errors.append(dict(path=path,message=str(exc)))
            chosen=next((v for v in found if v['path']==str(Path(selected[kind]).resolve())),None) if kind in selected else None
            chosen=chosen or next((v for v in found if v['pipeline_supported']),None) or (found[0] if found else None)
            results.append(dict(tool=kind,selected=chosen,candidates=found,errors=errors,status='ready' if chosen and chosen['pipeline_supported'] else 'detected_unsupported' if chosen else 'not_found',searched='Saved selection, environment, PATH and standard installation folders; Unreal registered builds',selection_error=next((e['message'] for e in errors if kind in selected and e['path']==selected[kind]),None)))
        result=dict(tools=results,checked_at=store.now(),scope='Local detection only; no downloads, activation, AI inference or game project changes')
        CACHE[key]=result;return result


def executable(kind):
    cached=CACHE.get(str(store.DATA))
    if cached:
        result=next((t for t in cached['tools'] if t['tool']==kind),None)
        if result and result['selected']:
            return result['selected']['path'] if result['selected']['pipeline_supported'] else None
    selected=config().get(kind)
    if selected and Path(selected).is_file():return selected
    paths=candidates(kind,False)
    if kind=='unity':paths=[p for p in paths if '6000.4.8f1' in p]
    return next((p for p in paths if Path(p).is_file()),None)


@router.get('')
def inventory():return discover()


@router.post('/detect')
def detect():return discover(True)


class Choose(BaseModel):
    tool:Tool
    path:str=Field(min_length=1,max_length=2000)


@router.post('/select')
def choose(body:Choose):
    from . import jobs
    if any(j['status'] not in jobs.TERMINAL|{'QUEUED'} for j in jobs.listing()):raise HTTPException(409,'A stage is running. Wait for its safe checkpoint before changing tool paths.')
    try:value=inspect(body.tool,body.path)
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired) as exc:raise HTTPException(400,str(exc))
    with LOCK:
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM drafts WHERE project_id=?',('__afs_local_tools__',)).fetchone();saved=json.loads(row['payload']) if row else {}
            saved[body.tool]=value['path'];db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',('__afs_local_tools__',json.dumps(saved)))
        CACHE.pop(str(store.DATA),None)
    return value
