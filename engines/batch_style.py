"""One shared visual style for every asset of a batch, written once by the local language model (CPU).

Without it each item is drawn from its own short description and the set comes out as unrelated styles (measured on a 2D
batch of knight, warrior, archer and mage: chibi, flat vector, cartoon outline and semi-realistic). The sentence describes the
look only (never a subject) so every item's concept gets the same medium, outline, shading, palette and proportions.
"""
from pydantic import BaseModel, ConfigDict, Field
from . import intent_adapter, local_semantics


class Style(BaseModel):
    model_config = ConfigDict(extra='forbid')
    medium: str = Field(min_length=1, max_length=80)
    outline_and_shading: str = Field(min_length=1, max_length=120)
    palette_and_proportions: str = Field(min_length=1, max_length=140)


SYSTEM = (
    'A game batch needs ONE visual style shared by all its assets so they look like one set. Read the user\'s request and the asset '
    'names. If the user already described a style (words like cartoon, low-poly, painted, pixel, realistic, colours), keep it exactly. '
    'Otherwise choose one coherent style that suits the assets and a stylized game. Describe the LOOK only, in English, never a '
    'subject: medium (e.g. flat cel-shaded 2D illustration), outline and shading, palette mood, and overall proportion style (e.g. chunky or '
    'slender, head-to-body ratio). Never describe anatomy, muscles, clothing, poses or any detail that belongs to one asset.')


def derive(master_prompt, names, project_style=''):
    selected = intent_adapter.model()
    answer = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=Style.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=4096, num_predict=300, num_gpu=0, num_thread=8), messages=[
            dict(role='system', content=SYSTEM),
            dict(role='user', content=f'Request:\n{master_prompt[:1500]}\nAssets: {", ".join(names[:40])}\nProject style: {project_style or "none"}')]), timeout=300)
    v = Style.model_validate_json(answer['message']['content'])
    return f'{v.medium}; {v.outline_and_shading}; {v.palette_and_proportions}'
