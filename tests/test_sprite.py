"""2D sprite slice: sprite framing through the shared concept route, then a measured deterministic cutout."""
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from apps.api import jobs, store
from apps.api.main import app
from engines import sprite as engine
from engines.concept_prompt import compose


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); return TestClient(app)


def _studio_render(path, gradient=True, shadow=True, text=True):
    image = Image.new('RGB', (512, 512)); draw = ImageDraw.Draw(image)
    for y in range(512):
        shade = 150 - y // 8 if gradient else 128; draw.line([(0, y), (511, y)], fill=(shade, shade, shade + 4))
    if shadow: draw.ellipse([150, 400, 380, 440], fill=(95, 95, 98))
    draw.rectangle([200, 120, 320, 410], fill=(30, 90, 170)); draw.ellipse([230, 80, 290, 140], fill=(200, 160, 60))
    if text: draw.rectangle([470, 490, 505, 505], fill=(240, 240, 240))
    image.save(path); return path


def test_sprite_framing_asks_for_a_flat_backdrop_without_shadow():
    prompt, _ = compose('A mana potion bottle.', 'hand-painted', 'Maximum', framing='sprite_2d')
    head = prompt.split('\n', 1)[0]
    assert 'no cast shadow' in head and 'flat even light grey background' in head and '3D game asset' not in head


def test_cutout_removes_gradient_background_shadow_and_text_islands(tmp_path):
    sprite, report = engine.cutout(_studio_render(tmp_path / 'render.png'))
    assert report['usable'] and report['border_opaque_fraction'] == 0 and report['dropped_islands'] >= 1
    alpha = sprite.getchannel('A')
    assert sprite.size[0] < 160 and sprite.size[1] < 360  # tight crop: no shadow ellipse, no corner text
    assert alpha.getpixel((sprite.size[0] // 2, sprite.size[1] // 2)) == 255
    files = engine.export(sprite, tmp_path / 'out', (256, 512))
    assert [Image.open(f['path']).size for f in files] == [(256, 256), (512, 512)] and Image.open(files[0]['path']).mode == 'RGBA'


def test_cutout_reports_unusable_when_the_object_touches_the_frame(tmp_path):
    image = Image.new('RGB', (256, 256), (120, 120, 120)); ImageDraw.Draw(image).rectangle([0, 60, 255, 200], fill=(30, 90, 170)); image.save(tmp_path / 'wide.png')
    _, report = engine.cutout(tmp_path / 'wide.png')
    assert not report['usable'] and report['border_opaque_fraction'] > 0.02


def test_generate_queues_concepts_then_cpu_cutouts_and_registers_sprites(client, tmp_path):
    from apps.api import studio
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Potion icon', prompt='A mana potion bottle', asset_type='sprite_2d')).json()
    assert client.post('/api/sprites/generate', json=dict(asset_id=model['id'], request_id='sprite-generate-1', seeds=[42, 43])).status_code == 201
    concepts = [j for j in jobs.listing() if j['payload']['kind'] == 'concept']; cutouts = [j for j in jobs.listing() if j['payload']['kind'] == 'sprite_cutout']
    assert len(concepts) == 2 and len(cutouts) == 2 and all(jobs.resource_class(j['payload']) == 'cpu' for j in cutouts)
    assert all(j['payload']['effective_config']['framing'] == 'sprite_2d' for j in concepts)
    assert jobs.dependency_readiness(cutouts[0])[0] == 'waiting'
    # Repeating the click reuses both stages.
    client.post('/api/sprites/generate', json=dict(asset_id=model['id'], request_id='sprite-generate-1', seeds=[42, 43])); assert len(jobs.listing()) == 4
    # Simulate the concept output with a real image and run the actual cutout stage.
    concept = concepts[0]; folder = store.DATA / 'jobs' / concept['id'] / 'output'; folder.mkdir(parents=True)
    _studio_render(folder / 'concept.png')
    store.add_artifact(folder / 'concept.png', 'concept', 'Sprite concept', dict(project_id='runavelle', asset_id=model['id'], job_id=concept['id']))
    for state in ('RUNNING', 'GENERATED', 'VALIDATING', 'REVIEW_REQUIRED'): jobs.transition(concept['id'], state)
    cutout = next(j for j in cutouts if j['payload']['concept_job_id'] == concept['id'])
    jobs.worker.execute(cutout); assert jobs.get(cutout['id'])['status'] == 'REVIEW_REQUIRED'
    listed = next(a for a in studio.studio('runavelle')['assets'] if a['id'] == model['id'])
    assert listed['thumbnail_kind'] == 'sprite' and {v['metadata']['size'] for v in listed['versions']} == {512}


def test_three_d_assets_cannot_take_the_sprite_route(client):
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Crate', prompt='A crate')).json()
    assert client.post('/api/sprites/generate', json=dict(asset_id=model['id'], request_id='sprite-generate-2')).status_code == 409


def test_harmonization_keeps_hue_and_background(tmp_path):
    from engines.harmonize import harmonize
    vivid = tmp_path / 'vivid.png'; image = Image.new('RGB', (256, 256), (120, 120, 120)); ImageDraw.Draw(image).ellipse([60, 60, 196, 196], fill=(220, 30, 30)); image.save(vivid)
    muted = tmp_path / 'anchor.png'; image = Image.new('RGB', (256, 256), (120, 120, 120)); ImageDraw.Draw(image).rectangle([70, 70, 186, 186], fill=(150, 110, 70)); image.save(muted)
    result, report = harmonize(vivid, muted, 0.5)
    assert report['median_hue_shift_degrees'] < 1 and report['after']['c_mean'] < report['before']['c_mean']
    r, g, b = result.getpixel((128, 128)); assert r > g + 60 and r > b + 60  # still clearly red
    assert result.getpixel((5, 5)) == (120, 120, 120)  # background untouched


def test_harmonization_skips_instead_of_guessing_when_no_object_is_measurable(tmp_path):
    from engines.harmonize import harmonize
    flat = tmp_path / 'flat.png'; Image.new('RGB', (64, 64), (120, 120, 120)).save(flat)
    result, report = harmonize(flat, flat, 0.5)
    assert report['skipped'] and result.getpixel((10, 10)) == (120, 120, 120)
