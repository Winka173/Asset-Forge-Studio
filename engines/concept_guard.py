"""Observed concept composition suitability; never artistic approval or geometric QA."""
import json
import time
from typing import Literal,Annotated
from pydantic import BaseModel,ConfigDict,Field
from . import intent_adapter,local_semantics

# 4: the checked subject falls back to the manifest heading instead of a generic "game asset".
# 5: subject-neutral framing question (no roof/wall wording that implies a building).
# 6: several separate objects (a set or lineup) count as multiple_views_or_panels.
# 7: buildings must read at human scale (a door a person walks through) unless giant, and a dwelling must not be a castle
#    or a ruin with broken pieces unless asked (measured: a house drawn as a four-tower castle, a merchant estate as a ruin).
# 8: a character asked to hold nothing (or whose weapons are separate assets) must have empty hands (measured: a
#    'no weapon held' knight was drawn with sword and shield and passed the check).
POLICY_VERSION=8


class ObservedLayout(BaseModel):
    """One categorical fact per dimension; avoid conflicting pass/fail booleans."""
    model_config=ConfigDict(extra='forbid')
    observed_subject_en:str=Field(min_length=1,max_length=400)
    composition:Literal['single_asset','multiple_views_or_panels','no_visible_asset']
    requested_subject:Literal['matches','plainly_different','uncertain']
    framing:Literal['whole_asset_visible','cropped']
    background:Literal['plain_studio','surrounding_scenery']
    lettering:Literal['absent','text_or_decorative_border']
    building:Literal['not_a_building','sound_and_human_scale','door_missing_or_too_small','castle_for_a_dwelling','ruined_or_broken_pieces']
    hands:Literal['not_a_character','empty','holding_an_object']
    observations:list[Annotated[str,Field(max_length=500)]]=Field(min_length=1,max_length=5)


def from_observation(facts,empty_hands=False):
    issues=[]
    if facts.composition!='single_asset':issues.append(facts.composition)
    if facts.requested_subject=='plainly_different':issues.append('missing_requested_subject')
    if facts.requested_subject=='uncertain':issues.append('uncertain_source')
    issues+={'door_missing_or_too_small':['no_human_scale_entrance'],'castle_for_a_dwelling':['missing_requested_subject'],'ruined_or_broken_pieces':['broken_or_ruined_structure']}.get(facts.building,[])
    if empty_hands and facts.hands=='holding_an_object':issues.append('holding_item')
    issues=list(dict.fromkeys(issues))
    return checked_assessment(Assessment(suitable_single_asset_image=not issues,observed_subject_en=facts.observed_subject_en,issues=issues,
        background_is_plain=facts.background=='plain_studio',border_or_text_visible=facts.lettering!='absent',
        entire_main_asset_visible=facts.framing=='whole_asset_visible',observations=facts.observations))


class Assessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    suitable_single_asset_image:bool
    observed_subject_en:str=Field(min_length=1,max_length=400)
    issues:list[Literal['multiple_views_or_panels','cropped_main_object','missing_requested_subject','no_visible_asset',
        'background_scene','border_or_text','uncertain_source','no_human_scale_entrance','broken_or_ruined_structure','holding_item']]=Field(default_factory=list,max_length=10)
    background_is_plain:bool
    border_or_text_visible:bool
    entire_main_asset_visible:bool
    observations:list[Annotated[str,Field(max_length=500)]]=Field(default_factory=list,max_length=5)


def checked_assessment(answer):
    """Contradictory model booleans cannot override observed source defects."""
    inferred=[]
    if not answer.background_is_plain:inferred.append('background_scene')
    if answer.border_or_text_visible:inferred.append('border_or_text')
    if not answer.entire_main_asset_visible:inferred.append('cropped_main_object')
    answer.issues=list(dict.fromkeys([*answer.issues,*inferred]))
    if answer.issues:answer.suitable_single_asset_image=False
    return answer


