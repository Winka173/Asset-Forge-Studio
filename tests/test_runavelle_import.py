"""Acceptance uses the user's actual large source, never a generated 349-row substitute."""
import hashlib
import json
import os
import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from apps.api import store,jobs
from apps.api.main import app
from apps.api.manifest import parse,MAX_MANIFEST_CHARACTERS
from engines.local_semantics import chunks,SemanticMetadata,endpoint


@pytest.fixture
def source():
    file=Path(os.environ.get('AFS_RUNAVELLE_SOURCE',str(Path.home()/'Downloads/Runavelle_V4_ALL_349_Model_Prompts.md')))
    if not file.is_file():pytest.skip('Actual Runavelle V4 source not supplied; set AFS_RUNAVELLE_SOURCE')
    content=file.read_bytes();return file,content,content.decode('utf-8-sig')


def test_actual_source_all_spans_hashes_and_counts(source):
    _,content,text=source
    headings=list(re.finditer(r'^# ([A-Z][A-Z0-9]*_[A-Za-z0-9_]+)[ \t]+[\u2014\u2013-][ \t]+([^\r\n]+)',text,re.M))
    rows,_=parse(text)
    assert len(headings)==len(rows)==349
    assert len({i['source_asset_id'] for i in rows})==349
    assert sum(i['source_status']=='FUTURE' for i in rows)==37
    assert sum(i['selected'] for i in rows)==349
    lines=text.splitlines(keepends=True)
    for index,(row,heading) in enumerate(zip(rows,headings)):
        stop=headings[index+1].start() if index+1<len(headings) else len(text)
        original=text[heading.start():stop]
        assert row['source_asset_id']==heading[1]
        assert row['prompt']==original==text[row['source_char_start']:row['source_char_end']]
        assert row['prompt']==''.join(lines[row['source_line_start']-1:row['source_line_end']])
        assert row['source_sha256']==hashlib.sha256(original.encode()).hexdigest()
        assert not row['confirmed']
        assert ''.join(chunk for _,_,chunk in chunks(original))==original


def test_actual_large_file_api_lossless_review_selection_queue(source,tmp_path,monkeypatch,qa_project):
    file,content,text=source;monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    # No lifespan worker: verify actual persisted scheduler admission without executing inference.
    client=TestClient(app)
    response=client.post('/api/batches/import',files={'file':(file.name,content,'text/markdown')},data=dict(project_id='runavelle',format='auto',mode='Maximum Quality Batch'))
    assert response.status_code==201,response.text[:1000]
    value=response.json();prefix='/api/batches/'+value['id'];diag=value['import_diagnostics']
    assert diag['parsed_count']==diag['expected_count']==349 and diag['primary_count']==312 and diag['future_count']==37
    assert not diag['local_ai_used'] and diag['parser_method']=='asset_id_heading_blocks'
    assert value['paused'] and jobs.listing()==[]
    assert client.get(prefix+'/source').content==content
    assert client.get(prefix+'/source?decoded=true').content.decode()==text
    assert value['source_file']['sha256']==hashlib.sha256(content).hexdigest()
    for item in value['items']:
        assert item['prompt']==text[item['source_char_start']:item['source_char_end']]
    chosen=value['items'][:3];ids=[i['asset_id'] for i in chosen]
    selected=client.post(prefix+'/selection',json=dict(selected_ids=ids)).json()
    assert sum(i['selected'] for i in selected['items'])==3 and jobs.listing()==[]
    assert client.post(prefix+'/selection',json=dict(selected_ids=['foreign'])).status_code==400
    assert client.post(prefix+'/run',json=dict(selected_ids=ids)).status_code==409
    for item in chosen:
        response=client.post(prefix+'/items/'+item['asset_id'],json=dict(confirmed=True))
        assert response.status_code==200,response.text[:1000]
    response=client.post(prefix+'/run',json=dict(selected_ids=ids))
    assert response.status_code==200,response.text[:1000]
    queued=jobs.listing();assert len(queued)==3
    for item in chosen:
        job=next(j for j in queued if j['payload']['asset_id']==item['asset_id'])
        assert job['status']=='QUEUED' and job['payload']['kind']=='concept'
        assert job['payload']['user_prompt']==item['prompt']
        assert job['payload']['prompt'].startswith(item['prompt'])  # existing project/style suffix is separate
    assert client.post(prefix+'/run',json=dict(selected_ids=ids)).status_code==200
    assert len(jobs.listing())==3  # request refresh/retry does not duplicate independent concepts
    invalid=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='x'*(MAX_MANIFEST_CHARACTERS+1)))
    assert invalid.status_code==422 and len(invalid.content)<1000
    assert 'input' not in invalid.json()['detail'][0] and 'ctx' not in invalid.json()['detail'][0]


