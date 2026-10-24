"""Shape engines run shape + MV-Adapter texture as one inference job and report what they need."""
from engines.adapters import ADAPTERS, REQUIREMENTS, SHAPE_ENGINES, TexturedShapeAdapter


def test_every_shape_engine_builds_a_textured_job(monkeypatch, tmp_path):
    for engine in SHAPE_ENGINES:
        adapter = ADAPTERS[engine]
        assert isinstance(adapter, TexturedShapeAdapter) and 'basecolor_texture' in adapter.capabilities and engine in REQUIREMENTS
        monkeypatch.setattr(adapter, 'probe', lambda: dict(installed=True))
        events = []
        command, cwd, request = adapter.generate(dict(request_path=str(tmp_path / 'r.json'), image='c.png', output=str(tmp_path / engine), seed=42, texture_size=2048), events.append)
        assert command[-3].endswith('textured_shape_worker.py') and command[-1] == str(tmp_path / 'r.json')
        assert request['shape_command'][-1].endswith({'triposg': 'triposg_worker.py', 'trellis_v1': 'sparse_research_worker.py', 'hunyuan3d21': 'hunyuan_worker.py'}[engine])
        assert request['uv_size'] == 2048 and request['texture_worker'].endswith('mvadapter_texture_worker.py') and request['u2net_home']
        assert events and events[0]['engine'] == engine


def test_trellis2_stays_the_full_pbr_default():
    assert 'pbr' in ADAPTERS['trellis2_community'].capabilities and 'trellis2_community' not in SHAPE_ENGINES
