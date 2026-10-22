import array
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs
from apps.api.main import app
from apps.api.cinematic import Scene
from engines.cinematic import media_tools
from engines.cinematic_audio import measure,run,mix_command
from audio_fixtures import create

def rms(path,tools,start,end):
    raw=run([tools['ffmpeg'],'-nostdin','-v','error','-i',str(path),'-ss',str(start),'-t',str(end-start),'-ac','1','-ar','48000','-f','f32le','-']).stdout
    values=array.array('f');values.frombytes(raw)
    return (sum(v*v for v in values)/len(values))**.5

def test_real_import_mix_mux_music_edit_and_AV_ripple(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path/'Library');qa_project();c=TestClient(app)
    fixture=store.ROOT/'.local/fixtures/RiggedSimple.glb'
    if not fixture.is_file():pytest.skip('Real licensed GLB fixture unavailable')
    files=create(tmp_path/'fixtures',store.ROOT)
    if 'voice1' not in files or 'voice2' not in files:pytest.skip('Actual installed Windows speech fixtures unavailable; no speech quality is simulated')
    try:tools=media_tools()
    except ValueError:pytest.skip('FFmpeg/FFprobe unavailable')
    source=c.post('/api/assets',json=dict(project_id='runavelle',name='Licensed technical source',prompt='Not generated game content')).json()
    glb=c.post('/api/import/candidate',params=dict(project_id='runavelle',asset_id=source['id']),files={'file':(fixture.name,fixture.read_bytes())}).json()
    scene=dict(project_id='runavelle',name='Real imported audio technical QA',objects=[dict(id='model',name='Licensed fixture',asset_id=source['id'],artifact_id=glb['id'],sha256=glb['sha256'])],shots=[dict(id='first',name='First',duration=4,distance=14),dict(id='second',name='Second',duration=4,distance=14,movement='dolly')],width=320,height=180,fps=12,samples=8)
    first=c.post('/api/cinematics/scenes',json=dict(scene=scene,request_id='audio-initial-snapshot')).json()
    records={};cues=[]
    for key,path in files.items():
        response=c.post('/api/cinematics/assets/'+first['asset_id']+'/audio',files={'file':(path.name,path.read_bytes(),'audio/wav')});assert response.status_code==201,response.text
        record=response.json();records[key]=record;assert len(record['metadata']['waveform']['peaks'])<=400
        assert c.post('/api/cinematics/assets/'+first['asset_id']+'/audio',files={'file':(path.name,path.read_bytes())}).json()['id']==record['id']
        family='dialogue' if key.startswith('voice') else 'sfx' if key.startswith('sfx') else key
        start={'voice1':.5,'voice2':4.2}.get(key,[1,2.4,3.8,5,7][int(key[-1])] if key.startswith('sfx') else 0)
        cues.append(dict(id=key,name=key,artifact_id=record['id'],sha256=record['sha256'],family=family,start=start,duration=min(record['metadata']['audio']['duration_seconds'],8-start),gain_db=-12 if family=='music' else -20 if family in ('sfx','ambience') else 0,fade_in=.02,fade_out=.02,linked_shot='first' if start<4 else 'second'))
    assert c.post('/api/cinematics/assets/'+first['asset_id']+'/audio',files={'file':('bad.wav',b'not an audio file')}).status_code==422
    assert jobs.listing()==[]
    scene.update(audio_mode='imported',audio_cues=cues)
    response=c.post('/api/cinematics/scenes',json=dict(scene=scene,asset_id=first['asset_id'],base_scene_id=first['scene_id'],request_id='audio-mix-snapshot'));assert response.status_code==201,response.text
    current=response.json()['scene_id'];baseline=None;voice_hash=None
    for index,prompt in enumerate((None,'Mute music from 2 to 4 seconds','Cut seconds 6-8')):
        if prompt:
            response=c.post('/api/cinematics/refinements',json=dict(scene_id=current,base_scene_id=current,prompt=prompt,request_id='audio-refine-'+str(index)));assert response.status_code==201,response.text
            current=response.json()['scene_id']
        response=c.post('/api/cinematics/render',json=dict(scene_id=current,request_id='audio-real-render-'+str(index)));assert response.status_code==201,response.text
        job=response.json()
        with jobs.resource_slot('cpu'):jobs.Worker().execute(job)
        assert jobs.get(job['id'])['status']=='REVIEW_REQUIRED',jobs.get(job['id']).get('error')
        folder=store.DATA/'jobs'/job['id']/'output';qa=json.loads((folder/'video_qa.json').read_text());render=json.loads((folder/'render_report.json').read_text())
        assert qa['audio']['clipped_samples']==0 and qa['audio']['true_peak_dbfs'] is not None and qa['audio']['true_peak_dbfs']<=0
        assert not qa['audio']['silent']
        assert qa['frames']==(72 if index==2 else 96)
        assert len(json.loads((folder/'audio_qa.json').read_text())['stems'])==4
        if index==0:
            baseline=qa;voice_hash=store.digest(folder/'stem_dialogue.wav');original_music=folder/'stem_music.wav'
            assert render['rendered_frames']==96
            # Prove actual music reduction under imported speech, not just a saved checkbox.
            raw_paths={r['id']:store.safe_path(r['relative_path']) for r in records.values()}
            command,_=mix_command(cues,raw_paths,tools,tmp_path/'unducked',8,False);run(command)
            assert rms(original_music,tools,1,3)<rms(tmp_path/'unducked/stem_music.wav',tools,1,3)*.9
            video=next(a for a in c.get('/api/cinematics/assets/'+first['asset_id']).json()['artifacts'] if a['role']=='cinematic_video');original_video=Path(video['metadata']['delivery']);original_hash=store.digest(original_video)
        else:
            assert render['rendered_frames']==0 and render['reused_frames']==qa['frames']
            assert [f['sha256'] for f in qa['frame_hashes']]==[f['sha256'] for f in baseline['frame_hashes'][:qa['frames']]]
            assert store.digest(original_video)==original_hash
            if index==1:
                assert store.digest(folder/'stem_dialogue.wav')==voice_hash
                assert rms(folder/'stem_music.wav',tools,2.2,3.8)<1e-8 and rms(original_music,tools,2.2,3.8)>.0001
        assert all(store.digest(store.safe_path(r['relative_path']))==r['sha256'] for r in records.values())
    detail=c.get('/api/cinematics/assets/'+first['asset_id']).json()
    assert len(detail['scenes'])==4 and len(jobs.listing())==3
    final=Scene.model_validate(detail['scenes'][-1]['scene'])
    assert all(c.start+c.duration<=6+.000001 for c in final.audio_cues)
    assert all(c.linked_shot in {s.id for s in final.shots} for c in final.audio_cues if c.linked_shot)
