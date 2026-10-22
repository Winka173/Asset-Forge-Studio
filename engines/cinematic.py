"""Reproducible Blender CPU shot render + local FFmpeg encode, no AI claims."""
import json
import os
import shutil
import subprocess
from pathlib import Path
from PIL import Image
from apps.api import store
from engines.quality import fingerprint

def media_tools():
    from apps.api.updates import active_media
    managed=active_media()
    if managed and not os.environ.get('AFS_FFMPEG') and not os.environ.get('AFS_FFPROBE'):return managed
    base=Path.home()/'Tools/trellis2'
    ffmpeg=os.environ.get('AFS_FFMPEG') or shutil.which('ffmpeg') or next((str(p) for p in (base/'code/venv/Lib/site-packages/imageio_ffmpeg/binaries').glob('ffmpeg*.exe')),None)
    ffprobe=os.environ.get('AFS_FFPROBE') or shutil.which('ffprobe') or str(base/'tools/python/ffprobe.exe')
    if not ffmpeg or not Path(ffmpeg).is_file() or not Path(ffprobe).is_file():raise ValueError('Local FFmpeg and FFprobe not found; configure AFS_FFMPEG / AFS_FFPROBE')
    return dict(ffmpeg=str(Path(ffmpeg).resolve()),ffprobe=str(Path(ffprobe).resolve()))

def effective_config(record,scene):
    from apps.api.cinematic import sources
    from apps.api.local_tools import executable
    sources(scene);blender=executable('blender')
    if not blender:raise ValueError('Local Blender required')
    tools=media_tools()
    for name,path in tools.items():
        check=subprocess.run([path,'-version'],capture_output=True,text=True,timeout=10)
        if check.returncode:raise ValueError(name+' version probe failed')
    return dict(scene_sha256=record['sha256'],blender=blender,tools=tools,source_hashes={o.artifact_id:o.sha256 for o in scene.objects},
        renderer='Blender Cycles CPU',script_sha256=store.digest(store.ROOT/'scripts/blender_cinematic.py'),resolution=[scene.width,scene.height],fps=scene.fps,samples=scene.samples,
        audio='silent; no generated audio',original_quality_preserved=True)

def prepare(payload,record,folder):
    from apps.api.cinematic import read_scene,sources
    _,scene=read_scene(record['id']);config=effective_config(record,scene)
    if config!=payload['effective_config'] or fingerprint(config)!=payload['effective_config_hash']:raise ValueError('Scene/source/tool configuration changed since enqueue')
    records=sources(scene);output=folder/'output';output.mkdir(exist_ok=True)
    # Cache is keyed by complete immutable scene/tool config. Only checked frames resume.
    cache=store.DATA/'cinematic-cache'/payload['effective_config_hash'];cache.mkdir(parents=True,exist_ok=True)
    required=scene.width*scene.height*4*sum(round(s.duration*scene.fps) for s in scene.shots)+512*1024**2
    if shutil.disk_usage(store.DATA).free<required:raise ValueError('Insufficient disk for conservative frame cache estimate')
    request=dict(scene=scene.model_dump(),sources={key:str(store.safe_path(value['relative_path'])) for key,value in records.items()},cache=str(cache),output=str(output),config_hash=payload['effective_config_hash'])
    path=folder/'render_request.json';path.write_text(json.dumps(request),encoding='utf-8')
    return [config['blender'],'-b','-t','4','--factory-startup','--python-exit-code','1','--python',str(store.ROOT/'scripts/blender_cinematic.py'),'--',str(path)],request

def encode(payload,folder,request):
    scene=request['scene'];cache=Path(request['cache']);output=folder/'output';frames=[];index=[]
    for shot in scene['shots']:
        for frame in range(round(shot['duration']*scene['fps'])):
            file=cache/shot['id']/f'{frame:06d}.png'
            with Image.open(file) as im:
                im.verify()
            with Image.open(file) as im:
                if im.size!=(scene['width'],scene['height']):raise ValueError('Frame resolution mismatch')
            frames.append(file);index.append(dict(shot=shot['id'],frame=frame,sha256=store.digest(file)))
    # Concat paths are application-owned, not user-authored filtergraph text.
    concat=folder/'frames.txt';concat.write_text(''.join("file '"+p.as_posix().replace("'","'\\''")+"'\nduration "+str(1/scene['fps'])+'\n' for p in frames),encoding='utf-8')
    partial=output/'cinematic.part.mp4';tools=payload['effective_config']['tools']
    command=[tools['ffmpeg'],'-nostdin','-y','-v','error','-f','concat','-safe','0','-i',str(concat),'-an','-r',str(scene['fps']),'-frames:v',str(len(frames)),'-c:v','libx264','-preset','slow','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
    return command,partial,index

def validate_video(payload,path,request):
    scene=request['scene'];tools=payload['effective_config']['tools']
    result=subprocess.run([tools['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30)
    if result.returncode:raise ValueError('FFprobe rejected video')
    data=json.loads(result.stdout);streams=[s for s in data['streams'] if s['codec_type']=='video'];expected=sum(round(s['duration']*scene['fps']) for s in scene['shots'])
    if len(streams)!=1:raise ValueError('Expected one real video stream')
    stream=streams[0]
    if stream['width']!=scene['width'] or stream['height']!=scene['height'] or stream['codec_name']!='h264' or abs(float(data['format']['duration'])-expected/scene['fps'])>1/scene['fps']+.01:raise ValueError('Video stream contract mismatch')
    decode=subprocess.run([tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True,text=True,timeout=300)
    if decode.returncode:raise ValueError('Full video decode failed: '+decode.stderr[-1000:])
    return dict(status='PASS_VIDEO_DECODE',streams=data['streams'],duration_seconds=float(data['format']['duration']),frames=expected,fps=scene['fps'],resolution=[scene['width'],scene['height']],audio='silent',artistic_review='not_reviewed')
