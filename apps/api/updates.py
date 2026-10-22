"""Public upstream metadata + isolated, hash-pinned portable media updates.

Never pip-upgrade an engine, change a model revision, or launch an editor.
Maintenance uses the existing durable CPU queue; activation is a separate idle gate.
"""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from . import store, jobs

router=APIRouter(prefix='/api/updates')
KEY='__afs_updates__'
LOCK=threading.RLock()
DEFAULTS=dict(auto_check=True,auto_update_media=True)

def state():
    with store.connect() as db:row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(KEY,)).fetchone()
    return json.loads(row['payload']) if row else dict(policy=DEFAULTS.copy(),items=[],status='not_checked')

def save(**changes):
    with LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(KEY,)).fetchone()
        value=json.loads(row['payload']) if row else dict(policy=DEFAULTS.copy(),items=[])
        value.update(changes);db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(KEY,json.dumps(value)))
    return value

def fetch(url):
    request=urllib.request.Request(url,headers={'User-Agent':'AssetForgeStudio-updates/1','Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=20) as response:
        data=response.read(4*1024*1024+1)
    if len(data)>4*1024*1024:raise ValueError('Upstream metadata exceeds 4 MiB')
    return json.loads(data)

def version(text):return tuple(int(x) for x in re.findall(r'\d+',text)[:3])

def command_version(path):
    result=subprocess.run([str(path),'-version'],capture_output=True,text=True,timeout=12,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    match=re.search(r'(?:ffmpeg|ffprobe) version (\S+)',result.stdout)
    if result.returncode or not match:raise ValueError('Media executable version probe failed')
    return match[1]

def media_item():
    from engines.cinematic import media_tools
    local=None
    try:local=command_version(media_tools()['ffmpeg'])
    except (ValueError,OSError,subprocess.SubprocessError):pass
    data=fetch('https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest')
    candidates=[a for a in data.get('assets',[]) if re.fullmatch(r'ffmpeg-n\d+\.\d+-latest-win64-gpl-\d+\.\d+\.zip',a['name']) and re.fullmatch(r'sha256:[a-f0-9]{64}',a.get('digest') or '')]
    if not candidates:raise ValueError('No stable Win64 build with published SHA-256; automatic installation disabled')
    asset=max(candidates,key=lambda a:version(a['name']))
    latest=re.search(r'ffmpeg-n(\d+\.\d+)',asset['name'])[1]
    active=state().get('active_media');new_build=bool(active and active['archive_sha256']!=asset['digest'][7:])
    return dict(id='ffmpeg',name='FFmpeg + FFprobe',kind='tool',installed=local,latest=latest,status='available' if new_build or not local or version(local)[:2]<version(latest)[:2] else 'current',source='https://ffmpeg.org/download.html',provider='BtbN Windows builds (linked by FFmpeg)',license='GPL build; license notices retained',automatic=True,reason='Portable side-by-side install; actual H.264 encode, probe and decode before activation. Managed builds compare archive digests; unmanaged installs compare stable branches only.',candidate=dict(url=asset['browser_download_url'],sha256=asset['digest'][7:],bytes=asset['size'],name=asset['name']))

def model_item(identifier,name,repo,path):
    root=Path(path);revision=None
    if root.name=='main' and root.is_file():revision=root.read_text().strip()
    elif root.is_dir():
        if re.fullmatch('[a-f0-9]{40}',root.name):revision=root.name
        else:
            revisions=set()
            for metadata in root.glob('.cache/huggingface/download/**/*.metadata'):
                line=metadata.read_text(encoding='utf-8').splitlines()
                if line and re.fullmatch('[a-f0-9]{40}',line[0]):revisions.add(line[0])
            if len(revisions)==1:revision=revisions.pop()
    data=fetch('https://huggingface.co/api/models/'+repo)
    latest=data.get('sha');license=data.get('cardData',{}).get('license','not provided; review required')
    return dict(id=identifier,name=name,kind='model',installed=revision,detected=root.exists(),latest=latest,status='not_installed' if not root.exists() else 'revision_unknown' if not revision else 'current' if revision==latest else 'available',source='https://huggingface.co/'+repo,license=license,automatic=False,reason='Weights stay pinned. A new revision requires separate dependencies/license review and a real quality benchmark before promotion. Repository revision changes can be documentation-only; no quality improvement is assumed.')

def code_item(identifier,name,repo,path):
    revision=None
    if (Path(path)/'.git').exists():
        result=subprocess.run(['git','-C',str(path),'rev-parse','HEAD'],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode==0:revision=result.stdout.strip()
    upstream=fetch('https://api.github.com/repos/'+repo+'/commits?per_page=1')[0]['sha']
    return dict(id=identifier,name=name+' code',kind='engine_code',installed=revision,latest=upstream,status='not_installed' if not Path(path).exists() else 'revision_unknown' if not revision else 'current' if revision==upstream else 'available',source='https://github.com/'+repo,automatic=False,reason='Default-branch commit comparison only. Local patches, dependency compatibility and commercial licenses require a separate environment and regression benchmark; no git pull or pip upgrade is performed.')

def editor_item(kind):
    from .local_tools import discover
    item=next(t for t in discover()['tools'] if t['tool']==kind);local=item['selected']['version'] if item['selected'] else None
    if kind=='unity':
        data=fetch('https://services.api.unity.com/unity/editor/release/v1/releases?limit=1');latest=data['results'][0]['version'];source='https://unity.com/releases/editor/archive'
    else:
        # Stay on the installed LTS series, never silently switch Blender major versions.
        series='.'.join((local or '4.5').split('.')[:2]);source='https://download.blender.org/release/Blender'+series+'/'
        with urllib.request.urlopen(urllib.request.Request(source,headers={'User-Agent':'AssetForgeStudio/1'}),timeout=20) as response:html=response.read(1024*1024).decode()
        versions=re.findall(r'blender-(\d+\.\d+\.\d+)-windows-x64\.zip',html)
        if not versions:raise ValueError('No Windows portable release in the official series catalog')
        latest=max(versions,key=version)
    return dict(id=kind,name='Unity Editor' if kind=='unity' else 'Blender (installed series)',kind='tool',installed=local,latest=latest,status='not_installed' if not local else 'available' if version(local)<version(latest) else 'installed_ahead' if version(local)>version(latest) else 'current',source=source,automatic=False,license='Unity terms/account required' if kind=='unity' else 'GPL',reason='Editor activation is pinned to validated AFS import profiles; install through Unity Hub and validate separately.' if kind=='unity' else 'Keep the working Blender. A new build must pass geometry, animation and cinematic regression tests before switching.')

def check():
    with jobs.file_lock(store.DATA/'.update-check.lock'):
        save(status='checking',check_started_at=store.now(),error=None)
        from engines.concept_adapter import CONCEPT_ADAPTER
        hub=Path.home()/'Tools/trellis2/code/MODELS/hub'
        specs=[('ffmpeg',media_item,()),('blender',editor_item,('blender',)),('unity',editor_item,('unity',)),
            ('trellis2',model_item,('trellis2','TRELLIS.2','microsoft/TRELLIS.2-4B',hub/'models--microsoft--TRELLIS.2-4B/refs/main')),
            ('trellis_v1',model_item,('trellis_v1','TRELLIS v1','microsoft/TRELLIS-image-large',hub/'models--microsoft--TRELLIS-image-large/snapshots/25e0d31ffbebe4b5a97464dd851910efc3002d96')),
            ('hi3dgen',model_item,('hi3dgen','Hi3DGen geometry','Stable-X/trellis-normal-v0-1',store.WORKSPACE/'models/hi3dgen')),
            ('hi3dgen_normal',model_item,('hi3dgen_normal','Hi3DGen normal estimator','Stable-X/yoso-normal-v1-8-1',store.WORKSPACE/'models/hi3dgen_normal')),
            ('triposg',model_item,('triposg','TripoSG','VAST-AI/TripoSG',store.WORKSPACE/'models/triposg')),
            ('sdxl',model_item,('sdxl','SDXL concept','stabilityai/stable-diffusion-xl-base-1.0',CONCEPT_ADAPTER.weights())),
            ('trellis_v1_code',code_item,('trellis_v1_code','TRELLIS v1','microsoft/TRELLIS',store.WORKSPACE/'.local/engines/TRELLIS-v1')),
            ('hi3dgen_code',code_item,('hi3dgen_code','Hi3DGen','bytedance/Hi3DGen',store.WORKSPACE/'.local/engines/Hi3DGen')),
            ('triposg_code',code_item,('triposg_code','TripoSG','VAST-AI-Research/TripoSG',store.WORKSPACE/'.local/engines/TripoSG'))]
        items=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures=[(identifier,pool.submit(fn,*args)) for identifier,fn,args in specs]
            for identifier,future in futures:
                try:items.append(future.result())
                except Exception as exc:items.append(dict(id=identifier,name=identifier,status='check_failed',automatic=False,error=str(exc),reason='Could not verify upstream. This does not mean up to date.'))
        items.append(dict(id='unreal',name='Unreal Editor',kind='tool',status='manual',automatic=False,source='https://www.unrealengine.com/download',reason='Deferred by user. Epic account and terms required; no unattended installation or version check is claimed.'))
        save(items=items,status='checked',checked_at=store.now())
        if state()['policy'].get('auto_update_media'):
            media=next((i for i in items if i['id']=='ffmpeg' and i['status']=='available'),None)
            if media:enqueue_media(media)

def enqueue_media(item):
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute('SELECT * FROM jobs'):
            job=jobs.decode(row)
            if job['payload'].get('kind')=='tool_update' and job['status'] not in jobs.TERMINAL:return job
            if job['payload'].get('kind')=='tool_update' and job['status']=='REVIEW_REQUIRED' and job['payload']['candidate']['sha256']==item['candidate']['sha256'] and (state().get('active_media') or state().get('pending_media')):return job
        return jobs.enqueue(dict(kind='tool_update',engine='portable_ffmpeg',candidate=item['candidate'],timeout_seconds=1800,priority=-100),db=db)

def active_media():
    value=state().get('active_media')
    if not value:return None
    root=(store.DATA/'tools/ffmpeg').resolve()
    for name in ('ffmpeg','ffprobe'):
        p=Path(value[name]).resolve()
        if not p.is_relative_to(root) or not p.is_file() or store.digest(p)!=value['hashes'][name]:raise ValueError('Managed media tool missing or changed; restore a validated version in Settings > Updates')
    return {key:value[key] for key in ('ffmpeg','ffprobe')}

def activate(value):
    # Pinned queued scenes must not see their executable paths change either.
    with LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if any(json.loads(row['payload'])['kind']!='tool_update' and row['status'] not in jobs.TERMINAL for row in db.execute('SELECT status,payload FROM jobs')):return False
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(KEY,)).fetchone();saved=json.loads(row['payload']) if row else dict(policy=DEFAULTS.copy(),items=[])
        saved.update(active_media=value,previous_media=saved.get('active_media'),pending_media=None)
        db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(KEY,json.dumps(saved)))
    return True

def execute(job,folder,stop):
    candidate=job['payload']['candidate'];digest=candidate['sha256']
    if not re.fullmatch('[a-f0-9]{64}',digest) or not re.fullmatch(r'https://github\.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n\d+\.\d+-latest-win64-gpl-\d+\.\d+\.zip',candidate['url']):raise ValueError('Untrusted media release')
    target=store.DATA/'tools/ffmpeg'/digest;target.mkdir(parents=True,exist_ok=True)
    archive=target/'download.part';size=candidate['bytes']
    if not 0<size<512*1024**2:raise ValueError('Media download size outside supported limit')
    if shutil.disk_usage(target).free<size*5:raise ValueError('Insufficient disk for isolated tool update')
    def checkpoint():
        if stop.is_set() or jobs.get(job['id'])['status']=='CANCELLED':raise ValueError('Update interrupted. Existing tool remains active; Retry downloads this pinned release again.')
    with jobs.file_lock(store.DATA/'.media-install.lock'):
        request=urllib.request.Request(candidate['url'],headers={'User-Agent':'AssetForgeStudio/1'})
        with urllib.request.urlopen(request,timeout=30) as response,archive.open('wb') as output:
            received=0
            while chunk:=response.read(1024*1024):
                checkpoint();received+=len(chunk)
                if received>size:raise ValueError('Download exceeds declared size')
                output.write(chunk)
                (folder/'worker.log').write_text(f'STAGE Download FFmpeg {received}/{size} bytes',encoding='utf-8')
        if received!=size or store.digest(archive)!=digest:raise ValueError('Release SHA-256/size mismatch; current tool preserved')
        jobs.transition(job['id'],'GENERATED');jobs.transition(job['id'],'VALIDATING')
        with zipfile.ZipFile(archive) as z:
            if sum(i.file_size for i in z.infolist())>2*1024**3:raise ValueError('Unexpected archive expansion')
            for info in z.infolist():
                checkpoint();dest=(target/info.filename).resolve()
                if not dest.is_relative_to(target.resolve()) or '\\' in info.filename or (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Unsafe archive path')
                z.extract(info,target)
        paths={name:next(target.glob('*/bin/'+name+'.exe'),None) for name in ('ffmpeg','ffprobe')}
        if not all(paths.values()):raise ValueError('Portable FFmpeg/FFprobe pair missing')
        versions={key:command_version(path) for key,path in paths.items()}
        if versions['ffmpeg']!=versions['ffprobe']:raise ValueError('Mismatched media versions')
        probe=target/'technical-probe.mp4'
        # Explicit codec diagnostic, never registered as an asset or AI output.
        commands=[[str(paths['ffmpeg']),'-nostdin','-y','-v','error','-f','lavfi','-i','testsrc2=size=128x128:rate=12','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(probe)],
                  [str(paths['ffmpeg']),'-nostdin','-v','error','-xerror','-i',str(probe),'-f','null','-']]
        for command in commands:
            checkpoint();result=subprocess.run(command,capture_output=True,text=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if result.returncode:raise ValueError('Real H.264 encode/decode failed: '+result.stderr[-1000:])
        result=subprocess.run([str(paths['ffprobe']),'-v','error','-show_streams','-of','json',str(probe)],capture_output=True,text=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        stream=json.loads(result.stdout)['streams'][0]
        if stream['codec_name']!='h264' or stream['width']!=128 or int(stream['nb_frames'])!=12:raise ValueError('Codec probe failed contract')
        checkpoint();value={key:str(path.resolve()) for key,path in paths.items()}|dict(hashes={key:store.digest(path) for key,path in paths.items()},version=versions['ffmpeg'],archive_sha256=digest,validated_at=store.now(),qa='PASS_REAL_H264_ENCODE_PROBE_DECODE')
        (folder/'manifest.json').write_text(json.dumps(dict(status='validated',activation='See persistent active_media pointer',tool=value,scope='Codec compatibility only; no AI model quality claim'),indent=2),encoding='utf-8')
        archive.unlink(missing_ok=True);checkpoint()
        save(pending_media=value)
        if state()['policy'].get('auto_update_media'):activate(value)
        jobs.transition(job['id'],'REVIEW_REQUIRED')

def startup():
    value=state()
    if value.get('status')=='checking':value=save(status='interrupted',error='Previous release check was interrupted. Check again; current tools were preserved.')
    # First-run network use is explicit in Updates; later opted-in checks run daily.
    if not value.get('checked_at') or not value['policy'].get('auto_check'):return
    from datetime import datetime,timezone
    if (datetime.now(timezone.utc)-datetime.fromisoformat(value['checked_at'])).total_seconds()<86400:return
    def run():
        try:check()
        except Exception as exc:save(status='check_failed',error=str(exc))
    threading.Thread(target=run,daemon=True).start()

def tick():
    value=state()
    if value.get('pending_media') and value['policy'].get('auto_update_media'):activate(value['pending_media'])

@router.get('')
def inventory():
    value=state()
    maintenance=[j for j in jobs.listing() if j['payload']['kind']=='tool_update']
    # Recover a validated but not activated installation, including after restart.
    if value.get('pending_media') and value['policy'].get('auto_update_media'):
        if activate(value['pending_media']):value=state()
    value=json.loads(json.dumps(value))
    if value.get('active_media'):
        for item in value.get('items',[]):
            if item['id']=='ffmpeg':
                item['installed']=value['active_media']['version']
                if item.get('candidate',{}).get('sha256')==value['active_media']['archive_sha256']:item['status']='current'
    return value|dict(jobs=maintenance[:10])

@router.post('/check',status_code=202)
def request_check(background:BackgroundTasks):
    def run():
        try:check()
        except Exception as exc:save(status='check_failed',error=str(exc))
    if state().get('status')=='checking':return dict(status='checking')
    save(status='checking');background.add_task(run);return dict(status='checking')

class Policy(BaseModel):
    auto_check:bool=True
    auto_update_media:bool=True

@router.post('/policy')
def policy(body:Policy):return save(policy=body.model_dump())

@router.post('/install-media')
def install_media():
    item=next((i for i in state().get('items',[]) if i['id']=='ffmpeg' and i.get('candidate')),None)
    if not item:raise HTTPException(409,'Check official sources first; no verified media release is available')
    return enqueue_media(item)

@router.post('/activate-media')
def activate_media():
    value=state().get('pending_media')
    if not value:raise HTTPException(409,'No validated installation waiting')
    if not activate(value):raise HTTPException(409,'Queued/running production uses pinned tools. Finish or cancel it before activation.')
    return state()

@router.post('/rollback-media')
def rollback_media():
    with LOCK,store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if any(row['status'] not in jobs.TERMINAL for row in db.execute('SELECT status FROM jobs')):raise HTTPException(409,'Wait for queued/running work before rollback')
        row=db.execute('SELECT payload FROM drafts WHERE project_id=?',(KEY,)).fetchone()
        value=json.loads(row['payload']) if row else dict(policy=DEFAULTS.copy(),items=[])
        value.update(active_media=value.get('previous_media'),previous_media=value.get('active_media'),pending_media=None)
        # A rollback must not be undone automatically by the next daily check.
        value['policy']['auto_update_media']=False
        db.execute('INSERT OR REPLACE INTO drafts VALUES (?,?)',(KEY,json.dumps(value)))
    return state()
