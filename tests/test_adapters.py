import subprocess
import sys

from fastapi.testclient import TestClient

from apps.api.main import app
from engines.adapters import ADAPTERS


def test_adapter_cancel_terminates_real_owned_process():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        result = ADAPTERS['triposg'].cancel({'process': process})
        assert result['status'] == 'TERMINATED'
        assert process.poll() is not None
    finally:
        if process.poll() is None: process.kill(); process.wait()


def test_separate_frontend_origin_and_tournament_input_guards():
    client = TestClient(app)
    response = client.options('/api/jobs/tournament', headers={'Origin': 'http://127.0.0.1:5173',
        'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'
    assert client.post('/api/jobs/tournament', json={'engine': 'triposg', 'artifact_id': 'unused', 'seeds': [42,42]}).status_code == 400
    assert client.post('/api/jobs/tournament', json={'engine': 'paid_cloud', 'artifact_id': 'unused'}).status_code == 422
