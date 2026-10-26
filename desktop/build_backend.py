"""Package only the lightweight API runtime; engine environments/weights stay external."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build():
    build_root = ROOT / '.local/desktop-build'
    source_roots = ['apps/api', 'engines', 'components', 'scripts', 'pipelines', 'presets', 'schemas', 'integrations/unity', 'apps/web/dist']
    def source_signature():
        included = []
        for folder in source_roots:
            included.extend(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix in {'.py', '.json', '.txt', '.patch', '.js', '.css', '.html', '.cs', '.asmdef', '.shader', '.hlsl'})
        included += [ROOT / 'desktop/backend_entry.py', Path(__file__), ROOT / 'benchmarks/archer_tower_t3/benchmark.json']
        digest = hashlib.sha256()
        for path in sorted(included): digest.update(path.relative_to(ROOT).as_posix().encode()); digest.update(path.read_bytes())
        return digest.hexdigest()
    signature = source_signature()
    destination = ROOT / 'src-tauri/binaries/afs-backend-x86_64-pc-windows-msvc.exe'
    metadata = build_root / 'backend-build.json'
    cached=json.loads(metadata.read_text()) if metadata.is_file() else {}
    if destination.is_file() and cached.get('source_sha256') == signature and cached.get('file_sha256') == hashlib.sha256(destination.read_bytes()).hexdigest():
        print('PACKAGED_BACKEND_CACHE_VERIFIED', flush=True); return
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--name', 'afs-backend',
            '--distpath', str(build_root / 'sidecar'), '--workpath', str(build_root / 'pyinstaller'), '--specpath', str(build_root),
            '--paths', str(ROOT), '--collect-submodules', 'apps.api', '--hidden-import', 'engines.adapters',
            '--hidden-import', 'uvicorn.protocols.http.h11_impl', '--hidden-import', 'uvicorn.loops.asyncio', '--hidden-import', 'uvicorn.lifespan.on']
    for folder in source_roots:
        args += ['--add-data', f'{ROOT / folder};{folder}']
    args += ['--add-data', f'{ROOT / "benchmarks/archer_tower_t3/benchmark.json"};benchmarks/archer_tower_t3', str(ROOT / 'desktop/backend_entry.py')]
    result = subprocess.run(args, cwd=ROOT)
    if result.returncode: raise SystemExit(result.returncode)
    if source_signature()!=signature:raise RuntimeError('Source/frontend changed during packaging; retry from a consistent source snapshot')
    shutil.copyfile(build_root / 'sidecar/afs-backend.exe', destination)
    metadata.write_text(json.dumps({'source_sha256': signature, 'file_sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
                                    'bytes': destination.stat().st_size, 'build_type': 'Bundled Python API; external AI environments/weights and Blender required'}, indent=2))
    print('PACKAGED_BACKEND_BUILT', destination.stat().st_size, flush=True)


if __name__ == '__main__': build()
