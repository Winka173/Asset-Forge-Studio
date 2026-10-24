"""Working files are dropped after a game delivery; registered artifacts and requested export components stay."""
import pytest

from apps.api import intermediates, jobs, store

FILES = ['output/raw_master.npz', 'output/mesh_checkpoint.json', 'output/raw.glb', 'output/raw.blend', 'output/master.blend', 'output/LOD0.glb',
         'output/LOD1.glb', 'output/LOD3.glb', 'output/pc1440_front_passes.exr', 'output/pc1440_front.png', 'output/textures/texture_000.png', 'output/report.json']


@pytest.fixture
def delivered(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project()
    listing = [dict(id='done', status='REVIEW_REQUIRED', payload=dict(asset_id='a1')), dict(id='busy', status='RUNNING', payload=dict(asset_id='a1')),
               dict(id='other', status='REVIEW_REQUIRED', payload=dict(asset_id='a2'))]
    monkeypatch.setattr(jobs, 'listing', lambda: listing)
    for job in listing:
        for name in FILES:
            path = tmp_path / 'jobs' / job['id'] / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'x' * 10)
    for name in ('output/raw.glb', 'output/LOD0.glb'): store.add_artifact(tmp_path / 'jobs/done' / name, 'candidate', name, dict(asset_id='a1'))
    return tmp_path


def remaining(root, job): return sorted(p.relative_to(root / 'jobs' / job).as_posix() for p in (root / 'jobs' / job).rglob('*') if p.is_file())


def test_glb_only_delivery_keeps_artifacts_and_light_files_only(delivered):
    result = intermediates.prune('a1', dict(glb=True))
    assert remaining(delivered, 'done') == ['output/LOD0.glb', 'output/pc1440_front.png', 'output/raw.glb', 'output/report.json']
    assert result['files'] == 8 and result['bytes'] == 80
    # Running jobs and other assets are untouched.
    assert len(remaining(delivered, 'busy')) == len(FILES) and len(remaining(delivered, 'other')) == len(FILES)


def test_requested_export_components_are_kept(delivered):
    intermediates.prune('a1', dict(glb=True, blend=True, lods=True, textures=True))
    assert {'output/raw.blend', 'output/master.blend', 'output/LOD1.glb', 'output/LOD3.glb', 'output/textures/texture_000.png'} <= set(remaining(delivered, 'done'))
    assert 'output/raw_master.npz' not in remaining(delivered, 'done')


def test_projects_can_opt_out():
    assert intermediates.enabled({}) and intermediates.enabled(dict(cleanup_intermediates=None)) and not intermediates.enabled(dict(cleanup_intermediates=False))


def test_finalize_keeps_only_the_delivered_glb_rig_and_thumbnail(tmp_path, monkeypatch, qa_project):
    import json
    from fastapi.testclient import TestClient
    from apps.api import studio
    from apps.api.export_profiles import _schema
    from apps.api.main import app
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); client = TestClient(app)
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Tower', prompt='A tower')).json(); aid = model['id']
    monkeypatch.setattr(jobs, 'listing', lambda: [dict(id='inf', status='REVIEW_REQUIRED', payload=dict(asset_id=aid)), dict(id='bl', status='REVIEW_REQUIRED', payload=dict(asset_id=aid))])
    def put(name, body=b'x'):
        path = tmp_path / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(body); return path
    raw = store.add_artifact(put('jobs/inf/output/raw.glb'), 'candidate', 'raw', dict(asset_id=aid, project_id='runavelle'))
    concept = store.add_artifact(put('jobs/inf/output/concept.png'), 'concept', 'concept', dict(asset_id=aid, project_id='runavelle'))
    final = store.add_artifact(put('jobs/bl/output/LOD0.glb'), 'candidate', 'LOD0', dict(asset_id=aid, project_id='runavelle', job_id='bl', parent_id=raw['id']))
    rig = store.add_artifact(put('jobs/rig/output/rigged.glb'), 'rigged', 'rig', dict(asset_id=aid, project_id='runavelle', parent_id=final['id']))
    put('jobs/bl/output/fit_three_quarter.png'); put('jobs/bl/output/pc1440_front.png'); put('jobs/bl/output/report.json')
    assert client.post(f'/api/production/assets/{aid}/finalize').status_code == 409  # nothing delivered yet
    shipped = put('exports/game/tower.glb'); _schema()
    delivery = dict(id='e1', delivery_scope='game', artifact_id=final['id'], export_directory=str(shipped.parent), output_root=str(tmp_path / 'exports'),
                    files=[dict(name='tower.glb', sha256=store.digest(shipped))])
    with store.connect() as db: db.execute('INSERT INTO selective_exports VALUES (?,?,?)', ('e1', aid, json.dumps(delivery)))
    value = studio.asset(aid); value.update(published_artifact_id=final['id'], concept_artifact_id=concept['id']); studio.save_asset(value)
    result = client.post(f'/api/production/assets/{aid}/finalize').json()
    assert set(result['kept']) == {final['id'], rig['id']} and result['files'] == 3
    left = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file() and p.suffix != '.sqlite' and 'jobs' in p.parts)
    assert left == ['jobs/bl/output/LOD0.glb', 'jobs/bl/output/fit_three_quarter.png', 'jobs/bl/output/report.json', 'jobs/rig/output/rigged.glb']
    assert shipped.is_file() and studio.asset(aid)['concept_artifact_id'] is None
