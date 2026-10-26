"""One-click download and install of the local AI components (engines, weights, tools) with visible progress.

Every source is pinned (release asset digest, Hugging Face commit, Ollama model tag) and verified; downloads resume.
Nothing here starts GPU work. Components already present on this machine are detected, never re-downloaded.
"""
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import store

router = APIRouter(prefix='/api/components', tags=['components'])
HOME = Path.home()
TOOLS = HOME / 'Tools'
TRELLIS = TOOLS / 'trellis2'
BLENDER_DIR = TOOLS / 'blender-5.2.3-windows-x64'
KLEIN_DIR = HOME / 'Models/black-forest-labs__FLUX.2-klein-4B'
KLEIN_VENV = TOOLS / 'sdxl/venv'
OLLAMA_VERSION = 'v0.40.8'
USER_AGENT = {'User-Agent': 'AssetForgeStudio-installer'}
KLEIN_REPO, KLEIN_SHA = 'black-forest-labs/FLUX.2-klein-4B', 'e7b7dc27f91deacad38e78976d1f2b499d76a294'
KLEIN_PREFIXES = ('scheduler/', 'text_encoder/', 'tokenizer/', 'transformer/', 'vae/')
SOURCES = dict(
    blender=dict(url='https://download.blender.org/release/Blender5.2/blender-5.2.3-windows-x64.zip', sha256='723f08a4401502561eb763cdeacf8745b31e5f3f154d287d3830d97cf75dc2fb', size=405_839_452),
    ollama=dict(url=f'https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/ollama-windows-amd64.zip', sha256='04d1d43ac62c2deb0393307bb49fed7caf6b192de41bdd497aaa9488089d5552', size=1_582_537_058),
    trellis=dict(url='https://github.com/IgorAherne/TRELLIS.2-stableprojectorz/releases/download/latest/trellis2-stableprojectorz_v22.zip', sha256='62be7caefaf12e396763dfec4b5e688fdd83c9450920090dfdb8082bd43811be', size=771_937_588))
MODEL = 'qwen3.6:35b'

# id, name, what it is, approximate download bytes (for the progress weighting), prerequisites
COMPONENTS = [
    ('blender', 'Blender 5.2.3', 'Scale, checks, previews and GLB export', 405_839_452, ()),
    ('klein_env', 'Concept engine environment', 'Python environment for FLUX.2 klein', 4_000_000_000, ('trellis_bundle',)),
    ('ollama', 'Local language runtime', 'Ollama, loopback only', 1_582_537_058, ()),
    ('trellis_bundle', 'TRELLIS.2 package', 'Engine code and portable Python', 771_937_588, ()),
    ('trellis_env', 'TRELLIS.2 engine and weights', 'PyTorch, extensions, TRELLIS.2 4B weights (MIT)', 24_000_000_000, ('trellis_bundle',)),
    ('qwen', 'Language and vision model', 'Qwen3.6 35B: reads prompts and checks results', 24_000_000_000, ('ollama',)),
    ('klein_weights', 'FLUX.2 klein 4B weights', 'Concept images (Apache-2.0)', 14_900_000_000, ()),
]
INFO = {c[0]: c for c in COMPONENTS}
# What the user wants to create -> the components it needs. note = something this app cannot install for them.
FEATURES = [
    dict(id='sprites', name='2D sprites and concept images', needs=['klein_env', 'klein_weights', 'ollama', 'qwen'], note=''),
    dict(id='models', name='3D models (single and batch)', needs=['klein_env', 'klein_weights', 'ollama', 'qwen', 'trellis_bundle', 'trellis_env', 'blender'], note=''),
    dict(id='effects', name='Effects (fire, smoke, slashes)', needs=['blender'], note='Slash and mesh effects also need Unity Editor, which you install yourself.'),
    dict(id='map', name='Maps and worlds', needs=[], note='Needs Unity Editor, which you install yourself. No AI download.'),
    dict(id='video', name='Video and cinematics', needs=['blender'], note=''),
    dict(id='motion', name='Motion and rigging', needs=None, note='Not downloadable from the app yet.'),
]
_lock = threading.Lock()
_state = {c[0]: dict(status='unknown', done=0, text='', error='') for c in COMPONENTS}
_session = dict(running=False, stop=threading.Event(), started=None, bytes_done=0, error='')


class Cancelled(Exception):
    pass


