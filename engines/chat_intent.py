"""What the user wants from a run of prompt-chat messages, read together by the local language model (CPU only).

The model labels each message (a new change, a correction of an earlier message, a cancellation, or taking back an applied
version); the merge itself is deterministic: corrections replace the message they correct, cancellations drop it, and
taking back a version goes back to the version before it instead of editing again. Measured with one combined answer
instead: the local model wrote the right summary but left the revert or the remaining edits empty.
The caller falls back to the raw messages when the model is unavailable.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import intent_adapter, local_semantics


class Message(BaseModel):
    model_config = ConfigDict(extra='forbid')
    message: int = Field(ge=1)
    kind: Literal['new_change', 'corrects_earlier_message', 'cancels_earlier_message', 'takes_back_version', 'not_a_change']
    earlier_message: int | None = None
    version: int | None = None
    instruction: str = Field(default='', max_length=400)


class Reading(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=300)
    messages: list[Message] = Field(min_length=1, max_length=20)


SYSTEM = (
    'A user edits ONE 3D game asset by chatting; every version after v1 was made by one change. Label EVERY new message '
    '(any language, ignore typos):\n'
    '- new_change: asks for a new edit. instruction = short English imperative edit keeping exact numbers, colours and names.\n'
    '- corrects_earlier_message: changes or adds detail to what an earlier NEW message asked. earlier_message = its number; '
    'instruction = the complete corrected edit (the earlier request with this correction applied).\n'
    '- cancels_earlier_message: withdraws an earlier NEW message. earlier_message = its number.\n'
    '- takes_back_version: rejects a change already made in a listed version (undo, go back, remove the X you added, the X looks bad). '
    'version = that version number. If the same message also asks for something new, label the new part as a separate entry with '
    'the same message number and kind new_change.\n'
    '- not_a_change: thanks, questions, chatter.\n'
    'summary: one short sentence in the user\'s language saying what will happen.\n'
    'Examples:\n'
    'Versions v1. Messages: 1. add a flag on top 2. make it blue -> [1 new_change "Add a flag on top"], [2 corrects_earlier_message 1 "Add a blue flag on top"].\n'
    'Versions v1, v2 Add a chimney. Messages: 1. I do not want the chimney -> [1 takes_back_version 2].\n'
    'Versions v1, v2 Add a chimney, v3 Make the door wider. Messages: 1. the wide door looks wrong 2. add ivy on the walls '
    '-> [1 takes_back_version 3], [2 new_change "Add ivy on the walls"].\n'
    'Versions v1. Messages: 1. make it taller 2. forget that, just add windows -> [1 new_change "Make it taller"], '
    '[2 cancels_earlier_message 1], [2 new_change "Add windows"].')


def interpret(messages, history, current_version):
    """messages: waiting texts in order; history: [(version number, change that made it)] oldest first, leading to the current version.
    Returns the version to go back to (None to stay), the instructions to apply after it, and a summary."""
    selected = intent_adapter.model()
    versions = '\n'.join(['v1: the original model'] + [f'v{n}: {p}' for n, p in history])
    answer = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=Reading.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=4096, num_predict=900, num_gpu=0, num_thread=8), messages=[
            dict(role='system', content=SYSTEM),
            dict(role='user', content=f'Versions:\n{versions}\nCurrent version: v{current_version}\nNew messages:\n' +
                 '\n'.join(f'{i + 1}. {m}' for i, m in enumerate(messages)))]), timeout=300)
    reading = Reading.model_validate_json(answer['message']['content'])
    return dict(merge(reading.messages, [n for n, _ in history]), summary=reading.summary, model=selected['name'])


def merge(labels, applied):
    """Deterministic merge of labelled messages; applied = version numbers in the current chain (v1 is the original)."""
    edits = {}; undone = []  # message number -> instructions, in message order
    for label in labels:
        text = label.instruction.strip()
        if label.kind in ('corrects_earlier_message', 'cancels_earlier_message') and label.earlier_message:
            edits.pop(label.earlier_message, None)
        if label.kind in ('new_change', 'corrects_earlier_message') and text:
            edits.setdefault(label.message, []).append(text)
        if label.kind == 'takes_back_version' and label.version in applied:
            undone.append(label.version)
    back = None
    if undone:
        at = applied.index(min(undone)); back = applied[at - 1] if at else 1
    return dict(revert_to_version=back, instructions=[t for n in sorted(edits) for t in edits[n]])
