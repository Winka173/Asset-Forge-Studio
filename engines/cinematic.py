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
    from apps.api.cinematic_audio import sources as audio_sources
    audio_records=audio_sources(scene)
    audio='silent; no generated audio' if scene.audio_mode=='silent' else dict(mode='imported',source_hashes={key:r['sha256'] for key,r in audio_records.items()},cue_hash=fingerprint([c.model_dump() for c in scene.audio_cues]),duck_music=scene.duck_music,engine='FFmpeg offline mix; no AI audio generation')
    return dict(scene_artifact_id=record['id'],scene_sha256=record['sha256'],blender=blender,tools=tools,source_hashes={o.artifact_id:o.sha256 for o in scene.objects},
        renderer='Blender Cycles CPU',script_sha256=store.digest(store.ROOT/'scripts/blender_cinematic.py'),resolution=[scene.width,scene.height],fps=scene.fps,samples=scene.samples,
        audio=audio,encoder=dict(codec='libx264',preset='slow',crf=16,video_threads=1,filter_threads=1,input_timing='numbered_image_sequence_explicit_framerate'),original_quality_preserved=True)

def shot_caches(scene,config):
    """Content-address original camera motion, independent of timeline cuts/order."""
    data=scene.model_dump() if hasattr(scene,'model_dump') else scene
    context={key:data[key] for key in ('objects','lighting','ground','width','height','fps','samples')}
    context.update(renderer_script=config['script_sha256'],blender=config['blender'])
    result={}
    for shot in data['shots']:
        motion={key:shot[key] for key in ('movement','target_id','distance','elevation','azimuth','amount')}
        motion.update(motion_duration=shot.get('motion_duration') or shot['duration'],look=shot.get('look','inherit'))
        key=fingerprint(dict(context=context,motion=motion))
        result[shot['id']]=dict(key=key,directory=str(store.DATA/'cinematic-shot-cache'/key),start_frame=shot.get('source_start_frame',0),frame_count=round(shot['duration']*data['fps']),motion_frames=round(motion['motion_duration']*data['fps']))
    return result

def frame_path(request,shot,offset=0):
    mapping=request['shot_caches'][shot['id']]
    return Path(mapping['directory'])/f'{mapping["start_frame"]+offset:06d}.png'

def prepare(payload,record,folder):
    from apps.api.cinematic import read_scene,sources
    _,scene=read_scene(record['id']);config=effective_config(record,scene)
    if config!=payload['effective_config'] or fingerprint(config)!=payload['effective_config_hash']:raise ValueError('Scene/source/tool configuration changed since enqueue')
    records=sources(scene);output=folder/'output';output.mkdir(exist_ok=True)
    from apps.api.cinematic_audio import sources as audio_sources
    audio_records=audio_sources(scene)
    # Old whole-scene path is retained for compatibility; new receipts are per motion.
    cache=store.DATA/'cinematic-cache'/payload['effective_config_hash'];cache.mkdir(parents=True,exist_ok=True)
    required=scene.width*scene.height*4*sum(round(s.duration*scene.fps) for s in scene.shots)+512*1024**2
    if shutil.disk_usage(store.DATA).free<required:raise ValueError('Insufficient disk for conservative frame cache estimate')
    request=dict(scene=scene.model_dump(),sources={key:str(store.safe_path(value['relative_path'])) for key,value in records.items()},audio_sources={key:str(store.safe_path(value['relative_path'])) for key,value in audio_records.items()},cache=str(cache),shot_caches=shot_caches(scene,config),output=str(output),config_hash=payload['effective_config_hash'])
    path=folder/'render_request.json';path.write_text(json.dumps(request),encoding='utf-8')
    return [config['blender'],'-b','-t','4','--factory-startup','--python-exit-code','1','--python',str(store.ROOT/'scripts/blender_cinematic.py'),'--',str(path)],request

