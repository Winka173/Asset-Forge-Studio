"""Admission arithmetic with controlled RAM readings; never simulated successful AI output."""
import json
import subprocess
import sys
import time
from types import SimpleNamespace

from apps.api import host_resources as host,jobs,store


def setup(tmp_path,monkeypatch,available):
    monkeypatch.setattr(store,'DATA',tmp_path/'Library')
    monkeypatch.setattr(jobs,'LOCK_ROOT',tmp_path/'locks')
    monkeypatch.setattr(jobs,'WORKER_LOCK',tmp_path/'locks/gpu.lock')
    monkeypatch.setattr(host.psutil,'virtual_memory',lambda:SimpleNamespace(available=available))


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
    first=host.estimate(payload);assert first['bytes']>9*host.GIB
    host.record_peak(payload,'smaller-stage',[dict(worker_tree_rss_bytes=2*host.GIB)])
    assert host.estimate(payload)['bytes']==first['bytes']
    monkeypatch.setattr(store,'DATA',tmp_path/'OtherLibrary')
    assert host.estimate(payload)['bytes']<first['bytes']
    assert payload['effective_config_hash']=='unchanged'


def test_unknown_claim_is_visible_and_never_silently_discarded(tmp_path,monkeypatch):
    setup(tmp_path,monkeypatch,64*host.GIB)
    ledger=jobs.LOCK_ROOT/'host-ram';ledger.mkdir(parents=True);broken=ledger/'broken.json';broken.write_text('{}','utf-8')
    job=jobs.enqueue(dict(kind='procedural_geometry'));receipt,_=host.check(job,'cpu')
    assert not receipt['allowed'] and 'unreadable' in receipt['reason']
    assert broken.read_text()=='{}'