def test_import_validation_and_local_semantic_boundaries(monkeypatch):
    with pytest.raises(ValueError,match='Duplicate source'):
        parse('# BLD_A_T1 \u2014 First\nOne body\n# BLD_A_T1 \u2014 Second\nTwo body')
    with pytest.raises(ValueError,match='empty prompt body'):parse('# BLD_A_T1 \u2014 Empty\n---\n')
    with pytest.raises(ValueError,match='declares 3'):parse('# ALL 3 PROMPTS\n# BLD_A_T1 \u2014 One\nFull prompt\n')
    with pytest.raises(ValueError):SemanticMetadata.model_validate(dict(source_asset_id='a',width_m=-1))
    with pytest.raises(ValueError):SemanticMetadata.model_validate(dict(source_asset_id='a',prompt='Rewrite source'))
    monkeypatch.setenv('AFS_OLLAMA_URL','https://paid.example.com')
    with pytest.raises(ValueError,match='loopback'):endpoint()


def test_actual_batch_image_upload_and_individual_reference_persist_losslessly(source,tmp_path,monkeypatch,qa_project):
    file,content,text=source
    image=store.ROOT/'.local/fixtures/ArcherTowerSource.png'
    if not image.is_file():pytest.skip('Real Archer reference unavailable')
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    uploaded=client.post('/api/import/reference?project_id=runavelle',files={'file':(image.name,image.read_bytes(),'image/png')})
    assert uploaded.status_code==201,uploaded.text
    reference=uploaded.json()
    assert reference['sha256']==hashlib.sha256(image.read_bytes()).hexdigest()
    assert client.get(reference['url']).content==image.read_bytes()
    imported=client.post('/api/batches/import',files={'file':(file.name,content,'text/markdown')},data=dict(project_id='runavelle',reference_ids=json.dumps([reference['id']])))
    assert imported.status_code==201,imported.text[:500]
    value=imported.json();assert len(value['items'])==349 and jobs.listing()==[]
    for item in value['items']:
        assert item['reference_ids']==[reference['id']]
        assert item['prompt']==text[item['source_char_start']:item['source_char_end']]
        assert item['source_sha256']==hashlib.sha256(item['prompt'].encode()).hexdigest()
    first=value['items'][0];prefix='/api/batches/'+value['id']
    other=client.post('/api/projects',json=dict(name='Unrelated game')).json()
    foreign=client.post('/api/import/reference?project_id='+other['id'],files={'file':(image.name,image.read_bytes(),'image/png')}).json()
    assert client.post(prefix+'/items/'+first['asset_id'],json=dict(reference_ids=[foreign['id']])).status_code==400
    assert client.post(prefix+'/items/'+first['asset_id'],json=dict(reference_ids=[])).status_code==200
    assert client.get(prefix).json()['items'][0]['reference_ids']==[]
    assert jobs.listing()==[]


def test_unavailable_local_analysis_does_not_submit_jobs(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project()
    monkeypatch.setenv('AFS_OLLAMA_URL','http://127.0.0.1:1')
    client=TestClient(app)
    value=client.post('/api/batches/analyze',json=dict(project_id='runavelle',master_prompt='- Local test prompt')).json()
    probe=client.get('/api/batch-analysis/local-models').json()
    assert not probe['available'] and not probe['models']
    response=client.post('/api/batch-analysis/'+value['id'],json=dict(model='not-installed',selected_ids=[value['items'][0]['asset_id']]))
    assert response.status_code==503 and jobs.listing()==[]
