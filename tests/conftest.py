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
def single_concept_by_default(monkeypatch):
    """Queue-invariant suites count jobs per asset; the concept tournament has its own dedicated tests."""
    from apps.api import automation
    monkeypatch.setattr(automation,'CONCEPT_CANDIDATES',{'Maximum':1,'Balanced':1,'Fast':1})


@pytest.fixture(autouse=True)
def no_implicit_local_llm_inference(monkeypatch):
    """Unit/API suites never start installed multi-GB models implicitly. Real acceptance is separate."""
    monkeypatch.setenv("AFS_INTENT_ENABLED","0")


@pytest.fixture(autouse=True)
def _no_real_batch_style(monkeypatch):
    """Batch analysis writes a shared style with the local model; tests must not load it."""
    import engines.batch_style as batch_style
    monkeypatch.setattr(batch_style, 'derive', lambda *a, **k: 'test shared style')
    from apps.api import batch
    monkeypatch.setattr(batch, 'STYLE_ASYNC', False)
