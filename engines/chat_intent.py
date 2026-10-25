"""What the user wants next from prompt-chat messages, decided by a local language model (CPU only).

One question with the whole context: the version tree (what made each version, from which one) and the recent
conversation (the user's messages and the earlier readings). The model answers with the version to continue from and
the edits still to make; code only checks that the version exists. An earlier design labelled each message and merged
the labels with hand-written rules; the 4B vision model mislabelled mixed or repeated requests ("back to v1 and remove
all weapons", "still has weapons, try again") and every fix needed another rule, so the reasoning moved to a stronger
model (now qwen3.6:35b, 8/8 on the measured chat cases).
"""
from pydantic import BaseModel, ConfigDict, Field
from . import intent_adapter, local_semantics



class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Written first so the model reasons about the versions before it commits to the structured answer.
    analysis: str = Field(min_length=1, max_length=600)
    summary: str = Field(min_length=1, max_length=300)
    start_from_version: int = Field(ge=1)
    instructions: list[str] = Field(default_factory=list, max_length=8)


SYSTEM = (
    'You help a user edit ONE 3D game asset through chat. Every version after v1 was made from an earlier version by one change. '
    'A version existing does NOT mean its change looks right: only the user sees the result and judges it. The assistant\'s earlier '
    'replies are claims, not proof: if the user asks again for something the history says is done, the result did not satisfy them, so make the edit again.\n'
    'Read the versions, the conversation so far and the new messages, then decide what happens next:\n'
    '- analysis: two or three short sentences: what the user wants now, which version is the right base, and what edits remain.\n'
    '- start_from_version: the version the next edits start from. The current version, unless the user goes back to a version '
    '(use that number) or no longer wants a change that a listed version made: then start from the version that change was made '
    'from and do NOT write an edit that removes it (going back removes it exactly and without loss).\n'
    '- instructions: every edit still to make from that version, ALWAYS written in English (translate the user\'s words) as short imperatives keeping exact numbers, colours and '
    'names. Merge messages about the same thing; later messages override earlier ones; drop what the user cancelled. When the user '
    'repeats a request or says it is not done, not enough, or to try again, the edit is needed again: include it (stronger if it was '
    'not enough). Empty when the user only goes back, undoes, thanks or asks a question.\n'
    '- summary: one short sentence in the user\'s language saying what will happen next.')


model = intent_adapter.model  # the app's one managed local model


def interpret(messages, history, current_version, conversation=()):
    """messages: new texts in order; history: [(version, change, made from version)] of the current lineage, oldest first;
    conversation: [(role, text)] recent turns. Returns the version to go back to (None to stay), the edits and a summary."""
    selected = model()
    versions = '\n'.join(['v1: the original model'] + [f'v{n}: made from v{parent} by "{change}"' for n, change, parent in history])
    talk = '\n'.join(f'{role}: {text}' for role, text in list(conversation)[-12:]) or '(none)'
    answer = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=Plan.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=6144, num_predict=600, num_gpu=0, num_thread=8), messages=[
            dict(role='system', content=SYSTEM),
            dict(role='user', content=f'Versions:\n{versions}\nCurrent version: v{current_version}\nConversation so far:\n{talk}\nNew messages:\n' +
                 '\n'.join(f'{i + 1}. {m}' for i, m in enumerate(messages)))]), timeout=600)
    plan = Plan.model_validate_json(answer['message']['content'])
    known = {1, *(n for n, _, _ in history)}
    start = plan.start_from_version if plan.start_from_version in known else current_version
    return dict(revert_to_version=start if start != current_version else None, instructions=[i.strip() for i in plan.instructions if i.strip()],
                summary=plan.summary, model=selected['name'])
