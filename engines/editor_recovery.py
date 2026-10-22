"""One bounded relaunch for an observed Unity Package Manager IPC startup failure."""
import json
import re
import shutil
from pathlib import Path
from apps.api import store
from .quality import fingerprint


def prepare_retry(folder,command,stage):
    if '-logFile' not in command:return False
    folder=Path(folder).resolve();log=Path(command[command.index('-logFile')+1]).resolve()
    if not log.is_relative_to(folder) or not log.is_file():return False
    text=log.read_text('utf-8',errors='replace').lower()
    if not ('ipc stream failed to read (not connected)' in text and 'failed to resolve packages: operation cancelled' in text):return False
    if re.search(r'error cs\d{4}|license.*(?:failed|invalid|denied|expired)|out of memory|disk full',text):return False
    receipt=folder/'editor_startup_recovery.json';history=json.loads(receipt.read_text('utf-8')) if receipt.exists() else []
    if any(record['stage']==stage for record in history):return False
    name=re.sub(r'[^a-zA-Z0-9_-]','_',stage)
    archive=folder/(name+'.failed_startup.log')
    if archive.exists():return False
    shutil.copyfile(log,archive)
    history.append(dict(stage=stage,root_cause='UNITY_UPM_IPC_DISCONNECTED',action='relaunch_same_editor_stage_once',
        command_sha256=fingerprint(command),failed_log=archive.name,failed_log_sha256=store.digest(archive),at=store.now(),
        policy='One startup relaunch only; no source regeneration, quality change or retry of license/compiler/content errors'))
    temporary=receipt.with_suffix('.part');temporary.write_text(json.dumps(history,indent=2),'utf-8');temporary.replace(receipt)
    return True
