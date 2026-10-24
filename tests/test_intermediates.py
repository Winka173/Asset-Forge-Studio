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
