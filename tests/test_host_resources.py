"""Admission arithmetic with controlled RAM readings; never simulated successful AI output."""
import json
import subprocess
import sys
import time
import pytest
from types import SimpleNamespace

from apps.api import host_resources as host,jobs,store


def setup(tmp_path,monkeypatch,available):
    monkeypatch.setattr(store,'DATA',tmp_path/'Library')
    monkeypatch.setattr(jobs,'LOCK_ROOT',tmp_path/'locks')
    monkeypatch.setattr(jobs,'WORKER_LOCK',tmp_path/'locks/gpu.lock')
    monkeypatch.setattr(host.psutil,'virtual_memory',lambda:SimpleNamespace(available=available))
    monkeypatch.setattr(host,'commit_memory',lambda:dict(status='measured',available_bytes=64*host.GIB))


def test_ram_wait_preserves_queue_and_quality_and_allows_lighter_stage(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,12*host.GIB)
    payload=dict(kind='inference',engine='unknown_unavailable_test_engine',effective_config_hash='immutable',quality='Maximum')
    job=jobs.enqueue(payload);before=json.dumps(job['payload'],sort_keys=True)
    jobs.worker.managed(job,'gpu')
    assert jobs.get(job['id'])['status']=='QUEUED'
    assert json.dumps(jobs.get(job['id'])['payload'],sort_keys=True)==before
    assert jobs.listing()[0]['progress']['reason_code']=='HOST_RAM_ADMISSION'
    assert not list(store.DATA.rglob('*.glb'))
    lighter=jobs.enqueue(dict(kind='procedural_geometry'))
    assert host.check(lighter,'cpu')[0]['allowed']


def test_unrealized_claim_prevents_early_overlap_and_is_released(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,30*host.GIB)
    heavy=jobs.enqueue(dict(kind='inference',engine='unknown_unavailable_test_engine'))
    large_cpu=jobs.enqueue(dict(kind='blender'))
    light_cpu=jobs.enqueue(dict(kind='procedural_geometry'))
    with host.reserve(heavy,'gpu') as receipt:
        assert receipt['allowed']
        assert not host.check(large_cpu,'cpu')[0]['allowed']
        assert host.check(light_cpu,'cpu')[0]['allowed']
        assert len(list((jobs.LOCK_ROOT/'host-ram').glob('*.json')))==1
    assert not list((jobs.LOCK_ROOT/'host-ram').glob('*.json'))
    assert host.check(large_cpu,'cpu')[0]['allowed']


def test_owned_orphan_child_holds_gpu_without_blocking_safe_cpu(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,64*host.GIB)
    identifier='owned-orphan';folder=store.DATA/'jobs'/identifier;folder.mkdir(parents=True)
    child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)',str(folder)])
    try:
        (folder/'process.json').write_text(json.dumps(dict(pid=child.pid)),'utf-8')
        ledger=jobs.LOCK_ROOT/'host-ram';ledger.mkdir(parents=True)
        claim=ledger/'owned-test.json';claim.write_text(json.dumps(dict(job_id=identifier,job_folder=str(folder),resource='gpu',owner_pid=999999999,owner_created=0,owner_thread=0,reserved_at=time.time()-1,allowance_bytes=24*host.GIB)),'utf-8')
        queued=jobs.enqueue(dict(kind='procedural_geometry'))
        assert not host.check(queued,'gpu')[0]['allowed']
        assert host.check(queued,'cpu')[0]['allowed']
        assert claim.exists()
    finally:child.terminate();child.wait(timeout=10)
    assert host.check(queued,'gpu')[0]['allowed']
    assert not claim.exists()


def test_measured_allowance_is_monotonic_and_scoped_to_library(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,64*host.GIB);payload=dict(kind='procedural_geometry',effective_config_hash='unchanged')
    host.record_peak(payload,'measured-stage',[dict(worker_tree_rss_bytes=5*host.GIB,worker_tree_private_bytes=9*host.GIB)])
    first=host.estimate(payload);assert first['bytes']>5*host.GIB and first['commit_bytes']>9*host.GIB
    host.record_peak(payload,'smaller-stage',[dict(worker_tree_rss_bytes=2*host.GIB)])
    assert host.estimate(payload)['bytes']==first['bytes']
    assert host.estimate(payload)['commit_bytes']==first['commit_bytes']
    monkeypatch.setattr(store,'DATA',tmp_path/'OtherLibrary')
    assert host.estimate(payload)['bytes']<first['bytes']
    assert payload['effective_config_hash']=='unchanged'


