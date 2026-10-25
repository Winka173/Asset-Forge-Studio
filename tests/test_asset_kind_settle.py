from apps.api import clarify


def item(**extra):
    return dict(asset_id='missing-asset', name='Old castle', prompt='Old stone castle with four towers', **extra)


def test_a_contradicted_type_is_asked_when_questions_are_on_and_auto_chosen_when_off():
    asked = item(kind='vehicle', allow_questions=True, interpret_prompt=True)
    clarify.settle_kind(asked)
    assert asked['kind'] == 'vehicle' and 'kind_note' not in asked
    question = clarify.with_kind_question([dict(id='q1', question='Colour?', options=['Red'])], asked)[0]
    assert question['id'] == 'asset_kind' and question['kind_options'] == ['building', 'vehicle']
    silent = item(kind='vehicle')
    clarify.settle_kind(silent)
    assert silent['kind'] == 'building' and silent['kind_confirmed'] and silent['kind_note']['chosen'] == 'vehicle'
    # A confirmed choice, Auto, a matching choice or a description without a clear subject word is left alone.
    for kept in (item(kind='vehicle', kind_confirmed=True), item(kind='auto'), item(kind='building'), dict(asset_id='x', name='Glider', prompt='Elven glider', kind='vehicle')):
        before = dict(kept); clarify.settle_kind(kept)
        assert kept['kind'] == before['kind'] and 'kind_note' not in kept
