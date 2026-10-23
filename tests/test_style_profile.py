"""Shape-free style profile: transferable materials/colours as text; the anchor image never conditions SDXL."""
import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apps.api import automation, jobs, store, style_profile
from apps.api.main import app
from engines import style_profile as engine


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); return TestClient(app)


def _png(colour=(40, 60, 140), background=(120, 120, 120)):
    image = Image.new('RGB', (64, 64), background)
    image.paste(colour, (16, 16, 48, 48))
    stream = io.BytesIO(); image.save(stream, format='PNG'); return stream.getvalue()


def test_structure_words_never_reach_other_assets():
    assert engine.clean('midnight blue slate roof tiles, ivory limestone walls; aged bronze finials') == 'midnight blue slate, ivory limestone; aged bronze'
    observed = dict(observation=dict(rendering_style='hand-painted tower render', stylization='stylized', surface_detail='high', edge_treatment='beveled roof edges', accent='',
        materials=[dict(substance='slate roof tiles', colour='navy', finish='satin', wear='weathered')]))
    text = engine.style_text(dict(palette=dict(entries=[dict(name='navy blue', share=0.5)]), observed=observed))
    assert 'navy slate (satin, weathered)' in text and 'colour palette: navy blue' in text
    assert not engine.SHAPE_WORDS.search(text)


def test_measured_palette_excludes_the_background(tmp_path):
    path = tmp_path / 'anchor.png'; path.write_bytes(_png())
    palette = engine.measure_palette(path)
    assert palette['entries'][0]['name'] == 'blue' and palette['entries'][0]['share'] > 0.9
    assert 0.2 < palette['subject_fraction'] < 0.3


def test_batch_waits_for_one_shared_profile_and_keeps_the_anchor_out_of_sdxl(client, monkeypatch):
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Tree', prompt='A fantasy tree with a thick trunk')).json()
    reference = client.post('/api/import/concept', params=dict(project_id='runavelle', asset_id=model['id']), files=dict(file=('anchor.png', _png()))).json()
    project = client.get('/api/projects').json()[0]
    assert client.post('/api/projects/runavelle', json=dict(name=project['name'], style_anchor_artifact_id=reference['id'])).status_code == 200
    body = dict(asset_id=model['id'], request_id='style-profile-gate', quality='Maximum', engine='trellis2_community', seeds=[42])
    group = client.post('/api/automation/single', json=body).json()['batch_id']
    analysis = [j for j in jobs.listing() if j['payload']['kind'] == 'style_profile']
    assert len(analysis) == 1 and jobs.resource_class(analysis[0]['payload']) == 'cpu'
    assert not any(j['payload']['kind'] == 'concept' for j in jobs.listing())
    automation.advance(group); assert len([j for j in jobs.listing() if j['payload']['kind'] == 'style_profile']) == 1
    # Unavailable local VLM: the profile still records the measured palette; nothing is fabricated.
    def unavailable(path, progress): raise ValueError('Injected unavailable local runtime')
    monkeypatch.setattr(engine, 'observe', unavailable)
    jobs.worker.execute(analysis[0]); assert jobs.get(analysis[0]['id'])['status'] == 'REVIEW_REQUIRED'
    stored = style_profile.find('runavelle', reference['sha256'])
    assert stored['observed'] is None and stored['palette']['entries'][0]['name'] == 'blue'
    automation.advance(group)
    concepts = [j for j in jobs.listing() if j['payload']['kind'] == 'concept']
    assert concepts and all(j['payload'].get('style_anchor') is None for j in concepts)
    assert all(j['payload']['effective_config']['style_profile']['anchor_sha256'] == reference['sha256'] for j in concepts)
    assert all('colour palette: blue' in j['payload']['prompt'] for j in concepts)


def test_image_mode_keeps_the_earlier_ip_adapter_route(client):
    assert style_profile.mode(dict(style_anchor_mode='image')) == 'image' and style_profile.mode({}) == 'profile'
    assert style_profile.ensure('runavelle', dict(style_anchor_mode='image', style_anchor_artifact_id='x'), ()) == ('none', None)