def present(identifier):
    """Real on-disk probes, so machines set up by hand or by the old package count as installed."""
    try:
        if identifier == 'blender': return (BLENDER_DIR / 'blender.exe').is_file()
        if identifier == 'ollama': return (TOOLS / f'afs-ollama/{OLLAMA_VERSION}/ollama.exe').is_file()
        if identifier == 'qwen': return (TOOLS / 'afs-ollama/models/manifests/registry.ollama.ai/library/qwen3.6/35b').is_file()
        if identifier == 'trellis_bundle': return (TRELLIS / 'code/install.py').is_file() and (TRELLIS / 'tools/python/python.exe').is_file()
        if identifier == 'trellis_env':
            code = TRELLIS / 'code'
            return ((code / 'venv/Scripts/python.exe').is_file() and (code / 'MODELS/hub/models--microsoft--TRELLIS.2-4B/refs/main').is_file()
                    and (code / 'MODELS/dinov3/model.safetensors').is_file() and (code / 'MODELS/RMBG-2.0/model.safetensors').is_file())
        if identifier == 'klein_env': return (KLEIN_VENV / 'Scripts/python.exe').is_file() and (KLEIN_VENV / 'Lib/site-packages/diffusers').is_dir()
        if identifier == 'klein_weights':
            return all((KLEIN_DIR / p).is_file() for p in ('model_index.json', 'vae/diffusion_pytorch_model.safetensors', 'transformer/diffusion_pytorch_model.safetensors', 'text_encoder/model-00002-of-00002.safetensors'))
    except OSError: pass
    return False


# ---------------------------------------------------------------- download helpers
def _open(url, start=0):
    request = urllib.request.Request(url, headers=USER_AGENT | ({'Range': f'bytes={start}-'} if start else {}))
    return urllib.request.urlopen(request, timeout=60)


def download(url, target, sha256=None, size=None, report=None, stop=None):
    """Resumable download to `target`; verifies size and SHA-256 before the file appears under its final name."""
    target = Path(target)
    if target.is_file() and (size is None or target.stat().st_size == size):
        if sha256 is None or sha256_file(target) == sha256: return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + '.part')
    for attempt in range(6):
        have = part.stat().st_size if part.exists() else 0
        try:
            with _open(url, have) as response:
                if have and response.status != 206: have = 0
                total = have + int(response.headers.get('Content-Length') or 0)
                with part.open('ab' if have else 'wb') as out:
                    while True:
                        if stop is not None and stop.is_set(): raise Cancelled()
                        chunk = response.read(1 << 20)
                        if not chunk: break
                        out.write(chunk); have += len(chunk)
                        if report: report(len(chunk))
            if size is not None and part.stat().st_size != size: raise OSError(f'size {part.stat().st_size} != {size}')
            break
        except Cancelled: raise
        except urllib.error.HTTPError as error:
            if error.code == 416 and have: break  # the partial file is already complete; verify it below
            if attempt == 5: raise OSError(f'Download failed: {url}: {error}')
            time.sleep(3 * (attempt + 1))
        except OSError as error:
            if attempt == 5: raise OSError(f'Download failed: {url}: {error}')
            time.sleep(3 * (attempt + 1))
    if sha256 and sha256_file(part) != sha256:
        part.unlink(missing_ok=True)
        raise OSError(f'Checksum mismatch for {target.name}; the file was removed. Try again.')
    os.replace(part, target)
    return target


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 22), b''): digest.update(block)
    return digest.hexdigest()


def extract(archive, destination, strip=None, stop=None):
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if stop is not None and stop.is_set(): raise Cancelled()
            name = info.filename
            if strip and name.startswith(strip): name = name[len(strip):]
            if not name: continue
            target = (destination / name).resolve()
            if destination not in target.parents and target != destination: raise OSError(f'Unsafe path in archive: {info.filename}')
            if info.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, open(target, 'wb') as out: shutil.copyfileobj(source, out, 1 << 20)


def top_folder(archive):
    with zipfile.ZipFile(archive) as bundle:
        tops = {n.split('/')[0] for n in bundle.namelist() if n}
        return (next(iter(tops)) + '/') if len(tops) == 1 else None


def run_stream(command, cwd, env, log, stop, text):
    """Run a vendor installer, streaming its last line as visible progress; killable."""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    def watch():
        while process.poll() is None:
            if stop.is_set(): subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], capture_output=True); return
            time.sleep(1)
    threading.Thread(target=watch, daemon=True).start()
    with log.open('a', encoding='utf-8') as out:
        for line in process.stdout:
            out.write(line); line = line.strip()
            if line: text(line[:160])
    code = process.wait()
    if stop.is_set(): raise Cancelled()
    if code: raise OSError(f'Installer exited with code {code}; see {log}')


# ---------------------------------------------------------------- installers
def _set(identifier, **values):
    with _lock: _state[identifier].update(values)


def _report(identifier):
    def add(n):
        with _lock:
            _state[identifier]['done'] += n
            _session['bytes_done'] += n
    return add


