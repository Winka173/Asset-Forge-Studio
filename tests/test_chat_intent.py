from engines.chat_intent import Message, merge


def label(n, kind, text='', earlier=None, version=None):
    return Message(message=n, kind=kind, instruction=text, earlier_message=earlier, version=version)


def test_corrections_replace_and_cancellations_drop_earlier_messages():
    result = merge([label(1, 'new_change', 'Add water inside'), label(2, 'corrects_earlier_message', 'Add purple water inside', earlier=1),
                    label(3, 'new_change', 'Make it taller'), label(4, 'cancels_earlier_message', earlier=3), label(5, 'not_a_change')], [])
    assert result == dict(revert_to_version=None, instructions=['Add purple water inside'])


def test_taking_back_a_version_returns_to_the_one_before_it_and_keeps_new_edits():
    applied = [2, 3]
    assert merge([label(1, 'takes_back_version', version=3), label(2, 'new_change', 'Make the walls taller')], applied) == dict(revert_to_version=2, instructions=['Make the walls taller'])
    assert merge([label(1, 'takes_back_version', version=2)], applied)['revert_to_version'] == 1
    # A version outside the current chain cannot be taken back.
    assert merge([label(1, 'takes_back_version', version=7)], applied)['revert_to_version'] is None
