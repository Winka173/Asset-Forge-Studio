"""Opt-in questions: vague prompts wait for answers (other assets continue); off means Auto decides."""
import pytest
from fastapi.testclient import TestClient

from apps.api import automation, batch, jobs, store
from apps.api.main import app
from engines import clarify, intent_adapter

QUESTIONS = [dict(id='kind', question='Loại rồng?', options=['Phương Tây', 'Wyvern'], importance=10),
             dict(id='colour', question='Màu chủ đạo?', options=['Đỏ', 'Xanh'], importance=8),
             dict(id='pose', question='Tư thế?', options=['Đứng', 'Bay'], importance=4)]


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project()
    monkeypatch.setattr(intent_adapter, 'available', lambda: True)
    monkeypatch.setattr(clarify, 'ask', lambda prompt, style: QUESTIONS)
    return TestClient(app)


def start(client, allow):
    model = client.post('/api/assets', json=dict(project_id='runavelle', name='Dragon', prompt='tạo 1 con rồng')).json()
    group = client.post('/api/automation/single', json=dict(asset_id=model['id'], request_id=f'clarify-{allow}-0001', allow_questions=allow)).json()['batch_id']
    return model['id'], group


def kinds(asset_id): return [j['payload']['kind'] for j in jobs.listing() if j['payload'].get('asset_id') == asset_id]


def run_questions(asset_id):
    from apps.api.clarify import execute
    job = next(j for j in jobs.listing() if j['payload'].get('asset_id') == asset_id and j['payload']['kind'] == 'prompt_questions')
    folder = store.DATA / 'jobs' / job['id']; folder.mkdir(parents=True, exist_ok=True); jobs.transition(job['id'], 'RUNNING'); execute(job, folder)


def test_questions_wait_for_answers_and_answers_reach_prompt_analysis(client):
    asset_id, group = start(client, True)
    assert kinds(asset_id) == ['prompt_questions']
    run_questions(asset_id); automation.advance(group)
    item = next(i for i in batch.batch(group)['items'] if i['asset_id'] == asset_id)
    assert item['clarification']['state'] == 'waiting' and [q['id'] for q in item['clarification']['questions']] == ['kind', 'colour', 'pose']
    assert item['automation']['status'] == 'waiting_for_answers' and 'prompt_analysis' not in kinds(asset_id)
    # Answer the first question, leave the second blank, let AI decide from the third on.
    state = client.post(f'/api/batches/{group}/items/{asset_id}/answers', json=dict(answers=dict(kind='Phương Tây', colour=' ', pose='Bay'), ai_decides_from='pose')).json()
    assert state['answers'] == dict(kind='Phương Tây') and state['ai_decides'] == ['pose', 'colour']
    analysis = next(j for j in jobs.listing() if j['payload'].get('asset_id') == asset_id and j['payload']['kind'] == 'prompt_analysis')
    assert analysis['payload']['original_prompt'] == 'tạo 1 con rồng\nUser-confirmed details:\n- Loại rồng? Phương Tây'
    assert client.post(f'/api/batches/{group}/items/{asset_id}/answers', json=dict(answers={})).status_code == 409


def test_switch_off_never_asks(client):
    asset_id, _ = start(client, False)
    assert kinds(asset_id) == ['prompt_analysis']


def test_detailed_prompt_without_questions_continues(client, monkeypatch):
    monkeypatch.setattr(clarify, 'ask', lambda prompt, style: [])
    asset_id, group = start(client, True)
    run_questions(asset_id); automation.advance(group)
    assert sorted(kinds(asset_id)) == ['prompt_analysis', 'prompt_questions']


def test_traits_the_request_already_names_are_not_asked():
    from engines.clarify import Question, already_stated
    colour = Question(id='main_colors', question='Màu sắc chủ đạo?', options=['Đỏ', 'Xanh'], importance=10)
    size = Question(id='size_role', question='Kích thước và vai trò?', options=['Boss', 'Prop'], importance=10)
    assert already_stated(colour, 'boss 1 con rồng khổng lồ đỏ') and already_stated(size, 'boss 1 con rồng khổng lồ đỏ')
    assert not already_stated(colour, 'tạo 1 con rồng') and not already_stated(size, 'a dragon')