def _archive(identifier, key, destination, extract_to, strip_top=True):
    source, stop = SOURCES[key], _session['stop']
    downloads = TOOLS / '_downloads'
    _set(identifier, text='Downloading', done=0)
    archive = download(source['url'], downloads / Path(source['url']).name, source['sha256'], source['size'], _report(identifier), stop)
    _set(identifier, text='Unpacking')
    extract(archive, extract_to, top_folder(archive) if strip_top else None, stop)
    archive.unlink(missing_ok=True)


def install_blender():
    _archive('blender', 'blender', BLENDER_DIR, BLENDER_DIR)


def install_ollama():
    _archive('ollama', 'ollama', None, TOOLS / f'afs-ollama/{OLLAMA_VERSION}', strip_top=False)


def install_trellis_bundle():
    _archive('trellis_bundle', 'trellis', None, TRELLIS)


def install_trellis_env():
    stop = _session['stop']
    code, tools = TRELLIS / 'code', TRELLIS / 'tools'
    env = os.environ.copy(); env['HF_HOME'] = str(code / 'models')
    script = TRELLIS / '_afs_install.bat'
    script.write_text('@echo off\r\ncall "%~dp0tools\\environment.bat"\r\ncd /d "%~dp0code"\r\n%PYTHON% -m pip install --upgrade pip\r\n%PYTHON% install.py\r\nexit /b %ERRORLEVEL%\r\n', encoding='ascii')
    _set('trellis_env', text='Preparing the engine (this runs the vendor installer)')
    log = store.DATA / 'component-logs' / 'trellis_env.log'; log.parent.mkdir(parents=True, exist_ok=True)
    run_stream(['cmd', '/c', str(script)], str(TRELLIS), env, log, stop, lambda t: _set('trellis_env', text=t))
    if not present('trellis_env'): raise OSError(f'TRELLIS.2 setup finished but files are missing; see {log}')
    (code / 'trellis2_init_done.txt').write_text('Trellis.2 Init Complete\n')
    script.unlink(missing_ok=True)


def install_klein_env():
    stop = _session['stop']
    python = TRELLIS / 'tools/python/python.exe'
    log = store.DATA / 'component-logs' / 'klein_env.log'; log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy(); env['SETUPTOOLS_USE_DISTUTILS'] = 'stdlib'
    freeze = Path(os.environ.get('AFS_RESOURCE_ROOT', store.ROOT)) / 'components/klein-freeze.txt'
    if not (KLEIN_VENV / 'Scripts/python.exe').is_file():
        _set('klein_env', text='Creating the environment')
        run_stream([str(python), '-m', 'pip', 'install', 'virtualenv'], str(TRELLIS), env, log, stop, lambda t: _set('klein_env', text=t))
        run_stream([str(python), '-m', 'virtualenv', str(KLEIN_VENV)], str(TRELLIS), env, log, stop, lambda t: _set('klein_env', text=t))
    run_stream([str(KLEIN_VENV / 'Scripts/python.exe'), '-m', 'pip', 'install', '--no-input', '-r', str(freeze), '--extra-index-url', 'https://download.pytorch.org/whl/cu128'],
               str(TRELLIS), env, log, stop, lambda t: _set('klein_env', text=t))


def install_klein_weights():
    stop = _session['stop']
    _set('klein_weights', text='Reading the file list')
    listing = json.load(_open(f'https://huggingface.co/api/models/{KLEIN_REPO}/tree/{KLEIN_SHA}?recursive=1'))
    files = [f for f in listing if f['type'] == 'file' and (f['path'] == 'model_index.json' or f['path'].startswith(KLEIN_PREFIXES))]
    for f in files:
        _set('klein_weights', text=f['path'])
        oid = (f.get('lfs') or {}).get('oid')
        download(f'https://huggingface.co/{KLEIN_REPO}/resolve/{KLEIN_SHA}/{f["path"]}', KLEIN_DIR / f['path'], oid, f['size'], _report('klein_weights'), stop)


