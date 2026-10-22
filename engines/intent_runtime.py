"""Owned portable loopback Ollama runtime. No installation/download on application start."""
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

MODEL='qwen3-vl:4b-instruct-q4_K_M'
HOME=Path.home()/'Tools/afs-ollama'
EXECUTABLE=HOME/'v0.40.8/ollama.exe'
MODELS=HOME/'models'
_lock=threading.Lock()
_process=None


def installed():
    return EXECUTABLE.is_file() and (MODELS/'manifests/registry.ollama.ai/library/qwen3-vl/4b-instruct-q4_K_M').is_file()


def ping():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:11434/api/version',timeout=1) as response:return bool(json.load(response).get('version'))
    except (OSError,ValueError):return False


def ensure():
    global _process
    if not installed():return False
    if ping():return True
    with _lock:
        if ping():return True
        from apps.api import jobs
        try:
            with jobs.file_lock(jobs.LOCK_ROOT/'intent-runtime-start.lock'):
                if ping():return True
                HOME.mkdir(parents=True,exist_ok=True)
                environment=os.environ.copy()
                environment.update(OLLAMA_HOST='127.0.0.1:11434',OLLAMA_MODELS=str(MODELS),OLLAMA_NO_CLOUD='1',
                    OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_KEEP_ALIVE='0',OLLAMA_CONTEXT_LENGTH='8192',
                    CUDA_VISIBLE_DEVICES='-1',GGML_VK_VISIBLE_DEVICES='-1')
                with (HOME/'server.log').open('ab') as log:
                    _process=subprocess.Popen([str(EXECUTABLE),'serve'],env=environment,stdout=log,stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for _ in range(30):
                    if ping():return True
                    if _process.poll() is not None:return False
                    time.sleep(.1)
        except OSError:return ping()
    return False


def close():
    global _process
    if _process and _process.poll() is None:
        _process.terminate()
        try:_process.wait(timeout=5)
        except subprocess.TimeoutExpired:_process.kill()
    _process=None
