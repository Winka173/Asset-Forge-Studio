"""Conservative exact commands -> typed edits. Never execute arbitrary prompt text."""
import copy
import re
from engines.quality import fingerprint

NUMBER=r'\d+(?:\.\d+)?'
TIME=r'(?:\d{1,2}:\d{2}(?:\.\d+)?|'+NUMBER+r')'

def seconds(text):
    if ':' not in text:return float(text)
    minute,second=text.split(':')
    if float(second)>=60:raise ValueError('Timestamp seconds must be below 60')
    return int(minute)*60+float(second)

def object_target(scene,name):
    name=re.sub(r'^(?:the|a|an)\s+','',name.strip(),flags=re.I).casefold()
    matches=[o for o in scene.objects if o.visible and (o.id.casefold()==name or o.name.casefold()==name or o.tag==name)]
    if not matches:matches=[o for o in scene.objects if o.visible and name in o.name.casefold()]
    if len(matches)!=1:raise ValueError('Choose one visible object by its exact name or unique role. Matching objects: '+(', '.join(o.name for o in matches) or 'none'))
    return matches[0]

def edit_audio(cues,start,end,operation):
    result=[];affected=0
    for cue in cues:
        cue=copy.deepcopy(cue);u,v=cue['start'],cue['start']+cue['duration'];a,b=max(u,start),min(v,end)
        if a>=b:
            if operation=='cut' and u>=end:cue['start']-=end-start
            result.append(cue);continue
        if operation=='mute_music' and cue['family']!='music':result.append(cue);continue
        affected+=1
        boundaries=sorted({u,a,b,v})
        for lo,hi in zip(boundaries,boundaries[1:]):
            middle=lo>=start and hi<=end
            if middle and operation=='cut':continue
            value=copy.deepcopy(cue);offset=lo-u
            value.update(id='cue_'+fingerprint(dict(parent=cue['id'],lo=lo,hi=hi,operation=operation))[:24],parent_cue_id=cue.get('parent_cue_id') or cue['id'],start=lo-(end-start if operation=='cut' and lo>=end else 0),duration=hi-lo,source_start=cue.get('source_start',0)+offset,envelope_start=cue.get('envelope_start',0)+offset,envelope_duration=cue.get('envelope_duration') or cue['duration'])
            if middle and operation=='mute_music':value['mute']=True
            result.append(value)
    return result,affected

def relink_audio(data):
    ids={s['id'] for s in data['shots']};cursor=0;timeline=[]
    for shot in data['shots']:
        end=cursor+round(shot['duration']*data['fps'])/data['fps'];timeline.append((cursor,end,shot['id']));cursor=end
    for cue in data.get('audio_cues',[]):
        if cue.get('linked_shot') and cue['linked_shot'] not in ids:cue['linked_shot']=next((sid for start,end,sid in timeline if start<=cue['start']<end),None)

