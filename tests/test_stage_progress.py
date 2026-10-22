"""Real captured worker-log prefixes, not fabricated generation results."""
from pathlib import Path
from apps.api import jobs,store
from apps.api.stage_progress import parse

ROOT=Path(__file__).parent/'fixtures/progress'


def test_real_trellis_and_sdxl_percent_survives_earlier_stage_header():
    for file,stage,percent in [('actual_trellis_castle_hr53.log','Sampling shape SLat (HR)',53),('actual_sdxl_tower54.log','Concept denoising',54)]:
        text=(ROOT/file).read_text('utf-8')
        if 'sdxl' in file:assert 'STAGE ' in text
        result=parse(text,'RUNNING');assert result==dict(stage=stage,percent=percent,scope='current_stage_only')
        changed=parse(text+'\nSTAGE GLB remesh, UV and native PBR finishing\n','RUNNING')
        assert changed['percent'] is None and changed['stage'].startswith('GLB remesh')


def test_queue_read_uses_the_actual_latest_progress_and_new_stage_resets(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    job=jobs.enqueue(dict(kind='inference'));jobs.transition(job['id'],'RUNNING')
    folder=store.DATA/'jobs'/job['id'];folder.mkdir(parents=True)
    text=(ROOT/'actual_sdxl_tower54.log').read_text('utf-8');log=folder/'worker.log';log.write_text(text,'utf-8')
    assert jobs.listing()[0]['progress']['percent']==54
    log.write_text(text+'\nSTAGE Save immutable concept\n','utf-8')
    assert jobs.listing()[0]['progress']['percent'] is None
    assert jobs.listing()[0]['progress']['stage']=='Save immutable concept'
    assert jobs.get(job['id'])['status']=='RUNNING'  # Log reading never changes job state.


def test_unknown_invalid_values_and_phase_boundaries_do_not_invent_progress():
    assert parse('Loading weights\n','RUNNING')['percent'] is None
    assert parse('STAGE load\nDenoising: 101%|\n','RUNNING')['percent'] is None
    assert parse('AFS_FRAME 5/10\nSTAGE encode\n','RUNNING')['percent'] is None
    assert parse('STAGE encode\nAFS_FRAME 5/10\n','RUNNING')['percent'] is None
    assert parse('STAGE render\nAFS_FRAME 5/10\n','RUNNING')['percent']==50
