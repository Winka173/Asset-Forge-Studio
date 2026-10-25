"""A one-sentence batch request ("4 2D models of a knight, warrior, archer and mage") as one item per named asset.

Runs on the local language model (CPU) only when the strict manifest parser found no list. The model lists exactly the
assets the user named; shared details (2D/3D, style, colours) apply to each. A stated count that disagrees with the
named assets is an error to fix, not something to fill in, so nothing is invented.
"""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from . import intent_adapter, local_semantics


class Item(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=600)
    output: Literal['2d', '3d']


class Split(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stated_count: int | None = Field(default=None, ge=1, le=200)
    items: list[Item] = Field(default_factory=list, max_length=200)


SYSTEM = (
    'The user asks for several game assets in one message (any language, ignore typos). List exactly the assets they name, '
    'in their order, one item each; never add an asset they did not name. Shared details (2D or 3D, style, colours, material, '
    'theme) apply to every item. stated_count: the number of assets they say they want, null if they give none. '
    'name: the user\'s own words for that asset (same language), without 2D/3D. '
    'prompt: one short English sentence: that asset plus only the shared details the user wrote; add no colour, pose, '
    'weapon or detail they did not write, and no filler words. output: 2d only when they ask for 2D, sprites or icons. '
    'Example: "cho tôi 3 model 2d của rồng đỏ, sói, gấu phong cách hoạt hình" -> items: (rồng đỏ, "A red dragon, cartoon style", 2d), '
    '(sói, "A wolf, cartoon style", 2d), (gấu, "A bear, cartoon style", 2d).')
TWO_D = re.compile(r'\b2\s*d\b|\bsprites?\b|\bicons?\b|hình 2d|ảnh 2d|2 chiều', re.I)
COUNT = re.compile(r'\b(\d{1,3})\s*(?:model|mô hình|asset|nhân vật|character|sprite|icon|item|món|cái|con|loại)', re.I)


def split(text):
    selected = intent_adapter.model()
    answer = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=Split.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=4096, num_predict=2000, num_gpu=0, num_thread=8),
        messages=[dict(role='system', content=SYSTEM), dict(role='user', content=text)]), timeout=300)
    value = Split.model_validate_json(answer['message']['content'])
    if not value.items: raise ValueError('No asset was named in the request. Name each asset, or use a bullet list, table, JSON or CSV.')
    written = COUNT.search(text)
    stated = int(written[1]) if written else value.stated_count
    if stated and stated != len(value.items):
        raise ValueError(f'The request asks for {stated} assets but names {len(value.items)} ({", ".join(i.name for i in value.items)}). Name each one; nothing was invented.')
    # 2D or 3D follows the words the user wrote, never a model guess (measured: a crate request came back as 2D).
    output = '2d' if TWO_D.search(text) else '3d'
    clean = lambda prompt: re.sub(r',?\s*\b2\s*d\b', '', prompt, flags=re.I).strip(' ,') or prompt
    return [i.model_dump() | dict(output=output, prompt=clean(i.prompt)) for i in value.items], selected['name']
