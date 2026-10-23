"""Asset Benchmark Lab: submit representative assets through the real Auto pipeline and collect measured results.

Usage (against a running AFS backend with its worker):
  python -m scripts.benchmark_lab submit --base http://127.0.0.1:8766 --project <id> --out run.json
  python -m scripts.benchmark_lab collect --base http://127.0.0.1:8766 --run run.json --out results.json
Submitting starts real GPU work through the shared queue; collecting only reads.
"""
import argparse, json, time, urllib.request
from pathlib import Path

CASES = [
    ('small_prop', 'Mana potion', 'A fantasy mana potion bottle with a brass stopper, cork seal and glowing cyan liquid.'),
    ('hard_surface', 'Knight longsword', "A knight's longsword with an ornate gold crossguard, blue leather grip and a polished steel blade."),
    ('hero', 'Archer hero', 'A stylized female archer hero in navy and gold armor holding a longbow, standing pose.'),
    ('architecture', 'Archer tower T3', 'A three-tier archer tower with a stone base, timber platforms, banners and a navy slate roof.'),
    ('modular_kit', 'Castle wall segment', 'A straight castle wall segment with crenellations in ivory stone, a single modular kit piece.'),
    ('creature', 'Stone golem boss', 'A stone golem boss creature with mossy rock armor and glowing cyan runes.'),
]


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    return json.load(urllib.request.urlopen(urllib.request.Request(base + path, data, {'Content-Type': 'application/json'}), timeout=60))


def submit(args):
    run = dict(started=time.time(), base=args.base, project=args.project, cases=[])
    for key, name, prompt in CASES:
        asset = call(args.base, '/api/assets', dict(project_id=args.project, name=f'BM {name}', prompt=prompt, reference_ids=[], settings={}, category='Benchmark'))
        result = call(args.base, '/api/automation/single', dict(asset_id=asset['id'], quality='Maximum', engine='auto', seeds=[42], request_id=f'benchmark-{key}-{int(run["started"])}'))
        run['cases'].append(dict(key=key, name=name, prompt=prompt, asset_id=asset['id'], batch_id=result['batch_id'], submitted=time.time()))
    Path(args.out).write_text(json.dumps(run, indent=2), encoding='utf-8')
    print(json.dumps([c['key'] for c in run['cases']]))


def collect(args):
    run = json.loads(Path(args.run).read_text(encoding='utf-8'))
    jobs = call(args.base, '/api/jobs')
    rows = []
    for case in run['cases']:
        detail = call(args.base, f"/api/production/assets/{case['asset_id']}")
        item = call(args.base, f"/api/batches/{case['batch_id']}")['items'][0]
        auto = item.get('automation') or {}
        own = [j for j in jobs if j['payload'].get('asset_id') == case['asset_id']]
        processed = [a for a in detail['artifacts'] if a['metadata'].get('stage') == 'blender_processed']
        finished = max((j.get('updated_at') or '' for j in own), default='')
        rows.append(dict(key=case['key'], name=case['name'], production=detail['asset'].get('production_status'), qa=detail['asset'].get('qa_status'),
                         export=detail['asset'].get('export_status'), stage=auto.get('stage'), error=auto.get('error'),
                         jobs={k: sum(j['payload'].get('kind') == k for j in own) for k in sorted({j['payload'].get('kind') for j in own})},
                         failed_jobs=[dict(kind=j['payload'].get('kind'), status=j['status'], error=(j.get('error') or '')[:300]) for j in own if j['status'] in ('FAILED', 'BLOCKED')],
                         concept_ranking=(auto.get('concept_selection') or {}).get('ranking'), triangles=[a['metadata'].get('triangles') for a in processed],
                         last_update=finished))
    Path(args.out).write_text(json.dumps(dict(run=run, results=rows), indent=2), encoding='utf-8')
    for r in rows:
        print(r['key'], r['production'], r['qa'], r['export'], r['triangles'], r['stage'], (r['error'] or '')[:120])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('submit'); s.add_argument('--base', required=True); s.add_argument('--project', required=True); s.add_argument('--out', required=True)
    c = sub.add_parser('collect'); c.add_argument('--base', required=True); c.add_argument('--run', required=True); c.add_argument('--out', required=True)
    args = parser.parse_args(); submit(args) if args.command == 'submit' else collect(args)