def install_qwen():
    stop = _session['stop']
    exe = TOOLS / f'afs-ollama/{OLLAMA_VERSION}/ollama.exe'; models = TOOLS / 'afs-ollama/models'
    # A private server on its own port, so another Ollama on the usual port can never receive (or satisfy) the download.
    port = 11437
    env = os.environ.copy(); env.update(OLLAMA_HOST=f'127.0.0.1:{port}', OLLAMA_MODELS=str(models), OLLAMA_NO_CLOUD='1')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def up():
        try: return bool(json.load(opener.open(f'http://127.0.0.1:{port}/api/version', timeout=1)).get('version'))
        except (OSError, ValueError): return False
    if up(): raise OSError(f'Port {port} is already in use; close the other program and try again')
    own = subprocess.Popen([str(exe), 'serve'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    for _ in range(60):
        if up(): break
        time.sleep(.5)
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{port}/api/pull', data=json.dumps(dict(model=MODEL, stream=True)).encode(), headers={'Content-Type': 'application/json'})
        seen = {}
        with opener.open(request, timeout=3600) as response:
            for line in response:
                if stop.is_set(): raise Cancelled()
                item = json.loads(line)
                if item.get('error'): raise OSError(item['error'])
                digest, completed = item.get('digest') or '', item.get('completed') or 0
                if digest and completed:
                    delta = max(0, completed - seen.get(digest, 0)); seen[digest] = completed
                    with _lock:
                        _session['bytes_done'] += delta; _state['qwen']['done'] += delta
                _set('qwen', text=item.get('status', ''))
    finally:
        if own.poll() is None: own.terminate()
    if not present('qwen'): raise OSError('Model download finished but the manifest is missing')


INSTALLERS = dict(blender=install_blender, ollama=install_ollama, trellis_bundle=install_trellis_bundle, trellis_env=install_trellis_env,
                  klein_env=install_klein_env, klein_weights=install_klein_weights, qwen=install_qwen)


def _ordered(ids):
    order, seen = [], set()
    def visit(i):
        if i in seen: return
        seen.add(i)
        for need in INFO[i][4]: visit(need)
        order.append(i)
    for i in ids: visit(i)
    return order


def _run(ids):
    stop = _session['stop']
    try:
        for identifier in _ordered(ids):
            if present(identifier): _set(identifier, status='installed', text='', error=''); continue
            _set(identifier, status='running', done=0, error='', text='Starting')
            try:
                INSTALLERS[identifier]()
            except Cancelled:
                _set(identifier, status='cancelled', text='Stopped; the next start continues where it left off'); raise
            except Exception as error:
                _set(identifier, status='failed', error=str(error)[:400], text='')
                _session['error'] = f'{INFO[identifier][1]}: {error}'[:500]
                continue
            _set(identifier, status='installed' if present(identifier) else 'failed', text='', error='' if present(identifier) else 'Finished but files are missing')
    except Cancelled: pass
    finally:
        _session['running'] = False


def listing():
    free = shutil.disk_usage(HOME).free if HOME.exists() else 0
    rows = []
    for identifier, name, what, size, needs in COMPONENTS:
        with _lock: row = dict(_state[identifier])
        if row['status'] not in ('running', 'cancelled', 'failed'): row['status'] = 'installed' if present(identifier) else ('queued' if _session['running'] and row['status'] == 'queued' else 'missing')
        rows.append(dict(id=identifier, name=name, what=what, bytes=size, requires=list(needs), status=row['status'], text=row['text'], error=row['error'],
                         progress=(min(1.0, row['done'] / size) if row['status'] == 'running' and row['done'] else None)))
    missing = sum(r['bytes'] for r in rows if r['status'] != 'installed')
    sizes = {r['id']: r['bytes'] for r in rows}; have = {r['id'] for r in rows if r['status'] == 'installed'}
    features = [dict(id=f['id'], name=f['name'], note=f['note'], available=f['needs'] is not None, needs=f['needs'] or [],
                     missing_bytes=sum(sizes[n] for n in (f['needs'] or []) if n not in have), ready=f['needs'] is not None and all(n in have for n in f['needs'])) for f in FEATURES]
    return dict(components=rows, features=features, running=_session['running'], error=_session['error'], bytes_done=_session['bytes_done'], missing_bytes=missing,
                free_bytes=free, enough_space=free > missing * 1.1 + 5 * 2**30, all_installed=all(r['status'] == 'installed' for r in rows))


class InstallRequest(BaseModel):
    ids: list[str] | None = None


@router.get('')
def inventory():
    return listing()


@router.post('/install', status_code=202)
def install(body: InstallRequest):
    ids = body.ids or [c[0] for c in COMPONENTS]
    if any(i not in INFO for i in ids): raise HTTPException(400, 'Unknown component')
    with _lock:
        if _session['running']: raise HTTPException(409, 'An installation is already running')
        todo = [i for i in _ordered(ids) if not present(i)]
        if not todo: return listing()
        need = sum(INFO[i][3] for i in todo)
        if shutil.disk_usage(HOME).free < need * 1.1 + 5 * 2**30: raise HTTPException(409, f'Not enough free disk space: about {need // 2**30 + 5} GB needed on the drive that holds your user folder')
        _session.update(running=True, error='', bytes_done=0, started=time.time()); _session['stop'].clear()
        for i in todo: _state[i].update(status='queued', done=0, text='Waiting', error='')
    threading.Thread(target=_run, args=(ids,), daemon=True).start()
    return listing()


@router.post('/cancel')
def cancel():
    _session['stop'].set()
    return dict(cancelling=_session['running'])