def test_separate_resident_and_commit_allowances_allow_safe_measured_profile(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,9*host.GIB)
    payload=dict(kind='procedural_geometry',effective_config_hash='original-quality')
    host.record_peak(payload,'real-counter-arithmetic',[dict(worker_tree_rss_bytes=5*host.GIB,worker_tree_private_bytes=9*host.GIB)])
    job=jobs.enqueue(payload);before=json.dumps(job['payload'],sort_keys=True)
    receipt,_=host.check(job,'cpu')
    assert receipt['allowed'] and receipt['allowance']['bytes']<receipt['allowance']['commit_bytes']
    assert receipt['available_bytes']<receipt['allowance']['commit_bytes']+host.HEADROOM
    assert receipt['quality_settings_changed'] is False
    monkeypatch.setattr(host,'commit_memory',lambda:dict(status='measured',available_bytes=12*host.GIB))
    receipt,_=host.check(job,'cpu')
    assert not receipt['allowed'] and receipt['reason_code']=='HOST_COMMIT_ADMISSION'
    assert 'Windows commit' in receipt['reason'] and jobs.get(job['id'])['status']=='QUEUED'
    assert json.dumps(jobs.get(job['id'])['payload'],sort_keys=True)==before
    monkeypatch.setattr(host,'commit_memory',lambda:dict(status='measured',available_bytes=64*host.GIB))
    monkeypatch.setattr(host.psutil,'virtual_memory',lambda:SimpleNamespace(available=7*host.GIB))  # 5 GiB peak -> 5.9 GiB allowance + 2 GiB reserve
    assert host.check(job,'cpu')[0]['reason_code']=='HOST_RAM_ADMISSION'
    assert not list(store.DATA.rglob('*.glb'))


def test_commit_claims_are_independent_and_released(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,20*host.GIB)
    monkeypatch.setattr(host,'commit_memory',lambda:dict(status='measured',available_bytes=20*host.GIB))
    payload=dict(kind='procedural_geometry')
    host.record_peak(payload,'arithmetic-only',[dict(worker_tree_rss_bytes=5*host.GIB,worker_tree_private_bytes=9*host.GIB)])
    first=jobs.enqueue(payload);second=jobs.enqueue(payload)
    with host.reserve(first,'cpu') as receipt:
        assert receipt['allowed']
        blocked=host.check(second,'cpu')[0]
        assert not blocked['allowed'] and blocked['reason_code']=='HOST_COMMIT_ADMISSION'
        assert blocked['usable_bytes']>blocked['allowance']['bytes']+host.HEADROOM
        assert blocked['unrealized_commit_reserved_bytes']>blocked['unrealized_reserved_bytes']
    assert host.check(second,'cpu')[0]['allowed']


def test_legacy_observations_split_only_from_valid_same_job_samples(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,9*host.GIB);payload=dict(kind='procedural_geometry')
    original=jobs.enqueue(payload);key=host.profile(payload)[0]
    legacy=dict(schema_version=1,peak_bytes=9*host.GIB,allowance_bytes=int(9*host.GIB*1.15)+host.GIB,job_id=original['id'])
    with store.connect() as db:db.execute('INSERT INTO drafts VALUES (?,?)',(key,json.dumps(legacy)))
    assert not host.check(original,'cpu')[0]['allowed']
    folder=store.DATA/'jobs'/original['id'];folder.mkdir(exist_ok=True,parents=True)
    report=dict(worker_tree_peak_rss_bytes=5*host.GIB,worker_tree_peak_private_bytes=9*host.GIB,
        samples=[dict(worker_tree_rss_bytes=5*host.GIB,worker_tree_private_bytes=9*host.GIB)])
    (folder/'resources.json').write_text(json.dumps(report),'utf-8');host._estimates.clear()
    result=host.check(original,'cpu')[0]
    assert result['allowed'] and result['allowance']['observed']['schema_version']==2
    with store.connect() as db:assert json.loads(db.execute('SELECT payload FROM drafts WHERE project_id=?',(key,)).fetchone()['payload'])['schema_version']==2