def plan(scene,prompt):
    original=scene.model_dump();data=copy.deepcopy(original);text=prompt.strip().rstrip('.!').replace('–','-').replace('—','-')
    cut=re.fullmatch(r'(?:cut|remove|cắt|xóa)\s+(?:(?:seconds?|giây)\s+)?('+TIME+r')\s*(?:-|to|đến)\s*('+TIME+r')(?:\s*(?:seconds?|giây))?',text,re.I)
    zoom=re.fullmatch(r'(?:zoom\s+(?:in(?:to)?|closer\s+to)|zoom|phóng\s+gần)\s+(.+?)\s+(?:at|from|trong|từ)\s+(?:(?:seconds?|giây)\s+)?('+TIME+r')\s*(?:-|to|đến)\s*('+TIME+r')(?:\s*(?:seconds?|giây))?(?:\s+(?:by\s+)?('+NUMBER+r')\s*%)?',text,re.I)
    epic=re.fullmatch(r'(?:make\s+(?:the\s+)?boss\s+reveal\s+more\s+epic|make\s+shot\s+(\d+)\s+more\s+epic)',text,re.I)
    mute=re.fullmatch(r'(?:mute\s+(?:the\s+)?(?:background\s+)?music|tắt\s+nhạc)\s+(?:from|at|từ)\s+(?:(?:seconds?|giây)\s+)?('+TIME+r')\s*(?:-|to|đến)\s*('+TIME+r')(?:\s*(?:seconds?|giây))?',text,re.I)
    changes=[]
    if cut or zoom:
        match=cut or zoom;start=seconds(match[1] if cut else match[2]);end=seconds(match[2] if cut else match[3]);fps=scene.fps
        a,b=round(start*fps),round(end*fps);total=sum(round(s.duration*fps) for s in scene.shots)
        if not 0<=a<b<=total:raise ValueError('Choose a nonempty interval inside the rendered timeline')
        if cut and b-a==total:raise ValueError('Cannot remove the entire cinematic')
        target=object_target(scene,zoom[1]) if zoom else None
        percent=float(zoom[4] or 35) if zoom else None
        if zoom and not 0<percent<=80:raise ValueError('Supported zoom is greater than 0 and at most 80 percent closer')
        clips=[];cursor=0
        for shot in scene.shots:
            count=round(shot.duration*fps);left=max(cursor,a);right=min(cursor+count,b)
            if left>=right:clips.append(shot.model_dump());cursor+=count;continue
            boundaries=sorted({cursor,left,right,cursor+count})
            for lo,hi in zip(boundaries,boundaries[1:]):
                affected=lo>=a and hi<=b
                if affected and cut:continue
                value=shot.model_dump();value['id']='clip_'+fingerprint(dict(parent=shot.id,lo=lo,hi=hi,prompt=prompt))[:24]
                value.update(duration=(hi-lo)/fps,source_start_frame=shot.source_start_frame+lo-cursor,motion_duration=shot.motion_duration or shot.duration)
                if affected and zoom:value.update(target_id=target.id,distance=shot.distance*(1-percent/100))
                clips.append(value)
            cursor+=count
        data['shots']=clips;operation='ripple_cut' if cut else 'camera_zoom'
        if cut and data.get('audio_cues'):
            data['audio_cues'],_=edit_audio(data['audio_cues'],a/fps,b/fps,'cut')
            if not data['audio_cues']:data['audio_mode']='silent'
        relink_audio(data)
        changes=[dict(type=operation,requested_seconds=[start,end],applied_frames=[a,b],applied_seconds=[a/fps,b/fps],target_id=target.id if target else None,closer_percent=percent)]
        explanation=('Remove this frame interval and close the gap. Surviving source frames keep their original camera and animation time; no image generation.' if cut else 'Split at the interval boundaries; change only the selected object target and camera distance. Other camera settings, sources and quality remain pinned. Camera visibility/intersection still needs review.')
    elif mute:
        start,end=seconds(mute[1]),seconds(mute[2]);duration=sum(round(s.duration*scene.fps) for s in scene.shots)/scene.fps
        if scene.audio_mode!='imported' or not 0<=start<end<=duration:raise ValueError('Choose a valid interval inside a cinematic with imported music')
        data['audio_cues'],affected=edit_audio(data.get('audio_cues',[]),start,end,'mute_music')
        if not affected:raise ValueError('No music cue overlaps this interval; no revision started')
        operation='mute_music';changes=[dict(type=operation,seconds=[start,end],affected_original_cues=affected)]
        explanation='Mute only music over this interval. Imported source files, dialogue/SFX cues, camera and every video frame remain unchanged. Existing fades retain their original envelope; no AI inference.'
    elif epic:
        if epic[1]:
            index=int(epic[1])-1
            if not 0<=index<len(scene.shots):raise ValueError('Shot number is outside the storyboard')
        else:
            bosses={o.id for o in scene.objects if o.tag=='boss' and o.visible}
            choices=[i for i,s in enumerate(scene.shots) if s.target_id in bosses or 'boss' in s.name.casefold()]
            if len(choices)!=1:raise ValueError('Assign the boss as one shot target, or use: Make shot 2 more epic')
            index=choices[0]
        shot=data['shots'][index];shot.update(distance=shot['distance']*.8,elevation=max(5,shot['elevation']-8),look='violet_reveal')
        operation='reveal_preset';changes=[dict(type=operation,shot_id=shot['id'],distance=shot['distance'],elevation=shot['elevation'],look='violet_reveal')]
        explanation='Only this shot gets a 20% closer camera, an angle up to 8 degrees lower and stronger violet rim light. No mesh editing, fog, generated motion, music or SFX is implied.'
    else:raise ValueError('Supported exact edits: Zoom into the crystal at seconds 3-5; Cut seconds 6-8; Make boss reveal more epic; Make shot 2 more epic; Mute music from 2 to 4 seconds. Other instructions remain unsupported; edit the shot/cue controls instead. No revision or render was started.')
    from .cinematic import Scene
    edited=Scene.model_validate(data)
    return dict(scene=edited.model_dump(),operation=operation,changes=changes,explanation=explanation,source_hashes_preserved=True,quality_preserved=True,ai_inference=False,duration_before_seconds=sum(round(s.duration*scene.fps) for s in scene.shots)/scene.fps,duration_after_seconds=sum(round(s.duration*scene.fps) for s in edited.shots)/scene.fps,parser='Deterministic exact-command parser; not general natural-language AI')