def assess(path,subject,prompt,progress,empty_hands=False):
    selected=intent_adapter.model();started=time.monotonic();progress('Local concept layout check / Qwen3-VL / CPU')
    system=('Check only if this generated image is a usable SINGLE image-to-3D source. '
        'Fail multiple separate rendered views, inset panels, contact sheets or turnarounds. '
        'Also use multiple_views_or_panels when the image shows several separate objects (a set, collection, lineup or scattered items) instead of one asset. '
        'One connected castle with several towers is ONE asset and is allowed. '
        'For a requested CASTLE, a lone watchtower, small house or close-up entrance without a fortified castle complex is plainly_different. '
        'Fail if the main asset is cropped, absent or plainly a different requested subject. '
        'The entire asset including every top, side extremity and its contact base must fit inside the image with visible margin. '
        'Fail background_scene when trees, mountains, sky/clouds, other buildings, scenery or an illustrated landscape surround the asset. '
        'A small connected foundation, entrance steps, contact shadow or transparent/flat/neutral studio gradient is allowed. '
        'A black background behind a rendered isolated asset is allowed. Do not mistake the floor shadow for scenery. '
        'Fail border_or_text for poster frames, page margins with decorative borders, labels, captions or printed text even if tiny. '
        'Choose background=plain_studio for flat/gradient studio backdrops, surrounding_scenery only for actual landscape or other surrounding objects. '
        'Choose framing=cropped if an important piece is cut by the image edge. '
        'Choose lettering=text_or_decorative_border for visible writing or poster framing. '
        'hands: not_a_character for objects and buildings; for a character or creature holding_an_object when any hand holds or carries something '
        '(weapon, shield, staff, tool, even strapped to the arm or resting against the body), otherwise empty. '
        'building: not_a_building for props, characters, plants, effects and structures people do not walk into (wells, fountains, walls, bridges, statues, fences, platforms, terrain). For a building people enter judge an ordinary 1.75 m person: '
        'door_missing_or_too_small when no entrance is visible or the main door would not let a person walk in upright compared with the windows, steps and walls; '
        'castle_for_a_dwelling when a house, home, shop, inn or estate is drawn as a castle or fortress (several defensive towers, battlements); '
        'ruined_or_broken_pieces when walls, roof or top look broken, jagged, half-collapsed or cluttered with irregular chunks and shards instead of clean shapes, and the request did not ask for ruins; '
        'otherwise sound_and_human_scale. A request that explicitly asks for a giant or colossal structure keeps its own scale. '
        'Choose requested_subject=uncertain if the subject cannot be determined, not matches by default. '
        'Do not score aesthetics, material quality, game readiness or artistic approval. '
        'Report only observed issues; unknown is not a quality pass. Return JSON schema: '+json.dumps(ObservedLayout.model_json_schema()))
    response=local_semantics.request('/api/chat',dict(model=selected['name'],stream=False,think=False,format=ObservedLayout.model_json_schema(),keep_alive=0,
        options=dict(temperature=0,num_ctx=8192,num_predict=700,num_gpu=0,num_thread=8),messages=[dict(role='system',content=system),
        dict(role='user',content=json.dumps(dict(requested_subject_en=subject,original_request=prompt)),images=[intent_adapter.image_input(path)])]),timeout=600)
    if not response.get('done') or response.get('done_reason')=='length':raise ValueError('Concept layout response incomplete; not passed')
    facts=ObservedLayout.model_validate_json(response['message']['content']);answer=from_observation(facts,empty_hands)
    current=next((m for m in local_semantics.probe()['models'] if m['name']==selected['name']),None)
    if not current or current['digest']!=selected['digest']:raise ValueError('Concept screening model changed during inference; report not accepted')
    return dict(schema_version=3,screening_policy=POLICY_VERSION,**answer.model_dump(),observed_facts=facts.model_dump(),model=selected['name'],model_digest=selected['digest'],
        duration_seconds=time.monotonic()-started,execution='local_cpu_only',method='VLM inferred composition check; not artistic approval',artistic_approval=False)
