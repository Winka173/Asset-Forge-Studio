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
    prompt, _ = compose(LONG, '', None)
    assert LONG.strip() in prompt
    assert COMPOSITION_POLICY == 4


def test_policy_three_output_is_unchanged_for_locked_configs():
    prompt, _ = compose('One complete tower.', 'warm stone', None, policy=3)
    assert prompt == ('One complete tower.\nVisual style: warm stone\nA single standalone 3D game asset, zoomed out, three-quarter view, '
                      'full object centered with clear margin, plain neutral studio background.')


def test_subject_anchor_is_bounded():
    assert len(subject_anchor(' '.join(['word'] * 80))).__le__(24 * 5)
    assert subject_anchor('Short tower. More text.') == 'Short tower'
