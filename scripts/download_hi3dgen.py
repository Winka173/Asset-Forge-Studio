"""User-authorized, pinned Hi3DGen/YOSO HTTPS downloads; no inference or auto-install.

Large files use exact bounded ranges, resume completed parts, then verify the HF
LFS SHA-256 before replacing the destination. Existing Tool caches are read only.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 32 * 1024 * 1024
EVIDENCE = ROOT / 'docs/evidence/hi3dgen_downloads.json'
CACHE = Path('C:/Users/Winka/Tools/trellis2/code/MODELS/hub/models--microsoft--TRELLIS-image-large/snapshots/25e0d31ffbebe4b5a97464dd851910efc3002d96')


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(4 * 1024 * 1024):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-download', action='store_true')
    args = parser.parse_args()
    if not args.authorized_download:
        raise SystemExit('Explicit user download authorization required')
    sources = json.loads((ROOT / 'docs/evidence/engine_sources.json').read_text('utf-8'))['engines']
    result = json.loads(EVIDENCE.read_text('utf-8')) if EVIDENCE.exists() else {'engines': {}, 'network_failures': []}
    result['recorded_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    normal_code = ROOT / '.local/engines/StableNormal'
    license_path = normal_code / 'LICENSE.txt'
    license_text = license_path.read_text('utf-8')
    if 'Apache License' not in license_text or 'Version 2.0' not in license_text:
        raise RuntimeError('StableNormal license verification failed')
    result['normal_code'] = {'repo': 'https://github.com/hugoycj/StableNormal',
                             'revision': subprocess.check_output(['git', '-C', str(normal_code), 'rev-parse', 'HEAD'], text=True).strip(),
                             'license': 'Apache-2.0', 'license_sha256': sha256(license_path),
                             'license_source': 'https://github.com/hugoycj/StableNormal/blob/1b7203c988384cb62286a25865d7354be8fdbbf7/LICENSE.txt',
                             'installed': False}
    lock = threading.Lock()

    def save():
        EVIDENCE.write_text(json.dumps(result, indent=2), encoding='utf-8')

    for identifier, expected_license in [('hi3dgen', 'mit'), ('hi3dgen_normal', 'apache-2.0')]:
        source = sources[identifier]
        revision = source['model_revision']
        repo = source['model'].removeprefix('https://huggingface.co/')
        with urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true', timeout=30) as response:
            metadata = json.load(response)
        if metadata['sha'] != revision or metadata.get('cardData', {}).get('license') != expected_license or metadata.get('gated'):
            raise RuntimeError('Pinned revision/license/access audit mismatch')
        row = result['engines'].setdefault(identifier, {})
        row.update(repo=source['model'], revision=revision, license_metadata=expected_license,
                   status='DOWNLOADING', path=str(ROOT / 'models' / identifier), inference='NOT_TESTED')
        completed = {entry['name']: entry for entry in row.get('files', [])}
        save()
        for item in metadata['siblings']:
            name = item['rfilename']
            if name == '.gitattributes':
                continue
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise RuntimeError('Unsafe remote path')
            target = ROOT / 'models' / identifier / name
            target.parent.mkdir(parents=True, exist_ok=True)
            expected = item.get('lfs', {}).get('sha256')
            size = item['size']
            transfer = 'official HF HTTPS bounded range' if expected else 'official HF HTTPS'
            if target.exists() and target.stat().st_size == size and (not expected or sha256(target) == expected):
                transfer = completed.get(name, {}).get('transport', 'existing destination verified')
            elif expected and (CACHE / name).is_file() and (CACHE / name).stat().st_size == size and sha256(CACHE / name) == expected:
                shutil.copyfile(CACHE / name, target)
                transfer = 'copied independent file from read-only TRELLIS v1 cache after remote LFS SHA-256 match'
            elif expected:
                parts = ROOT / '.local/downloads' / identifier / hashlib.sha256(name.encode()).hexdigest()[:16]
                parts.mkdir(parents=True, exist_ok=True)
                count = (size + CHUNK - 1) // CHUNK

                def download_part(index):
                    start = index * CHUNK
                    end = min(size, start + CHUNK) - 1
                    destination = parts / f'{index:04d}.part'
                    if destination.exists() and destination.stat().st_size == end - start + 1:
                        return
                    for attempt in range(5):
                        try:
                            query = urllib.parse.urlencode({'download': 'true', 'afs_range': f'{index}_{time.time_ns()}'})
                            request = urllib.request.Request(f'https://huggingface.co/{repo}/resolve/{revision}/{name}?{query}',
                                                             headers={'Range': f'bytes={start}-{end}'})
                            with urllib.request.urlopen(request, timeout=30) as response, destination.with_suffix('.tmp').open('wb') as stream:
                                if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                                    raise ValueError('Server did not honor exact requested range')
                                while block := response.read(1024 * 1024):
                                    stream.write(block)
                            if destination.with_suffix('.tmp').stat().st_size != end - start + 1:
                                raise ValueError('Incomplete range')
                            os.replace(destination.with_suffix('.tmp'), destination)
                            return
                        except Exception as exc:
                            # Never persist exception strings containing signed URLs or tokens.
                            with lock:
                                result['network_failures'].append({'engine': identifier, 'file': name, 'range': index,
                                                                   'attempt': attempt + 1, 'exception_type': type(exc).__name__})
                                save()
                            if attempt == 4:
                                raise RuntimeError(f'{identifier}/{name}: range {index} failed; rerun resumes saved ranges') from None
                            time.sleep(min(2 ** attempt, 8))

                print(f'DOWNLOAD {identifier}/{name} bytes={size} ranges={count}', flush=True)
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [pool.submit(download_part, index) for index in range(count)]
                    for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
                        future.result()
                        if done % 8 == 0 or done == count:
                            print(f'RANGES {identifier}/{name} {done}/{count}', flush=True)
                temporary = target.with_suffix('.verified-download')
                with temporary.open('wb') as stream:
                    for index in range(count):
                        with (parts / f'{index:04d}.part').open('rb') as part:
                            shutil.copyfileobj(part, stream, 4 * 1024 * 1024)
                if sha256(temporary) != expected:
                    raise RuntimeError('LFS SHA-256 verification failed; destination not installed')
                os.replace(temporary, target)
            else:
                url = f'https://huggingface.co/{repo}/resolve/{revision}/{name}'
                with urllib.request.urlopen(url, timeout=30) as response:
                    body = response.read()
                if len(body) != size:
                    raise RuntimeError('Small-file size mismatch')
                if hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest() != item['blobId']:
                    raise RuntimeError('Pinned Git blob mismatch')
                target.write_bytes(body)
            digest = sha256(target)
            if expected and digest != expected:
                raise RuntimeError('Final destination LFS SHA-256 mismatch')
            if not expected:
                body = target.read_bytes()
                if hashlib.sha1(f'blob {len(body)}\0'.encode() + body).hexdigest() != item['blobId']:
                    raise RuntimeError('Final destination pinned Git blob mismatch')
            completed[name] = {'name': name, 'bytes': target.stat().st_size, 'sha256': digest,
                               'remote_lfs_sha256': expected, 'remote_git_blob': item.get('blobId'), 'transport': transfer}
            row['files'] = list(completed.values())
            save()
            print(f'VERIFIED {identifier}/{name} bytes={size}', flush=True)
        row['status'] = 'DOWNLOADED_SHA256_VERIFIED'
        row['downloaded_bytes'] = sum(entry['bytes'] for entry in row['files'])
        row['cache_reuse_bytes'] = sum(entry['bytes'] for entry in row['files'] if entry['transport'].startswith('copied independent'))
        row['verified_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save()
    print('ALL_AUTHORIZED_WEIGHTS_VERIFIED', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if EVIDENCE.exists():
            result = json.loads(EVIDENCE.read_text('utf-8'))
            for row in result.get('engines', {}).values():
                if row.get('status') == 'DOWNLOADING':
                    row.update(status='DOWNLOAD_FAILED_RESUMABLE', exception_type=type(exc).__name__)
            EVIDENCE.write_text(json.dumps(result, indent=2), encoding='utf-8')
        raise
