"""Controlled planned-RAM claim for native negative admission tests; allocates no model."""
import json,os,sys,threading,time,uuid
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from apps.api import jobs,host_resources as host
folder=Path(sys.argv[1]).resolve();folder.mkdir(parents=True,exist_ok=True)
ledger=jobs.LOCK_ROOT/'host-ram';ledger.mkdir(parents=True,exist_ok=True)
path=ledger/('native-admission-test-'+uuid.uuid4().hex+'.json')
try:
    with jobs.file_lock(jobs.LOCK_ROOT/'ram-admission.lock'):
        amount=max(host.GIB,psutil.virtual_memory().available-6*host.GIB)
        value=dict(schema_version=1,job_id='native-negative-admission-test',job_folder=str(folder),resource='cpu',owner_pid=os.getpid(),owner_created=psutil.Process().create_time(),owner_thread=threading.get_native_id(),reserved_at=time.time(),allowance_bytes=amount,purpose='Controlled pending RAM reservation; no running model or successful output is simulated')
        temporary=path.with_suffix('.part');temporary.write_text(json.dumps(value),'utf-8');temporary.replace(path)
    print(json.dumps(dict(ready=True,path=str(path),claim=value)),flush=True)
    sys.stdin.readline()
finally:path.unlink(missing_ok=True)
