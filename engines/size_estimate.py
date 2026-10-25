"""Real-world size of one asset estimated from its description by the local language model (CPU only).

The asset-type rule (apps/api/size_rules.py) is given as the anchor; the model only departs from it when the request
says so (giant, tiny, three storeys, with a courtyard, ...). Returns metres and a short reason; the caller falls back
to the rule when the model is unavailable.
"""
from pydantic import BaseModel, ConfigDict, Field
from . import intent_adapter, local_semantics


class Size(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: str = Field(min_length=1, max_length=120)
    width_m: float = Field(gt=0, le=500)
    depth_m: float = Field(gt=0, le=500)
    height_m: float = Field(gt=0, le=500)
    reason: str = Field(min_length=1, max_length=300)


def estimate(prompt, hint=None, project_style=''):
    selected = intent_adapter.model()
    anchor = (f'A size table gives {hint["label"]} about {hint["dims"]["w"]} x {hint["dims"]["d"]} x {hint["dims"]["h"]} m (width x depth x height); '
              'start from it and change it only for what the request says. ') if hint else ''
    answer = local_semantics.request('/api/chat', dict(model=selected['name'], stream=False, think=False, format=Size.model_json_schema(), keep_alive=0,
        options=dict(temperature=0, num_ctx=2048, num_predict=300, num_gpu=0, num_thread=8), messages=[
            dict(role='system', content=(
                'Estimate the real-world bounding box in metres of ONE game asset described by the user (any language, ignore typos). '
                'Width is X, depth is Z, height is Y including roof or spires. References: a person is 1.8 m tall, a door 2.1 m, one storey about 3 m, '
                'a cottage 6 x 6 x 6 m, a watchtower about 5 x 5 x 12 m, a castle keep 20 x 20 x 24 m. '
                'Apply size words: giant or huge about 1.5-2x, small or tiny about 0.5x, explicit storeys or metres exactly; '
                'grounds, courtyard or walls enlarge the footprint, not the height. ' + anchor +
                'Write `reason` in the request\'s language, one short sentence.')),
            dict(role='user', content=f'Request: {prompt}\nProject style: {project_style or "none"}')]), timeout=300)
    value = Size.model_validate_json(answer['message']['content'])
    return dict(dims=dict(w=round(value.width_m, 2), d=round(value.depth_m, 2), h=round(value.height_m, 2)), subject=value.subject, reason=value.reason,
                source='local AI estimate from the description', model=selected['name'])
