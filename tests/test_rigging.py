"""Post-delivery auto-rig: a side branch that never blocks, fails or re-opens the delivered asset."""
import json
import trimesh
from apps.api import store, jobs, rigging


def _rigged(path, joints=3):
    trimesh.creation.box((0.5, 1.8, 0.3)).export(path)
    raw = path.read_bytes(); length = int.from_bytes(raw[12:16], 'little'); doc = json.loads(raw[20:20 + length])
    doc['skins'] = [dict(joints=list(range(joints)))]
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']: primitive['attributes'].update(JOINTS_0=0, WEIGHTS_0=0)
    body = json.dumps(doc).encode(); body += b' ' * (-len(body) % 4); rest = raw[20 + length:]
    path.write_bytes(raw[:8] + (12 + 8 + len(body) + len(rest)).to_bytes(4, 'little') + len(body).to_bytes(4, 'little') + b'JSON' + body + rest)
    return path


def test_rig_facts_require_a_real_skin(tmp_path):
    facts = rigging.joints(_rigged(tmp_path / 'rigged.glb', 28))
    assert facts == dict(skins=1, joints=28, skinned_primitives=True)
    plain = tmp_path / 'plain.glb'; trimesh.creation.box((1, 1, 1)).export(plain)
    assert rigging.joints(plain)['skins'] == 0


def test_only_characters_and_creatures_are_rigged(monkeypatch):
    monkeypatch.setattr(rigging, 'installed', lambda: True)
    assert rigging.wanted(dict(prompt='A knight with a shield'), {})
    assert rigging.wanted(dict(prompt='A giant red dragon'), {})
    assert not rigging.wanted(dict(prompt='A wooden supply barrel'), {})
    assert not rigging.wanted(dict(prompt='A knight with a shield'), dict(auto_rig=False))
    monkeypatch.setattr(rigging, 'installed', lambda: False)
    assert not rigging.wanted(dict(prompt='A knight with a shield'), {})


def test_rig_jobs_never_count_as_delivery_work(tmp_path, monkeypatch, qa_project):
    from apps.api import automation, batch
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project()
    value = dict(id='g', project_id='runavelle'); item = dict(asset_id='a', attempt=0)
    rig = dict(id='r', status='FAILED', payload=dict(kind='rig', batch_id='g', asset_id='a', batch_attempt=0))
    assert automation.snapshot_item_state(value, item, [rig], []) == []
