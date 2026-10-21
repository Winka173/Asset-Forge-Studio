"""Explicitly invoked, consented weight download. Never called by app startup or inference."""
import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authorized-download', action='store_true')
    parser.add_argument('--engines', nargs='+', choices=['triposg', 'sf3d'], required=True)
    args = parser.parse_args()
    if not args.authorized_download: raise SystemExit('Explicit download authorization required')
    root = Path(__file__).resolve().parents[1]
    sources = json.loads((root / 'docs/evidence/engine_sources.json').read_text(encoding='utf-8'))['engines']
    evidence = root / 'docs/evidence/model_downloads.json'
    result = json.loads(evidence.read_text(encoding='utf-8')) if evidence.exists() else {}
    for identifier in args.engines:
        row = sources[identifier]
        repo_id = row['model'].removeprefix('https://huggingface.co/')
        try:
            target = root / 'models' / identifier
            print(f'DOWNLOAD {repo_id}@{row["model_revision"]} -> {target}', flush=True)
            snapshot_download(repo_id, revision=row['model_revision'], local_dir=target,
                              ignore_patterns=['*.gif', '.gitattributes'], max_workers=2)
            result[identifier] = {'status': 'DOWNLOADED', 'revision': row['model_revision'], 'path': str(target)}
        except Exception as exc:
            # No token or credential content is logged.
            result[identifier] = {'status': 'BLOCKED', 'exception_type': type(exc).__name__,
                                   'reason': 'Access/network failure; gated models require user license/access acceptance' if identifier == 'sf3d' else 'Download failed; see network/access status'}
        (root / 'docs/evidence/model_downloads.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result[identifier]), flush=True)


if __name__ == '__main__': main()
