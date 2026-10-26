import hashlib
import http.server
import threading
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from apps.api import components
from apps.api.main import app

DATA = bytes(range(256)) * 4096  # 1 MiB


class Handler(http.server.BaseHTTPRequestHandler):
    interrupt_once = True

    def log_message(self, *a): pass

    def do_GET(self):
        start = 0
        header = self.headers.get('Range')
        if header: start = int(header.split('=')[1].split('-')[0])
        body = DATA[start:]
        self.send_response(206 if header else 200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        if Handler.interrupt_once and not header:
            Handler.interrupt_once = False
            self.wfile.write(body[:300_000]); self.wfile.flush(); self.connection.close(); return
        self.wfile.write(body)


@pytest.fixture
def server():
    Handler.interrupt_once = True
    httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{httpd.server_port}/file.bin'
    httpd.shutdown()


def test_download_resumes_after_a_dropped_connection_and_verifies(server, tmp_path, monkeypatch):
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    got = []
    target = components.download(server, tmp_path / 'a/file.bin', hashlib.sha256(DATA).hexdigest(), len(DATA), got.append)
    assert target.read_bytes() == DATA and not (tmp_path / 'a/file.bin.part').exists() and sum(got) == len(DATA)
    assert components.download(server, target, hashlib.sha256(DATA).hexdigest(), len(DATA)) == target  # already complete: no new request needed


def test_wrong_checksum_is_refused_and_removed(server, tmp_path, monkeypatch):
    monkeypatch.setattr(time, 'sleep', lambda s: None)
    Handler.interrupt_once = False
    with pytest.raises(OSError, match='Checksum mismatch'):
        components.download(server, tmp_path / 'file.bin', 'f' * 64, len(DATA))
    assert not (tmp_path / 'file.bin').exists() and not (tmp_path / 'file.bin.part').exists()


def test_extract_strips_the_top_folder_and_rejects_unsafe_paths(tmp_path):
    good = tmp_path / 'good.zip'
    with zipfile.ZipFile(good, 'w') as z: z.writestr('pkg/code/a.txt', 'x'); z.writestr('pkg/tools/b.txt', 'y')
    assert components.top_folder(good) == 'pkg/'
    components.extract(good, tmp_path / 'out', 'pkg/')
    assert (tmp_path / 'out/code/a.txt').read_text() == 'x'
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(bad, 'w') as z: z.writestr('../evil.txt', 'z')
    with pytest.raises(OSError, match='Unsafe'): components.extract(bad, tmp_path / 'out2')


def test_install_runs_in_dependency_order_reports_failures_and_checks_space(monkeypatch):
    client = TestClient(app)
    seen, done = [], set()
    monkeypatch.setattr(components, 'present', lambda i: i in done)
    def fake(i, fail=False):
        def run():
            seen.append(i)
            if fail: raise OSError('boom')
            done.add(i)
        return run
    monkeypatch.setattr(components, 'INSTALLERS', {i: fake(i, i == 'blender') for i in components.INFO})
    monkeypatch.setattr(components.shutil, 'disk_usage', lambda p: type('U', (), dict(free=10**13))())
    assert client.post('/api/components/install', json={'ids': ['klein_env']}).status_code == 202
    for _ in range(100):
        if not components.listing()['running']: break
        time.sleep(.05)
    assert seen == ['trellis_bundle', 'klein_env']  # prerequisite first
    rows = {r['id']: r for r in client.get('/api/components').json()['components']}
    assert rows['klein_env']['status'] == 'installed' and rows['blender']['status'] == 'missing'
    seen.clear()
    client.post('/api/components/install', json={'ids': ['blender']})
    for _ in range(100):
        if not components.listing()['running']: break
        time.sleep(.05)
    rows = {r['id']: r for r in client.get('/api/components').json()['components']}
    assert rows['blender']['status'] == 'failed' and 'boom' in rows['blender']['error']
    monkeypatch.setattr(components.shutil, 'disk_usage', lambda p: type('U', (), dict(free=10**9))())
    assert client.post('/api/components/install', json={'ids': ['qwen']}).status_code == 409
    assert client.post('/api/components/install', json={'ids': ['nope']}).status_code == 400


def test_features_map_what_you_create_to_the_parts_it_needs(monkeypatch):
    monkeypatch.setattr(components, 'present', lambda i: i in {'klein_env', 'klein_weights', 'ollama', 'qwen'})
    features = {f['id']: f for f in components.listing()['features']}
    assert features['sprites']['ready'] and features['sprites']['missing_bytes'] == 0
    assert not features['models']['ready'] and features['models']['missing_bytes'] > 0
    assert 'trellis_env' in features['models']['needs'] and 'trellis_env' not in features['sprites']['needs']
    assert features['map']['needs'] == [] and features['map']['ready'] is False or features['map']['available']
    assert features['motion']['available'] is False


def test_a_complete_partial_file_is_verified_instead_of_failing_with_416(tmp_path, monkeypatch):
    import io
    import urllib.error
    part = tmp_path / 'f.bin.part'; part.write_bytes(DATA)
    def deny(url, start=0): raise urllib.error.HTTPError(url, 416, 'Range Not Satisfiable', {}, io.BytesIO())
    monkeypatch.setattr(components, '_open', deny)
    assert components.download('http://x/f.bin', tmp_path / 'f.bin', hashlib.sha256(DATA).hexdigest(), len(DATA)).read_bytes() == DATA
