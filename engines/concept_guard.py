"""Observed concept composition suitability; never artistic approval or geometric QA."""
import json
import time
from typing import Literal,Annotated
from pydantic import BaseModel,ConfigDict,Field
from . import intent_adapter,local_semantics


class Assessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    suitable_single_asset_image:bool
    observed_subject_en:str=Field(min_length=1,max_length=400)
    issues:list[Literal['multiple_views_or_panels','cropped_main_object','missing_requested_subject','no_visible_asset']]=Field(default_factory=list,max_length=4)
    observations:list[Annotated[str,Field(max_length=500)]]=Field(default_factory=list,max_length=5)


def assess(path,subject,prompt,progress):
    selected=intent_adapter.model();started=time.monotonic();progress('Local concept layout check / Qwen3-VL / CPU')
    system=('Check only if this generated image is a usable SINGLE image-to-3D source. '
        'Fail multiple separate rendered views, inset panels, contact sheets or turnarounds. '
        'One connected castle with several towers is ONE asset and is allowed. '
        'Fail if the main asset is cropped, absent or plainly a different requested subject. '
        'Do not score aesthetics, material quality, game readiness or artistic approval. '
        'Report only observed issues; unknown is not a quality pass. Return JSON schema: '+json.dumps(Assessment.model_json_schema()))
    response=local_semantics.request('/api/chat',dict(model=selected['name'],stream=False,think=False,format=Assessment.model_json_schema(),keep_alive=0,
        options=dict(temperature=0,num_ctx=8192,num_predict=700,num_gpu=0,num_thread=8),messages=[dict(role='system',content=system),
        dict(role='user',content=json.dumps(dict(requested_subject_en=subject,original_request=prompt)),images=[intent_adapter.image_input(path)])]),timeout=600)
    if not response.get('done') or response.get('done_reason')=='length':raise ValueError('Concept layout response incomplete; not passed')
    answer=Assessment.model_validate_json(response['message']['content'])
    if answer.issues:answer.suitable_single_asset_image=False
    return dict(schema_version=1,**answer.model_dump(),model=selected['name'],model_digest=selected['digest'],
        duration_seconds=time.monotonic()-started,execution='local_cpu_only',method='VLM inferred composition check; not artistic approval',artistic_approval=False)
