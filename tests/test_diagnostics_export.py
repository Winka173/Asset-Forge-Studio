import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api import store
from apps.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch, qa_project):
    monkeypatch.setattr(store, 'DATA', tmp_path); qa_project(); return TestClient(app)


def test_support_report_has_logs_and_no_personal_data(client, monkeypatch, tmp_path):
    from apps.api import diagnostics_export as d, store
    cfg = tmp_path / 'cfg'; (cfg / 'logs').mkdir(parents=True)
    (cfg / 'logs/backend.log').write_text(f"started in {Path.home()} X-AFS-Token: {'a' * 40}\n", encoding='utf-8')
    monkeypatch.setenv('AFS_DESKTOP_CONFIG_DIR', str(cfg))
    created = client.post('/api/assets', json=dict(project_id='runavelle', name='Secret name', prompt='private prompt text')).json()
    response = client.post('/api/diagnostics/export')
    assert response.status_code == 200
    with zipfile.ZipFile(response.json()['path']) as bundle:
        names = bundle.namelist()
        assert {'system.json', 'jobs.json', 'logs/backend.log', 'README.txt'} <= set(names)
        everything = '\n'.join(bundle.read(n).decode('utf-8', 'replace') for n in names)
        assert str(Path.home()) not in everything and 'a' * 40 not in everything and 'private prompt text' not in everything
        assert json.loads(bundle.read('system.json'))['os']
