import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apps.api import automation, jobs, store, style_anchor
from apps.api.concept_rank import measure, rank
from apps.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); return TestClient(app)


def _image(path, box, colour=(200, 200, 205), background=(110, 110, 112), texture=False):
    canvas = np.full((512, 512, 3), background, dtype=np.uint8)
    x0, y0, x1, y1 = box
    patch = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.uint8) + np.array(colour, dtype=np.uint8)
    if texture:  # stone courses: low colour contrast, strong local gradients
        patch[::12] = np.clip(patch[::12].astype(int) - 40, 0, 255)
        patch[:, ::16] = np.clip(patch[:, ::16].astype(int) - 40, 0, 255)
    canvas[y0:y1, x0:x1] = patch
    Image.fromarray(canvas).save(path)
    return path


def test_real_default_queues_a_concept_tournament_once(client, monkeypatch):
    monkeypatch.setattr(automation, 'CONCEPT_CANDIDATES', {'Maximum': 3, 'Balanced': 2, 'Fast': 1})
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Castle', prompt='A fortified castle with four towers')).json()
    body = dict(asset_id=model['id'], request_id='concept-tournament-test', quality='Maximum', engine='trellis2_community', seeds=[42])
    assert client.post('/api/automation/single', json=body).status_code == 201
    assert client.post('/api/automation/single', json=body).status_code == 201
    concepts = [j for j in jobs.listing() if j['payload']['kind'] == 'concept']
    assert len(concepts) == 3 and {j['payload']['asset_id'] for j in concepts} == {model['id']}
    assert len({j['payload']['seed'] for j in concepts}) == 3


def test_framing_gates_and_ranking(tmp_path):
    centred = _image(tmp_path / 'centred.png', (150, 100, 360, 430))
    cropped = _image(tmp_path / 'cropped.png', (0, 120, 300, 512))
    tiny = _image(tmp_path / 'tiny.png', (250, 250, 262, 262))
    grey_stone = _image(tmp_path / 'stone.png', (140, 90, 370, 440), colour=(118, 118, 120), texture=True)
    assert measure(centred)['eligible']
    assert not measure(cropped)['eligible'] and 'frame edge' in measure(cropped)['reason']
    assert not measure(tiny)['eligible']
    stone = measure(grey_stone)
    assert stone['eligible'] and stone['occupancy'] > 0.2  # colour-distance segmentation would miss grey-on-grey
    ranked = rank([(dict(id='a'), cropped), (dict(id='b'), centred)])
    assert ranked[0][0]['id'] == 'b' and not ranked[1][1]['eligible']


def test_anchor_palette_prefers_matching_style(tmp_path):
    anchor = _image(tmp_path / 'anchor.png', (160, 80, 350, 450), colour=(40, 60, 120))
    navy = _image(tmp_path / 'navy.png', (150, 100, 360, 430), colour=(42, 62, 118))
    orange = _image(tmp_path / 'orange.png', (150, 100, 360, 430), colour=(200, 110, 40))
    assert measure(navy, anchor)['palette_similarity'] > measure(orange, anchor)['palette_similarity']
    assert rank([(dict(id='orange'), orange), (dict(id='navy'), navy)], anchor)[0][0]['id'] == 'navy'


def test_style_anchor_lock_has_no_machine_paths(monkeypatch):
    monkeypatch.setattr(style_anchor, 'adapter_dir', lambda: None)
    assert style_anchor.resolve('runavelle', dict(style_anchor_artifact_id='x'), ()) is None
    anchor = dict(artifact_id='a', path='C:/x.png', sha256='s', adapter_dir='C:/hub', weight_name='w', scale=0.35)
    assert style_anchor.locked(anchor) == dict(artifact_id='a', sha256='s', weight_name='w', scale=0.35)
