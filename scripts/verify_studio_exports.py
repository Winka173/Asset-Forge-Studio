"""Real local Blender export acceptance against isolated QA data, not production approval."""
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8766'


def request(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response: return json.load(response)


def main():
    flow = json.loads((ROOT / 'docs/evidence/studio_real_flow.json').read_text())
    identifier = flow['asset']['id']; master = flow['asset']['master']
    snapshot = request('/api/studio'); original = next(a for a in snapshot['artifacts'] if a['id'] == master)
    exports = []
    for preset, fmt in [('Master', 'fbx'), ('Unity Mobile', 'fbx'), ('Unity PC', 'glb')]:
        body = dict(artifact_id=master, preset=preset, format=fmt, request_id=f'qa-studio-{preset}-{fmt}-v1')
        result = request(f'/api/assets/{identifier}/export', body)
        assert request(f'/api/assets/{identifier}/export', body)['id'] == result['id']
        exports.append(result)
        print('REAL_EXPORT_QUEUED', preset, result.get('job_id'), flush=True)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        value = next(a for a in request('/api/studio')['assets'] if a['id'] == identifier)
        current = [e for e in value['exports'] if e['id'] in {e['id'] for e in exports}]
        if all(e['validation'] in ['REVIEW_REQUIRED', 'FAILED', 'BLOCKED', 'CANCELLED'] for e in current): break
        time.sleep(2)
    evidence = []
    for result in current:
        assert result['validation'] == 'REVIEW_REQUIRED', result
        mesh_file = next(f for f in result['files'] if f['name'].endswith('.' + result['format']))
        with urllib.request.urlopen(BASE + mesh_file['url']) as response: signature = response.read(24)
        assert signature.startswith(b'glTF' if result['format'] == 'glb' else b'Kaydara FBX Binary')
        manifest = request(f'/api/jobs/{result["job_id"]}/files/manifest.json')
        level = 0 if result['preset'] == 'Master' else 2 if result['preset'] == 'Unity Mobile' else 1
        measured = manifest['glb_inspections'][f'LOD{level}.glb']['triangles']
        if result.get('target_triangles'): assert measured <= result['target_triangles'] * 1.01
        evidence.append(dict(preset=result['preset'], format=result['format'], job_id=result['job_id'],
                             files=result['files'], measured_triangles=measured, validation=manifest['checks'],
                             unity='NOT_TESTED', visual_quality='NEEDS_REVIEW'))
    after = next(a for a in request('/api/studio')['artifacts'] if a['id'] == master)
    assert after['sha256'] == original['sha256']
    result = dict(status='PASS', scope='actual Blender file generation and reopen only', exports=evidence,
                  original_master_unchanged=True, artist_approval='NOT_TESTED', unity_import='NOT_TESTED')
    (ROOT / 'docs/evidence/studio_exports.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('REAL_EXPORT_PRESETS_PASS', [(e['preset'], e['measured_triangles']) for e in evidence], flush=True)


if __name__ == '__main__': main()
