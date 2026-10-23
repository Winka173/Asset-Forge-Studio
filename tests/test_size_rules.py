"""Provisional sizes by asset type so a batch is scaled sensibly without per-item previews."""
import pytest
from apps.api.size_rules import suggest, apply


@pytest.mark.parametrize('text,rule,height', [
    ('Giant red dragon boss', 'dragon', 12.8), ('tôi muốn model là boss 1 con rồng khổng lồ đỏ', 'dragon', 12.8),
    ('Swordsman with shield', 'character', 1.8), ('kiếm sĩ với khiên', 'character', 1.8),
    ("A knight's longsword with an ornate gold crossguard", 'sword', 1.1), ('Supply_Barrel', 'barrel', 1.0),
    ('Wood_Crate', 'crate', 0.8), ('Archer tower T3', 'tower', 12), ('tháp canh', 'tower', 12), ('thùng gỗ', 'crate', 0.8),
    ('MANA WELL T2 Runic Conduit', 'well', 3), ('Ember Highlands Tree 01', 'tree', 7), ('small house', 'house', 3.6),
])
def test_head_noun_and_modifiers_pick_a_plausible_size(text, rule, height):
    found = suggest(text)
    assert found['rule'] == rule and found['dims']['h'] == pytest.approx(height)


def test_type_rule_never_overrides_explicit_or_inherited_sizes_and_follows_an_explicit_height():
    item = dict(target_height_m=9.0, target_width_m=None, target_depth_m=None,
                spec_provenance=dict(target_height_m=dict(kind='explicit', source='prompt', value=9.0)))
    assert apply(item, 'stone tower')
    assert item['target_height_m'] == 9.0 and item['target_width_m'] == 3.0 and item['spec_provenance']['target_width_m']['kind'] == 'inferred'
    inherited = dict(target_width_m=5.0, target_depth_m=5.0, target_height_m=5.0, spec_provenance={k: dict(kind='inherited') for k in ('target_width_m', 'target_depth_m', 'target_height_m')})
    assert not apply(inherited, 'giant dragon') and inherited['target_height_m'] == 5.0


def test_prompt_analysis_refines_a_rule_or_default_size():
    item = dict(target_width_m=1.0, target_depth_m=1.0, target_height_m=1.0,
                spec_provenance={k: dict(kind='defaulted', source='category') for k in ('target_width_m', 'target_depth_m', 'target_height_m')})
    assert apply(item, 'giant red dragon boss') and item['target_height_m'] == 12.8
    assert apply(item, 'swordsman with a shield') and item['target_height_m'] == 1.8  # an earlier rule size is refined, not frozen
