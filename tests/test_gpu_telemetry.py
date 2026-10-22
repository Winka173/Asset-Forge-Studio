"""Read-only real host telemetry: no fabricated GPU readings."""
from fastapi.testclient import TestClient
from apps.api.main import app


def test_gpu_telemetry_is_uncached_and_explicit_about_availability():
    client=TestClient(app)
    first=client.get('/api/gpu');second=client.get('/api/gpu')
    assert first.status_code==second.status_code==200
    assert first.headers['cache-control']==second.headers['cache-control']=='no-store'
    a,b=first.json(),second.json()
    for value in (a,b):
        if value['available']:
            assert 0<=value['used_mib']<=value['total_mib']
            assert 0<=value['utilization_percent']<=100
            assert value['sampled_at'] and value['name']
        else:assert value['reason']
    if a['available'] and b['available']:assert a['sampled_at']!=b['sampled_at']
