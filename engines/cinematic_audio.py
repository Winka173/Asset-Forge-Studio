"""Local imported-audio cue mixing. No generated music, cloning or lip-sync claim."""
import array
import json
import math
import os
import re
import subprocess
from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field,model_validator

class Cue(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    name:str=Field(min_length=1,max_length=200)
    artifact_id:str
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    family:str=Field(pattern=r'^(music|sfx|dialogue|ambience)$')
    start:float=Field(default=0,ge=0,le=300)
    source_start:float=Field(default=0,ge=0,le=600)
    duration:float=Field(gt=0,le=300)
    gain_db:float=Field(default=0,ge=-60,le=12)
    pan:float=Field(default=0,ge=-1,le=1)
    fade_in:float=Field(default=0,ge=0,le=30)
    fade_out:float=Field(default=0,ge=0,le=30)
    mute:bool=False
    solo:bool=False
    linked_shot:str|None=None
    linked_object_id:str|None=None
    speaker_id:str|None=Field(default=None,max_length=100)
    language:str|None=Field(default=None,max_length=30)
    text:str=Field(default='',max_length=10000)
    parent_cue_id:str|None=None
    envelope_start:float=Field(default=0,ge=0,le=600)
    envelope_duration:float|None=Field(default=None,gt=0,le=300)
    @model_validator(mode='after')
    def fades(self):
        duration=self.envelope_duration or self.duration
        if self.fade_in+self.fade_out>duration:raise ValueError('Combined fades exceed original envelope duration')
        if self.envelope_start+self.duration>duration+1e-6 or self.source_start<self.envelope_start:raise ValueError('Trim lies outside original cue envelope')
        return self

def run(command,timeout=120):
    result=subprocess.run(command,capture_output=True,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if result.returncode:raise ValueError('Audio processing failed: '+result.stderr.decode('utf-8',errors='replace')[-1500:])
    return result

def probe(path,tools):
    result=run([tools['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(path)],30)
    data=json.loads(result.stdout);streams=[s for s in data.get('streams',[]) if s['codec_type']=='audio']
    if len(streams)!=1 or any(s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic') for s in data['streams']):raise ValueError('Import one mono/stereo audio stream; video files use the video workflow')
    stream=streams[0];duration=float(stream.get('duration') or data['format']['duration'])
    if not 0<duration<=600 or int(stream['channels']) not in (1,2) or not 8000<=int(stream['sample_rate'])<=192000:raise ValueError('Initial audio import supports mono/stereo, 8–192 kHz and up to 10 minutes')
    return dict(duration_seconds=duration,sample_rate=int(stream['sample_rate']),channels=int(stream['channels']),codec=stream['codec_name'])

def waveform(path,tools):
    raw=run([tools['ffmpeg'],'-nostdin','-v','error','-xerror','-protocol_whitelist','file,pipe','-i',str(path),'-vn','-t','600','-ac','2','-ar','8000','-f','f32le','-'],120).stdout
    samples=array.array('f');samples.frombytes(raw)
    if not samples or any(not math.isfinite(v) for v in samples):raise ValueError('Audio decoded to empty or non-finite samples')
    step=max(1,math.ceil(len(samples)/400));peaks=[max(abs(v) for v in samples[i:i+step]) for i in range(0,len(samples),step)]
    return dict(peaks=peaks,scope='Stereo absolute peaks resampled to 8 kHz for preview; not true-peak metering',decoded_duration_seconds=len(samples)/16000)

def mix_command(cues,paths,tools,folder,duration,duck=True):
    """Fixed filter vocabulary + validated numeric values; no user-authored graphs."""
    cues=[Cue.model_validate(c) for c in cues]
    if not cues:raise ValueError('No audio cues to mix; choose silent output explicitly')
    inputs=[];graph=[];buckets={};solo=any(c.solo for c in cues)
    for i,cue in enumerate(cues):
        inputs+=['-protocol_whitelist','file,pipe','-i',str(paths[cue.artifact_id])]
        gain=0 if cue.mute or solo and not cue.solo else 10**(cue.gain_db/20)
        envelope=cue.envelope_duration or cue.duration
        filters=['aresample=48000',f'atrim=start={cue.source_start-cue.envelope_start:.9f}:duration={envelope:.9f}','asetpts=N/SR/TB','aformat=sample_fmts=fltp:channel_layouts=stereo',f'volume={gain:.9f}',f'pan=stereo|c0={min(1,1-cue.pan):.9f}*c0|c1={min(1,1+cue.pan):.9f}*c1']
        if cue.fade_in:filters.append(f'afade=t=in:st=0:d={cue.fade_in:.9f}')
        if cue.fade_out:filters.append(f'afade=t=out:st={envelope-cue.fade_out:.9f}:d={cue.fade_out:.9f}')
        # adelay can emit leading silent frames with NOPTS. Rebuild the sample
        # clock before atrim/amix; otherwise those real silent samples get lost.
        filters.extend([f'atrim=start={cue.envelope_start:.9f}:duration={cue.duration:.9f}','asetpts=N/SR/TB',f'adelay=delays={round(cue.start*48000)}S:all=1','asetpts=N/SR/TB',f'apad=whole_dur={duration:.9f}',f'atrim=duration={duration:.9f}'])
        graph.append(f'[{i}:a:0]'+','.join(filters)+f'[cue{i}]');buckets.setdefault(cue.family,[]).append(f'[cue{i}]')
    buses={}
    for family,labels in buckets.items():
        label='raw_'+family;buses[family]=label
        graph.append(''.join(labels)+(f'amix=inputs={len(labels)}:normalize=0:duration=longest:dropout_transition=0' if len(labels)>1 else 'anull')+f'[{label}]')
    if duck and 'music' in buses and 'dialogue' in buses:
        graph.append('[raw_dialogue]asplit=2[voice_mix][speech_sidechain]')
        graph.append('[raw_music][speech_sidechain]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=250[ducked_music]')
        buses['music']='ducked_music';buses['dialogue']='voice_mix'
    for family,label in buses.items():graph.append(f'[{label}]asplit=2[stem_{family}][mix_{family}]')
    labels=''.join('[mix_'+family+']' for family in buses)
    mixer=f'amix=inputs={len(buses)}:normalize=0:duration=longest:dropout_transition=0' if len(buses)>1 else 'anull'
    graph.append(labels+mixer+f',aresample=192000,alimiter=limit=0.8:level=false:latency=true,aresample=48000,asetpts=N/SR/TB,apad=whole_dur={duration:.9f},atrim=duration={duration:.9f}[master]')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);script=folder/'audio_filtergraph.txt';script.write_text(';\n'.join(graph),encoding='utf-8')
    command=[tools['ffmpeg'],'-nostdin','-y','-v','error',*inputs,'-filter_complex_script',str(script),'-map','[master]','-c:a','pcm_s24le','-ar','48000','-ac','2',str(folder/'audio_master.wav')]
    stems={}
    for family in buses:
        file=folder/('stem_'+family+'.wav');stems[family]=str(file)
        command+=['-map',f'[stem_{family}]','-c:a','pcm_f32le','-ar','48000','-ac','2',str(file)]
    return command,stems

def measure(path,tools):
    raw=run([tools['ffmpeg'],'-nostdin','-v','error','-xerror','-i',str(path),'-vn','-ac','2','-ar','48000','-f','f32le','-'],120).stdout
    samples=array.array('f');samples.frombytes(raw)
    if not samples or any(not math.isfinite(v) for v in samples):raise ValueError('Mixed audio contains invalid samples')
    peak=max(abs(v) for v in samples);rms=math.sqrt(sum(v*v for v in samples)/len(samples));clipped=sum(abs(v)>=1 for v in samples)
    loud=run([tools['ffmpeg'],'-nostdin','-hide_banner','-i',str(path),'-vn','-af','ebur128=peak=true','-f','null','-'],120).stderr.decode('utf-8',errors='replace')
    matches=re.findall(r'True peak:\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS',loud)
    tp=float(matches[-1]) if matches and matches[-1]!='-inf' else None
    return dict(sample_peak=peak,sample_peak_dbfs=20*math.log10(peak) if peak else None,rms_dbfs=20*math.log10(rms) if rms else None,clipped_samples=clipped,true_peak_dbfs=tp,measured_duration_seconds=len(samples)/96000,silent=peak<1e-5,artistic_quality='not_reviewed',true_peak_method='FFmpeg ebur128 oversampled measurement' if matches else 'not_available')
