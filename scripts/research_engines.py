"""Fetch official repository metadata/model file sizes only. Never downloads weights."""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENGINES = {
    'triposg': ('VAST-AI-Research/TripoSG', 'VAST-AI/TripoSG'),
    'sf3d': ('Stability-AI/stable-fast-3d', 'stabilityai/stable-fast-3d'),
    'hunyuan21': ('Tencent-Hunyuan/Hunyuan3D-2.1', 'tencent/Hunyuan3D-2.1'),
    'spar3d': ('Stability-AI/stable-point-aware-3d', 'stabilityai/stable-point-aware-3d'),
    'trellis2': ('microsoft/TRELLIS.2', 'microsoft/TRELLIS.2-4B'),
}


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'AssetForgeStudio-audit'})
    with urllib.request.urlopen(request, timeout=30) as r:
        return json.load(r)


def main():
    result = {'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'weights_downloaded': False, 'engines': {}}
    for identifier, (repo, model) in ENGINES.items():
        row = {'repo': 'https://github.com/' + repo, 'model': 'https://huggingface.co/' + model, 'inference': 'NOT_TESTED'}
        for key, url in [('code', f'https://api.github.com/repos/{repo}/commits/main'), ('weights', f'https://huggingface.co/api/models/{model}?blobs=true')]:
            try:
                info = fetch(url)
                if key == 'code': row['code_revision'] = info['sha']
                else:
                    row.update({'model_revision': info['sha'], 'gated': info.get('gated'), 'license_metadata': info.get('cardData', {}).get('license'),
                                'all_repo_file_bytes': sum(f.get('size', 0) for f in info.get('siblings', [])),
                                'files': [{'path': f['rfilename'], 'bytes': f.get('size')} for f in info.get('siblings', [])]})
            except Exception as exc: row[key + '_error'] = str(exc)
        result['engines'][identifier] = row
        print(identifier, row.get('all_repo_file_bytes'), row.get('gated'), row.get('code_revision', row.get('code_error')))
    target = Path(__file__).resolve().parents[1] / 'docs/evidence/engine_sources.json'
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__': main()
