"""Replay the actually failed Editor stage, retaining the completed FBX and failed log."""
import json,os,sys,time,subprocess,sqlite3,shutil
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'.local/unity-startup-recovery'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');RUN.mkdir(parents=True)
sys.path.insert(0,str(ROOT))
from apps.api import jobs,store
from engines import unity_animation
from engines.editor_recovery import prepare_retry
library=Path.home()/'AppData/Local/Temp/pytest-of-Winka/pytest-241/test_real_single_clip_unity_pa0'
store.DATA=library.resolve()
db=sqlite3.connect('file:'+str(library/'studio.sqlite')+'?mode=ro',uri=True)
identifier,status,payload=next(row for row in db.execute('SELECT id,status,payload FROM jobs') if json.loads(row[2]).get('engine')=='unity_animation');payload=json.loads(payload)
assert status=='FAILED';folder=library/'jobs'/identifier
editor=payload['effective_config']['editor'] if 'editor' in payload['effective_config'] else unity_animation.probe()['editor']
project=folder/'editor_project';clean=folder/'clean_project'
if not clean.is_dir():clean=folder/'clean_import_project'
assert project.is_dir() and clean.is_dir()
fbx=folder/'output/Animation.fbx';source_hash=store.digest(fbx)
command=lambda location,method,log:[editor,'-batchmode','-nographics','-projectPath',str(location),*(['-quit'] if method!='CleanImport' else []),'-executeMethod','AssetForgeAnimation.'+method,'-logFile',str(folder/log)]
commands=[(command(project,'Run','unity.log'),'animation_native_import'),(command(project,'Reopen','unity_reopen.log'),'animation_cold_reopen'),(command(clean,'CleanImport','unity_clean.log'),'animation_clean_package_import')]
started=time.monotonic();report=dict(status='RUNNING',run=str(RUN),original_job=identifier,original_status=status,fbx_sha256=source_hash,scope='Real failed UPM IPC log and real Editor relaunch/cold reopen/clean package import; completed Blender FBX is reused. Original failed SQL job is not relabeled successful.')
try:
    assert prepare_retry(folder,*commands[0]);shutil.copyfile(folder/'editor_startup_recovery.json',RUN/'editor_startup_recovery.json')
    with jobs.resource_slot('cpu'):
        for args,stage in commands:
            result=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,timeout=300)
            assert result.returncode==0,stage
    validation=unity_animation.validate(payload,folder);assert store.digest(fbx)==source_hash
    report.update(status='VERIFIED_REAL_EDITOR_STAGE_RELAUNCH',validation=validation,recovery=json.loads((RUN/'editor_startup_recovery.json').read_text('utf-8')),fbx_preserved=True)
except Exception as exc:
    report.update(status='FAILED',error=str(exc));raise
finally:
    report['seconds']=time.monotonic()-started;(RUN/'report.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(dict(status=report['status'],run=str(RUN))),flush=True)
