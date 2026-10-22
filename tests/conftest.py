import json
import pytest
from apps.api import store


@pytest.fixture
def qa_project():
    """Explicit legacy-compatible test project, never a production startup seed."""
    def create():
        value=dict(id='runavelle',name='Runavelle QA',description='Explicit test setup',art_bible=json.loads((store.ROOT/'presets/runavelle.json').read_text(encoding='utf-8')),
                   palette=[],material_language='',default_style='',units='m',target_height_m=10,export_settings={},cover_artifact_id=None)
        with store.connect() as db:db.execute('INSERT INTO projects VALUES (?,?,0)',('runavelle',json.dumps(value)))
    return create


@pytest.fixture(autouse=True)
def no_implicit_local_llm_inference(monkeypatch):
    """Unit/API suites never start installed multi-GB models implicitly. Real acceptance is separate."""
    monkeypatch.setenv("AFS_INTENT_ENABLED","0")