def test_regenerating_one_asset_of_a_cancelled_batch_does_not_show_it_as_cancelled(client):
    from apps.api import batch, statuses
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Barrel', prompt='A wooden supply barrel')).json()
    group = client.post('/api/automation/single', json=dict(asset_id=model['id'], request_id='cancel-then-regenerate', quality='Fast', engine='trellis2_community', seeds=[42])).json()['batch_id']
    assert client.post(f'/api/batches/{group}/control', json=dict(action='cancel')).status_code == 200
    for job in jobs.listing():
        if job['status'] not in jobs.TERMINAL: jobs.transition(job['id'], 'CANCELLED')
    statuses.refresh_all(); assert client.get(f'/api/production/assets/{model["id"]}').json()['asset']['production_status'] == 'cancelled'
    assert client.post(f'/api/batches/{group}/items/{model["id"]}/action', json=dict(action='regenerate')).status_code == 200
    value = batch.batch(group); assert value['items'][0]['production_cancelled'] is False and value['production_cancelled'] is False
    statuses.refresh_all(); assert client.get(f'/api/production/assets/{model["id"]}').json()['asset']['production_status'] != 'cancelled'


def test_unstarted_items_do_not_keep_a_regenerated_batch_cancelled(client):
    from apps.api import batch
    first = client.post('/api/assets', json=dict(project_id='runavelle', name='Crate', prompt='A wooden crate')).json()
    group = client.post('/api/automation/single', json=dict(asset_id=first['id'], request_id='legacy-cancel', quality='Fast', engine='trellis2_community', seeds=[42])).json()['batch_id']
    value = batch.batch(group); value['production_cancelled'] = True
    other = client.post('/api/assets', json=dict(project_id='runavelle', name='Sack', prompt='A grain sack')).json()
    value['items'].append(dict(value['items'][0], asset_id=other['id'], name='Sack', started=False)); [i.pop('production_cancelled', None) for i in value['items']]
    batch.save(value)  # data cancelled before per-asset flags existed
    for job in jobs.listing():
        if job['status'] not in jobs.TERMINAL: jobs.transition(job['id'], 'CANCELLED')
    assert client.post(f'/api/batches/{group}/items/{first["id"]}/action', json=dict(action='regenerate')).status_code == 200
    assert batch.batch(group)['production_cancelled'] is False


def test_batch_generate_all_shares_one_profile_across_assets(client, monkeypatch):
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Anchor holder', prompt='Anchor')).json()
    reference = client.post('/api/import/concept', params=dict(project_id='runavelle', asset_id=model['id']), files=dict(file=('anchor.png', _png()))).json()
    project = client.get('/api/projects').json()[0]
    client.post('/api/projects/runavelle', json=dict(name=project['name'], style_anchor_artifact_id=reference['id']))
    manifest = ('# SHARED_SUPPLY_BARREL — Supply_Barrel\nSupply_Barrel. A wooden supply barrel with iron hoops.\n\n'
                '# BIO_TEST_Tree_01 — Test Tree_01\nTest Tree_01. A medium fantasy tree with a thick trunk.\n')
    value = client.post('/api/batches/import', files=dict(file=('two.md', manifest.encode())), data=dict(project_id='runavelle', mode='Maximum Quality Batch')).json()
    assert len(value['items']) == 2
    assert client.post(f"/api/batches/{value['id']}/run-all", json={}).status_code == 200
    analysis = [j for j in jobs.listing() if j['payload']['kind'] == 'style_profile']
    assert len(analysis) == 1 and not any(j['payload']['kind'] == 'concept' for j in jobs.listing())
    monkeypatch.setattr(engine, 'observe', lambda path, progress: dict(observation=dict(rendering_style='hand-painted', stylization='stylized', surface_detail='high',
        edge_treatment='soft bevels', accent='', materials=[dict(substance='oak', colour='warm brown', finish='matte', wear='weathered')]), model='fixture', model_digest='fixture', duration_seconds=0))
    jobs.worker.execute(analysis[0])
    automation.advance(value['id']); automation.advance(value['id'])
    concepts = [j for j in jobs.listing() if j['payload']['kind'] == 'concept']
    assert {j['payload']['asset_id'] for j in concepts} == {i['asset_id'] for i in value['items']}
    assert all(j['payload'].get('style_anchor') is None and j['payload']['effective_config']['style_profile']['observed'] for j in concepts)
    assert all('warm brown oak (matte, weathered)' in j['payload']['prompt'] for j in concepts)
    assert len([j for j in jobs.listing() if j['payload']['kind'] == 'style_profile']) == 1


