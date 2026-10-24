"""Opt-in "Allow questions": ask about missing visual details before prompt analysis; off means Auto decides."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import jobs, store
from engines import clarify

router = APIRouter(prefix='/api/batches')


def execute(job, folder):
    payload = job['payload']; warnings = []
    try: questions = clarify.ask(payload['prompt'], payload.get('project_style', ''))
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
    if (item.get('clarification') or {}).get('state') in ('answered', 'none'): return False
    done = [j for j in current if j['payload']['kind'] == 'prompt_questions' and j['status'] in jobs.TERMINAL]
    if not done:
        if not any(j['payload']['kind'] == 'prompt_questions' for j in current):
            snapshot = value.get('style_snapshot') or {}
            jobs.enqueue(dict(kind='prompt_questions', engine='qwen3_vl_local_cpu', project_id=value['project_id'], asset_id=item['asset_id'], batch_id=value['id'],
                              batch_attempt=item['attempt'], prompt=item.get('resolved_prompt') or item['prompt'], project_style=style_summary(snapshot), use_gpu=False, timeout_seconds=900, priority=item.get('priority', 0)))
        auto.update(status='queued', stage='Prepare questions about the request / local CPU'); return True
    path = store.DATA / 'jobs' / done[-1]['id'] / 'questions.json'
    questions = json.loads(path.read_text(encoding='utf-8'))['questions'] if path.is_file() else []
    if not questions:
        item['clarification'] = dict(state='none', questions=[]); return False
    item['clarification'] = dict(state='waiting', questions=questions, asked_at=(item.get('clarification') or {}).get('asked_at') or store.now())
    auto.update(status='waiting_for_answers', stage='Waiting for your answers (other assets continue)'); return True


def analysis_text(item):
    """The immutable original prompt plus the user's confirmed answers; this is what prompt analysis reads."""
    state = item.get('clarification') or {}
    return item['prompt'] + (clarify.details(state.get('questions', []), state.get('answers', {})) if state.get('state') == 'answered' else '')


class Answers(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    # Answer up to this question; it and every later question are left for AI to decide.
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
        answers = {k: v[:500] for k, v in body.answers.items() if k in ids[:cut] and v.strip()}
        state.update(state='answered', answers=answers, ai_decides=ids[cut:] + [k for k in ids[:cut] if k not in answers], answered_at=store.now())
        batch.save(value)
    automation.advance(identifier)
    return state


@router.get('/questions/pending')
def pending(project_id: str | None = None):
    with store.connect() as db: values = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM batches WHERE ? IS NULL OR project_id=?', (project_id, project_id))]
    return [dict(batch_id=v['id'], asset_id=i['asset_id'], name=i['name'], prompt=i['prompt'], questions=i['clarification']['questions'], asked_at=i['clarification'].get('asked_at'))
            for v in values for i in v['items'] if (i.get('clarification') or {}).get('state') == 'waiting' and not i.get('production_cancelled')]