def test_unavailable_commit_measurement_blocks_without_new_claim(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,64*host.GIB)
    monkeypatch.setattr(host,'commit_memory',lambda:dict(status='unavailable',reason='Declared measurement fault'))
    with host.reserve(jobs.enqueue(dict(kind='procedural_geometry')),'cpu') as receipt:
        assert not receipt['allowed'] and receipt['reason_code']=='HOST_COMMIT_ADMISSION'
    assert not list((jobs.LOCK_ROOT/'host-ram').glob('*.json'))


def test_actual_windows_commit_counters():
    import os,pytest
    if os.name!='nt':pytest.skip('Windows system API only')
    from apps.api.host_memory import commit_memory
    result=commit_memory()
    assert result['status']=='measured'
    assert 0<=result['available_bytes']<=result['limit_bytes']
    assert result['used_bytes']+result['available_bytes']==result['limit_bytes']


@pytest.mark.parametrize('fault',['missing_samples','wrong_profile','inconsistent_header','unknown_job'])
def test_legacy_peak_with_unproven_origin_stays_conservative(tmp_path,monkeypatch,fault):
    setup(tmp_path,monkeypatch,9*host.GIB);payload=dict(kind='procedural_geometry')
    original=jobs.enqueue(dict(kind='blender') if fault=='wrong_profile' else payload);key=host.profile(payload)[0]
    legacy=dict(schema_version=1,peak_bytes=9*host.GIB,allowance_bytes=int(9*host.GIB*1.15)+host.GIB,
        job_id='no-such-job' if fault=='unknown_job' else original['id'])
    with store.connect() as db:db.execute('INSERT INTO drafts VALUES (?,?)',(key,json.dumps(legacy)))
    folder=store.DATA/'jobs'/legacy['job_id'];folder.mkdir(exist_ok=True,parents=True)
    report=dict(worker_tree_peak_rss_bytes=(4 if fault=='inconsistent_header' else 5)*host.GIB,
        worker_tree_peak_private_bytes=9*host.GIB,samples=[] if fault=='missing_samples' else [dict(worker_tree_rss_bytes=5*host.GIB,worker_tree_private_bytes=9*host.GIB)])
    (folder/'resources.json').write_text(json.dumps(report),'utf-8')
    probe=jobs.enqueue(payload);result=host.check(probe,'cpu')[0]
    assert not result['allowed'] and result['allowance']['observed']['schema_version']==1
    with store.connect() as db:assert json.loads(db.execute('SELECT payload FROM drafts WHERE project_id=?',(key,)).fetchone()['payload'])==legacy


def test_unknown_claim_is_visible_and_never_silently_discarded(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,64*host.GIB)
    ledger=jobs.LOCK_ROOT/'host-ram';ledger.mkdir(parents=True);broken=ledger/'broken.json';broken.write_text('{}','utf-8')
    job=jobs.enqueue(dict(kind='procedural_geometry'));receipt,_=host.check(job,'cpu')
    assert not receipt['allowed'] and 'unreadable' in receipt['reason']
    assert broken.read_text()=='{}'


def test_lone_gpu_stage_may_page_but_commit_stays_a_hard_gate(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,0)
    job=jobs.enqueue(dict(kind='inference',engine='unknown_unavailable_test_engine'))
    need=host.estimate(job['payload'])['bytes']
    monkeypatch.setattr(host.psutil,'virtual_memory',lambda:SimpleNamespace(available=need-4*host.GIB))
    assert host.check(job,'gpu')[0]['allowed'] and not host.check(job,'cpu')[0]['allowed']
    monkeypatch.setattr(host.psutil,'virtual_memory',lambda:SimpleNamespace(available=need-12*host.GIB))  # beyond the 10 GiB paging tolerance
    assert host.check(job,'gpu')[0]['reason_code']=='HOST_RAM_ADMISSION'
    monkeypatch.setattr(host.psutil,'virtual_memory',lambda:SimpleNamespace(available=need-4*host.GIB))
    monkeypatch.setattr(host,'commit_memory',lambda:dict(status='measured',available_bytes=8*host.GIB))
    assert host.check(job,'gpu')[0]['reason_code']=='HOST_COMMIT_ADMISSION'
