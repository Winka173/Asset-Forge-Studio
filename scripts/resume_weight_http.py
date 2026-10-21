"""Authorized Hugging Face fallback: bounded range requests, pinned revision, SHA-256 verification."""
import concurrent.futures
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = '2c1c516d22d58db486a058d98d31bb6177344e06'
NAME = 'transformer/diffusion_pytorch_model.safetensors'
CHUNK = 32 * 1024 * 1024


def main():
    info_url = f'https://huggingface.co/api/models/VAST-AI/TripoSG/revision/{REVISION}?blobs=true'
    with urllib.request.urlopen(info_url, timeout=30) as r: info = json.load(r)
    metadata = next(f for f in info['siblings'] if f['rfilename'] == NAME)
    size = metadata['size']; expected = metadata['lfs']['sha256']
    target = ROOT / 'models/triposg' / NAME
    part_root = ROOT / '.local/downloads/triposg_transformer'; part_root.mkdir(parents=True, exist_ok=True)
    count = (size + CHUNK - 1) // CHUNK
    print(f'OFFICIAL_RANGE_DOWNLOAD bytes={size} chunks={count} sha256={expected}', flush=True)
    def part(index):
        start = index * CHUNK; end = min(start + CHUNK, size) - 1
        path = part_root / f'{index:04d}.part'
        if path.exists() and path.stat().st_size == end - start + 1: return index
        for attempt in range(5):
            try:
                query = urllib.parse.urlencode({'download': 'true', 'afs_part': f'{index}_{time.time_ns()}'})
                url = f'https://huggingface.co/VAST-AI/TripoSG/resolve/{REVISION}/{NAME}?{query}'
                req = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
                with urllib.request.urlopen(req, timeout=30) as r, path.with_suffix('.tmp').open('wb') as out:
                    if r.status != 206 or r.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                        raise ValueError('Server did not honor exact requested byte range')
                    written = 0
                    while block := r.read(1024 * 1024): out.write(block); written += len(block)
                    if written != end - start + 1: raise ValueError('Incomplete range')
                os.replace(path.with_suffix('.tmp'), path)
                return index
            except Exception as exc:
                if attempt == 4: raise RuntimeError(f'Range {index} failed ({type(exc).__name__}); rerun resumes completed parts') from None
                time.sleep(min(2 ** attempt, 8))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        done = 0
        for future in concurrent.futures.as_completed([pool.submit(part, i) for i in range(count)]):
            future.result(); done += 1
            if done % 8 == 0 or done == count: print(f'RANGES_COMPLETE {done}/{count}', flush=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    combined = target.with_suffix('.verified-download')
    digest = hashlib.sha256()
    with combined.open('wb') as out:
        for index in range(count):
            with (part_root / f'{index:04d}.part').open('rb') as f:
                while block := f.read(4 * 1024 * 1024): digest.update(block); out.write(block)
    if digest.hexdigest() != expected: raise RuntimeError('Weight SHA-256 mismatch; refusing to install')
    os.replace(combined, target)
    evidence = ROOT / 'docs/evidence/model_downloads.json'
    result = json.loads(evidence.read_text()) if evidence.exists() else {}
    result['triposg'] = {'status': 'DOWNLOADED', 'revision': REVISION, 'path': str(target.parent.parent),
                         'transformer_sha256': expected, 'transport': 'official HF HTTPS range fallback'}
    evidence.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('WEIGHT_VERIFIED ' + expected, flush=True)


if __name__ == '__main__': main()
