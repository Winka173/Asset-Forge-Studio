"""Opt-in clarifying questions for vague prompts (local Qwen3-VL, CPU). Only asked when the user allowed questions."""
import re

from pydantic import BaseModel, ConfigDict, Field

from apps.api.concept_rank import requested_hues
from apps.api.size_rules import SCALE
from engines import intent_adapter, local_semantics

LIMIT = 10


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=3, max_length=300)
    options: list[str] = Field(min_length=2, max_length=4)
    importance: int = Field(ge=1, le=10)


class Questions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    questions: list[Question] = Field(default_factory=list, max_length=LIMIT)


def vietnamese(text):
    return bool(re.search(r'[ăâđêôơưạảãáàặẳẵắằậẩẫấầẹẻẽéèệểễếềịỉĩíìọỏõóòộổỗốồợởỡớờụủũúùựửữứừỵỷỹýỳ]', text, re.I))


def ask(prompt, project_style):
    selected = intent_adapter.model()
    language = 'Vietnamese' if vietnamese(prompt) else 'English'
    # A few words name only the subject; a longer request usually fixes most visual traits already.
    if len(prompt.split()) < 12:
        amount = 'This short request names only the subject and IS vague: ask at least 4 questions (e.g. "a dragon" -> dragon type, main colours, size/role, pose, distinctive features). '
    else:
        amount = 'This request is detailed: ask only about visually important traits it truly leaves open, usually 0-3 questions; return an empty list when nothing important is missing. '
    answer = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=Questions.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=4096, num_predict=1500, num_gpu=0, num_thread=8), messages=[dict(role='system', content=(
            'You help a game artist turn a short request into ONE game-ready 3D asset. List the questions whose answers would visibly change the result '
            'and that the request does not already answer: e.g. subject variant or species, main colours, materials, size class or role (boss, common enemy, prop), '
            'age or condition, era or culture, distinctive parts, pose for characters. '
            'Never ask about camera, background, file format, polycount or engine. Never ask what the request already states. '
            f'At most {LIMIT} questions, most important first (importance 10 = changes the silhouette). '
            + amount +
            f'Write question and options in {language}; 2-4 short concrete options each; ids are short snake_case words.')),
            dict(role='user', content=f'Request: {prompt}\nProject style: {project_style or "none"}')]), timeout=600)
    found = Questions.model_validate_json(answer['message']['content']).questions
    unique = [q for q in {q.id: q for q in found}.values() if not already_stated(q, prompt)]
    return [q.model_dump() for q in sorted(unique, key=lambda q: -q.importance)][:LIMIT]


STATED = [  # (question topic, request words that already answer it); the small model often asks anyway
    (re.compile(r'colou?r|màu', re.I), lambda text: bool(requested_hues(text))),
    (re.compile(r'size|scale|role|kích thước|cỡ|vai trò', re.I), lambda text: any(re.search(pattern, text, re.I) for pattern, _ in SCALE)),
]


def already_stated(question, prompt):
    topic = question.id + ' ' + question.question
    return any(asks.search(topic) and stated(prompt) for asks, stated in STATED)


def details(questions, answers):
    """Answered questions become explicit request details; skipped ones are left for the interpreter to decide."""
    lines = [f"{q['question']} {answers[q['id']].strip()}" for q in questions if answers.get(q['id'], '').strip()]
    return ('\nUser-confirmed details:\n- ' + '\n- '.join(lines)) if lines else ''