def test_settings_view_reads_without_queueing_work(client):
    assert client.get('/api/projects/runavelle/style-profile').json()['status'] == 'no_anchor'
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Holder', prompt='Anchor')).json()
    reference = client.post('/api/import/concept', params=dict(project_id='runavelle', asset_id=model['id']), files=dict(file=('anchor.png', _png()))).json()
    project = client.get('/api/projects').json()[0]
    client.post('/api/projects/runavelle', json=dict(name=project['name'], style_anchor_artifact_id=reference['id']))
    view = client.get('/api/projects/runavelle/style-profile').json()
    assert view['status'] == 'measured_only' and view['palette'][0]['name'] == 'blue' and view['mode'] == 'profile'
    assert not jobs.listing()


def test_world_preview_seeds_provisional_colours_from_the_palette(client):
    plain = client.post('/api/world/preview-plan', json=dict(project_id='runavelle', name='Field', prompt='')).json()['plan']
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Holder', prompt='Anchor')).json()
    reference = client.post('/api/import/concept', params=dict(project_id='runavelle', asset_id=model['id']), files=dict(file=('anchor.png', _png(colour=(70, 120, 50))))).json()
    project = client.get('/api/projects').json()[0]
    client.post('/api/projects/runavelle', json=dict(name=project['name'], style_anchor_artifact_id=reference['id']))
    seeded = client.post('/api/world/preview-plan', json=dict(project_id='runavelle', name='Field', prompt='')).json()
    assert seeded['plan']['grass_color'] != plain['grass_color'] and seeded['plan']['road_color'] == plain['road_color']
    assert any('style palette' in a for a in seeded['plan']['assumptions']) and seeded['enqueued_jobs'] == 0 and not jobs.listing()


@pytest.mark.parametrize('text,subject,observed,expected', [
    ('tôi muốn model là boss 1 con rồng khổng lồ đỏ, phù hợp với các công trình này', 'giant red dragon boss', 'stone watchtower with a blue slate roof', True),
    ('tôi muốn model là 1 kiếm sĩ với khiên, phù hợp với các công trình này', 'swordsman with a shield', 'top-down fantasy map with roads', True),
    ('A knight that matches these buildings', 'knight', 'castle keep', True),
    ('Make this watchtower into a 3D model', 'stone watchtower', 'stone watchtower with a wooden roof', False),
    ('Build a giant red dragon', 'giant red dragon', 'red dragon with spread wings', False),
])
def test_style_intent_guard_keeps_a_different_subject_from_rebuilding_the_reference(text, subject, observed, expected):
    from engines.intent_adapter import style_intent
    class Answer: requested_subject_en = subject; reference_description_en = observed
    assert style_intent(text, Answer) is expected


def test_map_preview_matches_an_explicit_reference_image(client):
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Swordsman', prompt='A swordsman')).json()
    reference = client.post('/api/import/concept', params=dict(project_id='runavelle', asset_id=model['id']), files=dict(file=('swordsman.png', _png(colour=(150, 115, 70))))).json()
    plain = client.post('/api/world/preview-plan', json=dict(project_id='runavelle', name='Field', prompt='')).json()['plan']
    matched = client.post('/api/world/preview-plan', json=dict(project_id='runavelle', name='Field', prompt='map for this swordsman', style_reference_id=reference['id'])).json()['plan']
    assert matched['road_color'] != plain['road_color'] and any('chosen reference image' in a for a in matched['assumptions']) and not jobs.listing()


def test_effect_plan_inherits_a_saturated_project_accent_but_not_a_muted_one(client):
    plain = client.post('/api/fx/plan', json=dict(project_id='runavelle', name='Slash', prompt='fire sword slash')).json()
    assert plain['recipe']['accent_color'] is None
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Holder', prompt='Anchor')).json()
    reference = client.post('/api/import/concept', params=dict(project_id='runavelle', asset_id=model['id']), files=dict(file=('anchor.png', _png(colour=(30, 200, 220))))).json()
    project = client.get('/api/projects').json()[0]
    client.post('/api/projects/runavelle', json=dict(name=project['name'], style_anchor_artifact_id=reference['id']))
    planned = client.post('/api/fx/plan', json=dict(project_id='runavelle', name='Slash', prompt='fire sword slash')).json()
    assert planned['recipe']['element'] == 'fire' and planned['recipe']['accent_color'].startswith('#') and planned['recipe']['accent_strength'] <= 0.5
    assert planned['provenance']['accent_color']['kind'] == 'inferred' and planned['enqueued_jobs'] == 0
    override = client.post('/api/fx/plan', json=dict(project_id='runavelle', name='Slash', prompt='fire sword slash', overrides=dict(accent_color='#ff0000', accent_strength=0.1))).json()
    assert override['recipe']['accent_color'] == '#ff0000' and override['provenance']['accent_color']['kind'] == 'explicit'


