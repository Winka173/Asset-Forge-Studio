import json
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from apps.api import store,jobs

@pytest.fixture
def client(tmp_path,monkeypatch,qa_project):
    monkeypatch.setattr(store,'DATA',tmp_path);qa_project();return TestClient(app)

def make(tmp_path,name):
    asset=dict(id=name+'-id',project_id='runavelle',name=name,prompt='p',settings={},approvals=[],status='Candidate',created_at=store.now())
    with store.connect() as db:db.execute('INSERT INTO assets VALUES (?,?,?)',(asset['id'],'runavelle',json.dumps(asset)))
    job=jobs.enqueue(dict(kind='concept',project_id='runavelle',asset_id=asset['id']))
    folder=tmp_path/'jobs'/job['id'];folder.mkdir(parents=True);(folder/'big.bin').write_bytes(b'x'*1000)
    out=tmp_path/'projects'/'runavelle'/'outputs';out.mkdir(parents=True,exist_ok=True);f=out/f'{name}.glb';f.write_bytes(b'glTF'+name.encode())
    art=store.add_artifact(f,'candidate',name,dict(project_id='runavelle',asset_id=asset['id']))
    with store.connect() as db:db.execute('INSERT INTO batches VALUES (?,?,?)',('b1','runavelle',json.dumps(dict(id='b1',project_id='runavelle',name='B',items=[dict(asset_id=asset['id'],name=name)])))) if name=='Bad' else None
    return asset,job,folder,f,art

def test_delete_removes_every_file_and_record_of_only_that_asset(client,tmp_path):
    bad,job,folder,glb,art=make(tmp_path,'Bad');keep,kjob,kfolder,kglb,kart=make(tmp_path,'Keep')
    plan=client.get(f"/api/asset-delete/{bad['id']}").json()
    assert plan['jobs']==1 and plan['artifacts']==1 and plan['library_bytes']>=1000 and plan['active_jobs']==1
    assert client.post(f"/api/asset-delete/{bad['id']}",json=dict(confirm_name='wrong')).status_code==400
    done=client.post(f"/api/asset-delete/{bad['id']}",json=dict(confirm_name='Bad')).json()
    assert done['status']=='DELETED' and not folder.exists() and not glb.exists()
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM assets WHERE id=?',(bad['id'],)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM artifacts WHERE asset_id=?',(bad['id'],)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM batches WHERE id=?',('b1',)).fetchone()[0]==0
    assert kfolder.exists() and kglb.exists() and jobs.get(kjob['id'])

def test_batch_model_choice_applies_only_to_items_not_started(client):
    from apps.api import batch as batches
    value=dict(id='bm',project_id='runavelle',name='B',mode='Quality Batch',paused=True,items=[dict(asset_id='a',name='A',started=True,engines=[],preferred_engine='auto',texturer=''),dict(asset_id='b',name='B',engines=[],preferred_engine='auto',texturer='')])
    with store.connect() as db:db.execute('INSERT INTO batches VALUES (?,?,?)',('bm','runavelle',json.dumps(value)))
    import unittest.mock as m
    with m.patch.object(batches,'detail',lambda v:dict(items=v['items'])),m.patch.object(batches,'save',lambda v:None),m.patch.object(batches,'batch',lambda i:value):
        out=client.post('/api/batches/bm/models',json=dict(engines=['triposg'],texturer='trellis2')).json()
    a,b=out['items'];assert out['models_applied']==1 and a['preferred_engine']=='auto' and b['preferred_engine']=='triposg' and b['texturer']=='trellis2'

def test_batch_keep_final_option_is_saved(client):
    from apps.api import batch as batches
    value=dict(id='bk',project_id='runavelle',name='B',mode='Quality Batch',paused=True,items=[])
    import unittest.mock as m
    with m.patch.object(batches,'detail',lambda v:v),m.patch.object(batches,'save',lambda v:None),m.patch.object(batches,'batch',lambda i:value):
        assert client.post('/api/batches/bk/options',json=dict(keep_final_only=True)).json()['keep_final_only'] is True
