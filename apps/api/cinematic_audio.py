"""Project-scoped immutable imported audio; no mandatory AI or paid service."""
import json
import uuid
from pathlib import Path
from fastapi import APIRouter,HTTPException,UploadFile,File
from starlette.concurrency import run_in_threadpool
from . import store,studio
from engines import cinematic_audio as audio

router=APIRouter(prefix='/api/cinematics')

def sources(scene):
    if scene.audio_mode=='silent':return {}
    records={}
    for cue in scene.audio_cues:
        record=studio.scoped_artifact(cue.artifact_id,scene.project_id)
        if record['role']!='cinematic_audio_source':raise ValueError('Cue requires an imported cinematic audio source')
        path=store.safe_path(record['relative_path'])
        if cue.sha256!=record['sha256'] or store.digest(path)!=cue.sha256:raise ValueError('Audio source checksum changed: '+cue.name)
        if cue.source_start+cue.duration>record['metadata']['audio']['duration_seconds']+.002:raise ValueError('Cue extends beyond source audio: '+cue.name)
        records[cue.artifact_id]=record
    return records

@router.post('/assets/{asset_id}/audio',status_code=201)
async def import_audio(asset_id:str,file:UploadFile=File(...)):
    from engines.cinematic import media_tools
    model=studio.asset(asset_id)
    if model.get('asset_type')!='cinematic':raise HTTPException(409,'Save a cinematic scene before attaching audio')
    extension=Path(file.filename or '').suffix.lower()
    if extension not in {'.wav','.mp3','.flac','.ogg','.m4a','.aac'}:raise HTTPException(422,'Choose WAV, MP3, FLAC, OGG, M4A or AAC audio')
    folder=store.safe_path(f'projects/{model["project_id"]}/assets/{asset_id}/audio/{uuid.uuid4().hex}');folder.mkdir(parents=True)
    temporary=folder/('source'+extension+'.part');target=folder/('source'+extension)
    try:
        size=0
        with temporary.open('xb') as output:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>256*1024**2:raise ValueError('Audio exceeds 256 MiB limit')
                output.write(chunk)
        temporary.replace(target);tools=media_tools()
        measured=await run_in_threadpool(audio.probe,target,tools);preview=await run_in_threadpool(audio.waveform,target,tools)
        checksum=store.digest(target)
        with store.connect() as db:
            existing=next((store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE asset_id=? AND role='cinematic_audio_source' AND sha256=?",(asset_id,checksum))),None)
        if existing:
            target.unlink();folder.rmdir();return existing
        return store.add_artifact(target,'cinematic_audio_source',Path(file.filename or 'Audio').name,dict(project_id=model['project_id'],asset_id=asset_id,asset_type='cinematic',origin='user_import',license='NEEDS_REVIEW',audio=measured,waveform=preview,source_filename=Path(file.filename or 'Audio').name,afs_ai_generated=False,generation_provenance='Not supplied for imported source; no AFS audio inference invoked',quality='Source preserved; import does not establish artistic quality or commercial rights'))
    except Exception as exc:
        temporary.unlink(missing_ok=True);target.unlink(missing_ok=True)
        if folder.exists() and not any(folder.iterdir()):folder.rmdir()
        raise HTTPException(422,str(exc))
