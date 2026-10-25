from engines.concept_prompt import COMPOSITION_POLICY, FRAMING, compose, subject_anchor


LONG = ('A fortified stone castle with a central keep and four corner towers. '
        + ' '.join(f'Detail clause {n} describing crenellations, banners and timber hoardings.' for n in range(60)))


def test_policy_four_front_loads_subject_framing_and_style():
    prompt, negative = compose(LONG, 'ivory limestone; midnight blue slate; aged bronze', 'Maximum')
    head = prompt.split('\n', 1)[0]
    assert head.startswith('A fortified stone castle with a central keep and four corner towers')
    assert FRAMING in head and 'ivory limestone' in head
    assert len(head.split()) <= 60  # stays inside the first 75-token CLIP window for ordinary words
    assert 'multiple views' in negative


def test_policy_four_keeps_every_description_word():
    prompt, _ = compose(LONG, '', None, policy=4)
    assert LONG.strip() in prompt
    assert COMPOSITION_POLICY == 10


def test_policy_three_output_is_unchanged_for_locked_configs():
    prompt, _ = compose('One complete tower.', 'warm stone', None, policy=3)
    assert prompt == ('One complete tower.\nVisual style: warm stone\nA single standalone 3D game asset, zoomed out, three-quarter view, '
                      'full object centered with clear margin, plain neutral studio background.')


def test_subject_anchor_is_bounded():
    assert len(subject_anchor(' '.join(['word'] * 80))).__le__(24 * 5)
    assert subject_anchor('Short tower. More text.') == 'Short tower'


MANIFEST = ('# BLD_MANA_WELL_T2_Runic_Conduit — MANA WELL T2 Runic Conduit\n\n**Status:** proposed art contract.\n'
            '## 2. Visual identity\nShared palette text.\nMANA WELL T2 Runic Conduit. Tiered hexagonal mana fountain with six runic obelisks. True 3D structure.\n')


def test_policy_five_anchors_a_manifest_heading_on_its_restated_description():
    assert subject_anchor(MANIFEST) == 'MANA WELL T2 Runic Conduit: Tiered hexagonal mana fountain with six runic obelisks'
    assert subject_anchor(MANIFEST, policy=4) == 'MANA WELL T2 Runic Conduit'
    tree = '# BIO_EMBER_Tree_01 — Ember Tree_01\nEmber Tree_01. Medium fantasy tree with a complete trunk.'
    assert subject_anchor(tree) == 'Ember Tree 01: Medium fantasy tree with a complete trunk'
    assert compose(MANIFEST)[0].startswith('MANA WELL T2 Runic Conduit: Tiered hexagonal mana fountain')


def test_policy_six_conditions_manifest_concepts_only_on_the_visual_description():
    prompt, _ = compose(MANIFEST + '## 6. Export contract\nDeliver LOD0/LOD1 and FBX; Meshy pricing notes.\n', 'warm stone', 'Maximum')
    assert 'Tiered hexagonal mana fountain with six runic obelisks. True 3D structure.' in prompt
    assert 'Meshy' not in prompt and 'Status' not in prompt and 'Shared palette text' not in prompt
    assert compose(MANIFEST, policy=5)[0].count('Shared palette text') == 1  # locked policy 5 output keeps the full manifest
    bounded = compose(LONG)[0]
    assert 'Detail clause 59' not in bounded and len(bounded.splitlines()[1].split()) <= 160  # long rewrites stay within ~3 windows
    assert 'A fortified stone castle with a central keep and four corner towers.' in bounded


def test_directives_survive_description_bounding():
    prompt, _ = compose(LONG, 'warm stone', 'Maximum', directives=['Colors: navy, ivory.', 'Pull the camera back.'])
    assert 'Colors: navy, ivory.' in prompt and 'Pull the camera back.' in prompt and 'Detail clause 59' not in prompt
    legacy, _ = compose('One tower.', '', None, policy=5, directives=['Pull the camera back.'])
    assert legacy.endswith('One tower.\nPull the camera back.')  # earlier policies kept appending them to the text


def test_repair_framing_is_subject_neutral():
    from apps.api.concept_guard import REPAIR_FRAMING
    assert 'roof' not in REPAIR_FRAMING and 'wall' not in REPAIR_FRAMING


