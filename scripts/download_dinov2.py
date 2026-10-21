"""Explicit consented download from the encoder author's public model endpoint."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--authorized-download', action='store_true')
    if not parser.parse_args().authorized_download: raise SystemExit('Download authorization required')
    root = Path(__file__).resolve().parents[1]
    target = root / 'models/dinov2/dinov2_vitl14_reg4_pretrain.pth'
    target.parent.mkdir(parents=True, exist_ok=True)
    url = 'https://dl.fbaipublicfiles.com/dinov2/dinov2_vitl14/dinov2_vitl14_reg4_pretrain.pth'
    temporary = target.with_suffix('.download')
    if not target.exists():
        offset = temporary.stat().st_size if temporary.exists() else 0
        request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
        with urllib.request.urlopen(request, timeout=90) as response:
            resume = offset and response.status == 206
            with temporary.open('ab' if resume else 'wb') as output:
                total = offset if resume else 0
                while chunk := response.read(8 * 1024**2):
                    output.write(chunk); total += len(chunk)
                    print(f'DINO_BYTES {total}', flush=True)
        if temporary.stat().st_size != 1217607321:
            raise RuntimeError('Incomplete official DINO checkpoint; retain partial download for resume')
        temporary.rename(target)
    with target.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    evidence = {'url': url, 'bytes': target.stat().st_size, 'sha256': digest,
                'license': 'Apache-2.0', 'source': 'facebookresearch/dinov2 official hub URL',
                'hash_scope': 'local content digest; author does not publish expected SHA256 here'}
    (root / 'docs/evidence/dinov2_download.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence), flush=True)


if __name__ == '__main__': main()
