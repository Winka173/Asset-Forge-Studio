import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from apps.api import store,jobs,batch,studio
from apps.api.main import app


def test_new_subject_uses_concept_not_reference_mesh(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();client=TestClient(app)
    prompt='tạo cho tôi 1 căn lâu đài có style tương tự hình ref'
    asset=client.post('/api/assets',json=dict(project_id='runavelle',name='Castle',prompt=prompt)).json()
    image=io.BytesIO();Image.new('RGB',(32,32),(22,45,90)).save(image,format='PNG')
    ref=client.post('/api/import/reference',params=dict(project_id='runavelle',asset_id=asset['id']),files=dict(file=('tower.png',image.getvalue()))).json()
    response=client.post('/api/automation/single',json=dict(asset_id=asset['id'],reference_id=ref['id'],reference_usage='palette_style',request_id='palette-castle-source-01'))
    assert response.status_code==201,response.text
    created=jobs.listing();assert len(created)==1 and created[0]['payload']['kind']=='concept'
    payload=created[0]['payload'];assert payload['user_prompt']==prompt and 'castle, broad fortified complex' in payload['prompt']
    assert payload['reference_direction']['references'][0]['sha256']==ref['sha256']
    assert payload['effective_config']['reference_hashes']==[ref['sha256']]
    item=batch.batch(response.json()['batch_id'])['items'][0]
    assert item['reference_ids']==[] and item['style_reference_ids']==[ref['id']]
    assert studio.asset(asset['id'])['original_prompt']==prompt
    assert client.post('/api/automation/single',json=dict(asset_id=asset['id'],reference_id=ref['id'],reference_usage='palette_style',request_id='palette-castle-source-01')).status_code==201
    assert len(jobs.listing())==1
    # Actual image hash validation, not a mocked AI result.
    store.safe_path(ref['relative_path']).write_bytes(b'changed')
    from apps.api.reference_direction import concept_direction
    with pytest.raises(ValueError,match='checksum'):concept_direction(prompt,[ref['id']],'runavelle')