def test_characters_and_creatures_get_a_rig_friendly_pose_but_buildings_and_posed_requests_do_not():
    from engines.concept_prompt import rig_class
    assert rig_class('Giant red dragon, full silhouette') == 'creature' and rig_class('Stone golem boss') == 'creature'
    assert rig_class('A knight with a shield') == 'humanoid' and rig_class('Kiếm sĩ với khiên') == 'humanoid' and rig_class('Bone Spearman') == 'humanoid'
    for text in ('Archer tower T3', 'Statue of a knight', 'A wooden supply barrel', 'A knight swinging his sword', 'Rồng đang bay'):
        assert rig_class(text) is None, text
    head = compose('A knight with a shield. Blue tabard.', 'warm stone', 'Maximum')[0].split('\n', 1)[0]
    assert 'A-pose with both arms held away from the body' in head and 'three-quarter view' not in head
    assert 'A-pose' not in compose('A knight with a shield.', '', None, policy=6)[0]  # locked older policy unchanged


def test_english_regexes_survive_escaping():
    from apps.api.concept_rank import requested_hues
    from engines.intent_adapter import MATCH_PHRASES
    assert requested_hues('a giant red dragon') == [(345, 15)] and requested_hues('navy blue knight') == [(200, 250)]
    assert MATCH_PHRASES.search('A knight that matches these buildings') and MATCH_PHRASES.search('same style as this')
    assert not MATCH_PHRASES.search('turn this watchtower photo into a model')


def test_full_body_characters_render_in_portrait_and_creatures_in_landscape(tmp_path, monkeypatch, qa_project):
    from fastapi.testclient import TestClient
    from apps.api import store, jobs, studio
    from apps.api.main import app
    from engines.concept_adapter import CONCEPT_ADAPTER
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); client = TestClient(app)
    monkeypatch.setattr(type(CONCEPT_ADAPTER), 'installed', property(lambda self: True))
    for name, prompt, expected in (('Knight', 'A knight with a shield', (832, 1216)), ('Dragon', 'A giant red dragon', (1216, 832)), ('Barrel', 'A wooden barrel', (1024, 1024))):
        asset = client.post('/api/assets', json=dict(project_id='runavelle', name=name, prompt=prompt)).json()
        job = studio.concept(studio.ConceptInput(asset_id=asset['id'], request_id=f'aspect-{name}-0001', prompt=prompt, quality='Maximum'))
        assert (job['payload']['width'], job['payload']['height']) == expected and job['payload']['effective_config']['width'] == expected[0]


def test_buildings_are_drawn_at_human_scale_unless_giant():
    from engines.concept_prompt import HUMAN_SCALE, building_scale
    scale, negative = building_scale('Merchant house with a shop front')
    assert scale == HUMAN_SCALE and 'castle' in negative and 'ruins' in negative
    assert 'castle' not in building_scale('Castle keep with towers')[1]
    assert building_scale('Giant temple for titans')[0] == ''
    assert 'ruins' not in building_scale('Ruined temple')[1]
    assert building_scale('Wooden barrel') == ('', building_scale('Wooden barrel')[1]) and 'ruins' not in building_scale('Wooden barrel')[1]


def test_asset_kind_detects_and_an_explicit_choice_overrides_the_subject_words():
    from engines.asset_kind import detect, effective
    from engines.concept_prompt import HUMAN_SCALE, rig_for
    assert [detect(t) for t in ('Hero knight holding a sword and shield', 'Red dragon boss', 'Stone archer tower', 'Wooden barrel', 'Siege catapult', 'Oak tree')] == \
        ['character', 'creature', 'building', 'prop', 'vehicle', 'nature']
    assert effective('auto', 'Wooden barrel') == 'prop' and effective('building', 'Wooden barrel') == 'building'
    # A giant boss chosen as a creature gets the creature pose; a chosen building gets the human-scale door rule
    # even when its name has no building word, but a chosen prop never does.
    assert rig_for('Colossal stone guardian', 'creature') == 'creature' and rig_for('Knight statue', 'prop') is None
    assert HUMAN_SCALE in compose('Mana Dwelling of the arcane order', kind='building')[0]
    assert HUMAN_SCALE not in compose('Merchant house', kind='prop')[0]
