"""TRELLIS.2 is the only 3D engine; the removed ones are archived (docs/REMOVED_ENGINES.md)."""
from engines.adapters import ADAPTERS, REQUIREMENTS, SHAPE_ENGINES


def test_trellis2_is_the_only_engine_with_full_pbr():
    assert list(ADAPTERS) == ['trellis2_community'] and list(REQUIREMENTS) == ['trellis2_community'] and SHAPE_ENGINES == ()
    assert 'pbr' in ADAPTERS['trellis2_community'].capabilities
