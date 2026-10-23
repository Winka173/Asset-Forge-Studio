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
    assert COMPOSITION_POLICY == 6


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
