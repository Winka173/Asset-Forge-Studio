"""The downloadable batch examples must import exactly as documented."""
from pathlib import Path

import pytest

from apps.api.manifest import parse

EXAMPLES = Path(__file__).resolve().parents[1] / 'apps/web/src/prompt-examples'
IDS = ['PROP_OAK_BARREL', 'BLD_ARCHER_TOWER_T1', 'BLD_ARCHER_TOWER_T2', 'UNIT_KNIGHT', 'FUT_BOSS_FROST_WYVERN']


@pytest.mark.parametrize('name', ['batch-blocks.md', 'batch-table.md', 'batch.csv', 'batch.json'])
def test_every_batch_example_imports_the_same_five_assets(name):
    items, _ = parse((EXAMPLES / name).read_text(encoding='utf-8'))
    assert [i['source_asset_id'] for i in items] == IDS
    tower = items[1]
    assert (tower['target_width_m'], tower['target_depth_m'], tower['target_height_m']) == (5, 5, 10) and tower['prompt']
    assert items[4]['source_status'] == 'FUTURE'
    if name != 'batch-blocks.md':
        assert items[2]['dependencies'] == ['BLD_ARCHER_TOWER_T1'] and items[3]['quality'] == 'Maximum' and items[0]['expected_materials'] == ['oak', 'wrought iron']
