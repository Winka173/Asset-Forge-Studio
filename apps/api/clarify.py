"""Opt-in "Allow questions": ask about missing visual details before prompt analysis; off means Auto decides."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import jobs, store
from engines import clarify

router = APIRouter(prefix='/api/batches')
# A follow-up round runs only when the user answered without handing the rest to AI.
MAX_ROUNDS = 3


def execute(job, folder):
    payload = job['payload']; warnings = []
    try: questions = clarify.ask(payload['prompt'], payload.get('project_style', ''), payload.get('asked', []))
    except Exception as exc:  # Questions are optional; Auto continues and decides.
        questions = []; warnings.append('Questions unavailable; Auto decides: ' + str(exc)[:300])
    target = folder / 'questions.json'; temporary = folder / 'questions.json.part'
    temporary.write_text(json.dumps(dict(questions=questions, warnings=warnings), ensure_ascii=False, indent=2), encoding='utf-8'); temporary.replace(target)
    jobs.transition(job['id'], 'GENERATED'); jobs.transition(job['id'], 'VALIDATING'); jobs.transition(job['id'], 'REVIEW_REQUIRED')


def style_summary(snapshot):
    return '; '.join(str(snapshot.get(k)) for k in ('description', 'material_language', 'default_style') if snapshot.get(k))[:1500]


def admit(value, item, current, auto):
    """True while this asset waits for its questions (or the user's answers). Other assets keep running."""
    if not item.get('allow_questions') or not item.get('interpret_prompt'): return False
    state = item.get('clarification') or {}
    if state.get('state') in ('answered', 'none'): return False
    if state.get('state') == 'waiting': auto.update(status='waiting_for_answers', stage='Waiting for your answers (other assets continue)'); return True
    round_ = state.get('round', 1)
    mine = [j for j in current if j['payload']['kind'] == 'prompt_questions' and j['payload'].get('round', 1) == round_]
    done = [j for j in mine if j['status'] in jobs.TERMINAL]
    if not done:
        if not mine:
            snapshot = value.get('style_snapshot') or {}
            jobs.enqueue(dict(kind='prompt_questions', engine='qwen3_vl_local_cpu', project_id=value['project_id'], asset_id=item['asset_id'], batch_id=value['id'],
                              batch_attempt=item['attempt'], prompt=(item.get('resolved_prompt') or item['prompt']) + confirmed(state), round=round_,
                              asked=[q['question'] for q in state.get('asked', [])], project_style=style_summary(snapshot), use_gpu=False, timeout_seconds=900, priority=item.get('priority', 0)))
        auto.update(status='queued', stage=('Prepare questions' if round_ == 1 else f'Check the answers (round {round_})') + ' / local CPU'); return True
    path = store.DATA / 'jobs' / done[-1]['id'] / 'questions.json'
    asked = {q['id'] for q in state.get('asked', [])} | {q['question'].casefold() for q in state.get('asked', [])}
    questions = [q for q in (json.loads(path.read_text(encoding='utf-8'))['questions'] if path.is_file() else []) if q['id'] not in asked and q['question'].casefold() not in asked]
    if not questions:
        state.update(state='answered' if state.get('asked') else 'none', questions=[]); item['clarification'] = state; return False
    item['clarification'] = state | dict(state='waiting', round=round_, questions=questions, asked_at=store.now())
    auto.update(status='waiting_for_answers', stage='Waiting for your answers (other assets continue)'); return True


def confirmed(state):
    return clarify.details(state.get('asked', []), state.get('answers', {}))


def analysis_text(item):
    """The immutable original prompt plus every answer the user confirmed; this is what prompt analysis reads."""
    state = item.get('clarification') or {}
    return item['prompt'] + (confirmed(state) if state.get('state') == 'answered' else '')


class Answers(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    # Questions the user handed to AI one by one ("Let AI decide"); the others keep their answers.
    ai_decides: list[str] = Field(default_factory=list)
    # Older clients: this question and every later one are left for AI.
    ai_decides_from: str | None = None


@router.post('/{identifier}/items/{asset_id}/answers')
def answer(identifier: str, asset_id: str, body: Answers):
    from . import automation, batch
    with batch.LOCK:
        value = batch.batch(identifier); item = next((i for i in value['items'] if i['asset_id'] == asset_id), None)
        state = (item or {}).get('clarification') or {}
        if not item or state.get('state') != 'waiting': raise HTTPException(409, 'This asset is not waiting for answers.')
        ids = [q['id'] for q in state['questions']]
        cut = ids.index(body.ai_decides_from) if body.ai_decides_from in ids else len(ids)
        answers = {k: v[:500] for k, v in body.answers.items() if k in ids[:cut] and k not in body.ai_decides and v.strip()}
        delegated = ids[cut:] + [k for k in ids[:cut] if k not in answers]
        state.update(asked=state.get('asked', []) + state['questions'], answers=state.get('answers', {}) | answers,
                     ai_decides=state.get('ai_decides', []) + delegated, questions=[], answered_at=store.now())
        # Another round only checks real answers; handing anything to AI ends the questions.
        followup = bool(answers) and not body.ai_decides_from and state.get('round', 1) < MAX_ROUNDS
        state.update(state='followup', round=state.get('round', 1) + 1) if followup else state.update(state='answered')
        batch.save(value)
    automation.advance(identifier)
    return state


@router.get('/questions/pending')
def pending(project_id: str | None = None):
    with store.connect() as db: values = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches WHERE ? IS NULL OR project_id=?', (project_id, project_id))]
    return [dict(batch_id=v['id'], asset_id=i['asset_id'], name=i['name'], prompt=i['prompt'], questions=i['clarification']['questions'], asked_at=i['clarification'].get('asked_at'))
            for v in values for i in v['items'] if (i.get('clarification') or {}).get('state') == 'waiting' and not i.get('production_cancelled')]