def encode(payload,folder,request):
    scene=request['scene'];cache=Path(request['cache']);output=folder/'output';frames=[];index=[]
    for shot in scene['shots']:
        for frame in range(round(shot['duration']*scene['fps'])):
            file=frame_path(request,shot,frame)
            with Image.open(file) as im:
                im.verify()
            with Image.open(file) as im:
                if im.size!=(scene['width'],scene['height']):raise ValueError('Frame resolution mismatch')
            frames.append(file);index.append(dict(shot=shot['id'],frame=frame,sha256=store.digest(file)))
    # Numbered inputs give each decoded image an exact rational timestamp. The
    # concat/image demuxer can emit missing/rounded PTS across separate PNG files.
    sequence=folder/'encode_frames';sequence.mkdir(exist_ok=True)
    for frame_number,file in enumerate(frames):
        target=sequence/f'{frame_number:06d}.png'
        if not target.exists():
            try:os.link(file,target)
            except OSError:shutil.copyfile(file,target)
        elif store.digest(target)!=store.digest(file):raise ValueError('Encoder staging frame changed')
    partial=output/'cinematic.part.mp4';tools=payload['effective_config']['tools']
    audio=['-an'] if scene['audio_mode']=='silent' else ['-i',str(output/'audio_master.wav'),'-map','0:v:0','-map','1:a:0','-c:a','aac','-b:a','320k','-ar','48000','-ac','2','-t',str(len(frames)/scene['fps'])]
    command=[tools['ffmpeg'],'-nostdin','-y','-v','error','-filter_threads','1','-framerate',str(scene['fps']),'-start_number','0','-i',str(sequence/'%06d.png'),*audio,'-r',str(scene['fps']),'-frames:v',str(len(frames)),'-c:v','libx264','-threads:v','1','-preset','slow','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
    return command,partial,index

def reuse_encoded(payload,record,frame_hashes,partial):
    """Reuse a completed encoded checkpoint, never rely on bit-identical H.264 retries."""
    delivery=store.DATA/'exports'/payload['project_id']/'cinematics'/payload['asset_id']/payload['effective_config_hash']
    target=delivery/'cinematic.mp4'
    if not target.exists():return False
    from apps.api import jobs
    with store.connect() as db:artifacts=[store.artifact(r) for r in db.execute('SELECT * FROM artifacts WHERE asset_id=?',(payload['asset_id'],))]
    checksum=store.digest(target)
    for video in artifacts:
        if video['role']!='cinematic_video' or video['metadata'].get('parent_id')!=record['id'] or video['sha256']!=checksum:continue
        prior=jobs.get(video['metadata']['job_id'])
        if prior['payload'].get('effective_config_hash')!=payload['effective_config_hash']:continue
        qa=next((a for a in artifacts if a['role']=='qa_report' and a['name']=='Cinematic technical QA' and a['metadata'].get('job_id')==prior['id']),None)
        if not qa:continue
        qa_path=store.safe_path(qa['relative_path'])
        if not qa_path.is_file() or store.digest(qa_path)!=qa['sha256']:continue
        previous=json.loads(qa_path.read_text())
        if previous.get('frame_hashes')!=frame_hashes:continue
        manifest=json.loads((delivery/'manifest.json').read_text(encoding='utf-8'))
        expected=dict(asset_id=payload['asset_id'],project_id=payload['project_id'],scene_id=record['id'],scene_sha256=record['sha256'],source_hashes=payload['effective_config']['source_hashes'],sha256=checksum,video='cinematic.mp4')
        if any(manifest.get(key)!=value for key,value in expected.items()):raise ValueError('Existing cinematic delivery manifest differs; no overwrite')
        shutil.copyfile(target,partial)
        if store.digest(partial)!=checksum:raise ValueError('Encoded checkpoint copy failed checksum')
        (partial.parent/'encode_checkpoint.json').write_text(json.dumps(dict(status='REUSED_VERIFIED_ENCODED_CHECKPOINT',source_artifact_id=video['id'],sha256=checksum,frame_hashes_equal=True,scope='Actual prior delivery copied; full decode/QA still runs. H.264 byte reproducibility is not assumed.'),indent=2))
        return True
    raise ValueError('Existing delivery has no matching verified frame/config checkpoint; no overwrite')

def validate_video(payload,path,request):
    scene=request['scene'];tools=payload['effective_config']['tools']
    result=subprocess.run([tools['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=30)
    if result.returncode:raise ValueError('FFprobe rejected video')
    data=json.loads(result.stdout);streams=[s for s in data['streams'] if s['codec_type']=='video'];expected=sum(round(s['duration']*scene['fps']) for s in scene['shots'])
    if len(streams)!=1:raise ValueError('Expected one real video stream')
    stream=streams[0]
    if stream['width']!=scene['width'] or stream['height']!=scene['height'] or stream['codec_name']!='h264' or abs(float(data['format']['duration'])-expected/scene['fps'])>1/scene['fps']+.01:raise ValueError('Video stream contract mismatch')
    if int(stream.get('nb_frames',0))!=expected:raise ValueError('Encoded frame count does not match timeline')
    numerator,denominator=map(int,stream['avg_frame_rate'].split('/'))
    if denominator==0 or abs(numerator/denominator-scene['fps'])>.001:raise ValueError('Encoded frame rate does not match timeline')
    audio='silent';audio_streams=[s for s in data['streams'] if s['codec_type']=='audio']
    if scene['audio_mode']=='silent' and audio_streams:raise ValueError('Silent export unexpectedly has audio')
    if scene['audio_mode']=='imported':
        if len(audio_streams)!=1 or audio_streams[0]['codec_name']!='aac' or audio_streams[0]['channels']!=2 or int(audio_streams[0]['sample_rate'])!=48000 or abs(float(audio_streams[0]['duration'])-expected/scene['fps'])>.05:raise ValueError('Audio codec/channels/rate/sync contract mismatch')
        from engines.cinematic_audio import measure
        audio=measure(path,tools)
        if audio['clipped_samples'] or audio['true_peak_dbfs'] is not None and audio['true_peak_dbfs']>0:raise ValueError('Encoded audio clipping/true-peak validation failed; source stems are retained')
    decode=subprocess.run([tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True,text=True,timeout=300)
    if decode.returncode:raise ValueError('Full video decode failed: '+decode.stderr[-1000:])
    return dict(status='PASS_VIDEO_DECODE',streams=data['streams'],duration_seconds=float(data['format']['duration']),frames=expected,fps=scene['fps'],resolution=[scene['width'],scene['height']],audio=audio,artistic_review='not_reviewed')
