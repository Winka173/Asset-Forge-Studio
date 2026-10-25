import json
import engines.chat_intent as chat_intent


def answer(monkeypatch, plan):
    monkeypatch.setattr(chat_intent, 'model', lambda: dict(name='qwen3.6:35b', digest='d'))
    monkeypatch.setattr(chat_intent.local_semantics, 'request', lambda path, payload, timeout: dict(message=dict(content=json.dumps(dict(analysis='ok', **plan)))))


def test_the_model_decides_the_version_and_edits_and_code_only_checks_the_version(monkeypatch):
    tree = [(2, 'Remove weapons', 1), (3, 'Remove weapons', 2)]
    answer(monkeypatch, dict(summary='Về v1 rồi bỏ hết vũ khí', start_from_version=1, instructions=['Remove all weapons', ' ']))
    assert chat_intent.interpret(['back về v1 và bỏ hết vũ khí'], tree, 3) == dict(revert_to_version=1, instructions=['Remove all weapons'], summary='Về v1 rồi bỏ hết vũ khí', model='qwen3.6:35b')
    # A version that does not exist in this lineage keeps the current one.
    answer(monkeypatch, dict(summary='x', start_from_version=7, instructions=['Remove all weapons']))
    assert chat_intent.interpret(['thử lại'], tree, 3)['revert_to_version'] is None