def test_a_vietnamese_count_of_one_is_an_article_not_a_dropped_number():
    from engines.intent_adapter import numeric_values
    import re
    source, translated = 'boss 1 con rồng khổng lồ đỏ', 'a giant red dragon boss'
    missing = numeric_values(source) - numeric_values(translated)
    assert missing == {'1'} and re.search(r'\b(?:a|an|one|single)\b', translated)


def test_fallback_without_the_model_never_rebuilds_a_reference_the_user_asked_to_match():
    from engines.intent_adapter import MATCH_PHRASES
    assert MATCH_PHRASES.search('tôi muốn model là 1 kiếm sĩ với khiên, phù hợp với các công trình này')
    assert not MATCH_PHRASES.search('biến tấm ảnh tháp canh này thành model 3D')


def test_guard_also_covers_a_none_role_when_an_image_was_supplied(tmp_path, monkeypatch):
    """Regression (real S1 run): Qwen answered reference_role='none' for a dragon + watchtower image; aggregation defaulted to source."""
    import json as _json
    from engines import intent_adapter, local_semantics
    monkeypatch.setattr(store, 'DATA', tmp_path)
    image = tmp_path / 'tower.png'; image.write_bytes(_png())
    reference = dict(id='ref', relative_path='tower.png', sha256=store.digest(image))
    monkeypatch.setattr(intent_adapter, 'model', lambda: dict(name='fixture', digest='fixture'))
    monkeypatch.setattr(local_semantics, 'probe', lambda: dict(models=[dict(name='fixture', digest='fixture')]))
    answers = iter([
        dict(translated_prompt_en='I want the model to be a giant red dragon boss, matching these buildings', requested_subject_en='giant red dragon boss',
             reference_role='none', reference_description_en='', style_traits=[], appearance=dict(colors=['ivory'], materials=['stone'], surface_treatment='painted', rendering_aesthetic='stylized'), warnings=[]),
        dict(description_en='A giant red dragon boss with crimson scales and spread wings.', inferred_ordinary_details=[]),
    ])
    monkeypatch.setattr(local_semantics, 'request', lambda path, payload=None, timeout=3: dict(done=True, done_reason='stop', message=dict(content=_json.dumps(next(answers)))))
    result = intent_adapter.interpret('tôi muốn model là boss 1 con rồng khổng lồ đỏ, phù hợp với các công trình này', [reference], {}, 'auto', lambda message: None)
    assert result['reference_role'] == 'style' and 'dragon' in result['generation_prompt_en']


def test_incomplete_planning_keeps_the_english_translation_instead_of_untranslated_text(tmp_path, monkeypatch):
    import json as _json
    from engines import intent_adapter, local_semantics
    monkeypatch.setattr(intent_adapter, 'model', lambda: dict(name='fixture', digest='fixture'))
    monkeypatch.setattr(local_semantics, 'probe', lambda: dict(models=[dict(name='fixture', digest='fixture')]))
    interpretation = dict(translated_prompt_en='A giant red dragon, final boss', requested_subject_en='giant red dragon', reference_role='none', reference_description_en='',
                          style_traits=[], appearance=dict(colors=[], materials=[], surface_treatment='', rendering_aesthetic=''), warnings=[])
    replies = iter([dict(done=True, done_reason='stop', message=dict(content=_json.dumps(interpretation))),
                    dict(done=True, done_reason='length', message=dict(content='{')), dict(done=True, done_reason='length', message=dict(content='{'))])
    monkeypatch.setattr(local_semantics, 'request', lambda path, payload=None, timeout=3: next(replies))
    result = intent_adapter.interpret('Một con rồng đỏ khổng lồ, boss cuối màn', [], {}, 'auto', lambda message: None)
    assert result['generation_prompt_en'].startswith('A giant red dragon') and 'rồng' not in result['generation_prompt_en']
