"""Held weapons/shields become separate, socket-tagged assets; the character is drawn empty-handed."""
import pytest
from fastapi.testclient import TestClient

from apps.api import batch, jobs, store, studio
from apps.api.held_items import detect
from apps.api.main import app


@pytest.mark.parametrize('text,items', [
    ('swordsman with shield', ['shield', 'sword']), ('kiếm sĩ với khiên', ['shield', 'sword']), ('A knight with a longsword and shield', ['sword', 'shield']),
    ('archer', ['bow']), ('cung thủ với cung và kiếm', ['sword', 'bow']), ('Bone Spearman', ['spear']), ('A mage holding a staff', ['staff']),
    ('giant red dragon', []), ('A knight', []), ('Skeleton warrior with an axe', ['axe']),
])
def test_held_item_detection_in_english_and_vietnamese(text, items):
    assert detect(text) == items


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); return TestClient(app)


def test_character_items_become_companion_assets_and_the_body_is_empty_handed(client):
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Swordsman', prompt='A swordsman with a shield')).json()
    group = client.post('/api/automation/single', json=dict(asset_id=model['id'], request_id='held-items-single', quality='Maximum', engine='trellis2_community', seeds=[42])).json()['batch_id']
    value = batch.batch(group); body = next(i for i in value['items'] if i['asset_id'] == model['id'])
    companions = [i for i in value['items'] if i.get('companion_of') == model['id']]
    assert body['held_items'] == ['shield', 'sword'] and {(c['name'], c['socket']) for c in companions} == {('Swordsman – shield', 'left_hand'), ('Swordsman – sword', 'right_hand')}
    assert all(c['started'] and c['automation']['enabled'] and c['target_height_m'] for c in companions)
    concepts = [j for j in jobs.listing() if j['payload']['kind'] == 'concept' and j['payload']['asset_id'] == model['id']]
    assert concepts and all('Both hands empty' in j['payload']['prompt'] and j['payload']['negative_prompt'].startswith('shield, sword') for j in concepts)
    spec = studio.asset(companions[0]['asset_id'])['resolved_specification']
    assert spec['attach_to']['parent_asset_id'] == model['id']
    # Advancing again never duplicates companions.
    from apps.api import automation
    automation.advance(group); assert len([i for i in batch.batch(group)['items'] if i.get('companion_of')]) == 2


def test_props_and_opted_out_projects_get_no_companions(client):
    from apps.api.held_items import ensure_companions
    crate = dict(asset_id='x', name='Crate', prompt='A wooden crate with a sword painted on it', quality='Maximum')
    assert ensure_companions(dict(project_id='runavelle', items=[]), crate, {}, lambda: None) == [] and crate['held_items'] == []
    knight = dict(asset_id='y', name='Knight', prompt='A knight with a sword', quality='Maximum')
    assert ensure_companions(dict(project_id='runavelle', items=[]), knight, dict(separate_held_items=False), lambda: None) == []
