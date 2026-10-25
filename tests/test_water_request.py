from apps.api.revisions import WATER_REQUEST, water_level


def test_water_prompts_add_or_move_one_surface():
    assert water_level('thêm nước mana vào trong giếng') == {} and WATER_REQUEST.search('thêm nước mana vào trong giếng')
    assert water_level('cho nước cao hơn nữa, đang hơi thấp') == dict(mode='higher')
    assert water_level('cho nước cao hơn nữa, gần rìa thành luôn, cho độ cao gần với độ cao giếng') == dict(mode='full')
    assert water_level('Raise the water level near the rim') == dict(mode='full')
    assert water_level('hạ nước xuống thấp hơn') == dict(mode='lower')
    assert water_level('water level 7 m') == dict(mode='level', level_m=7.0)
    assert not WATER_REQUEST.search('make the roof red') and not WATER_REQUEST.search('Uniformly scale to height 6 m')


def test_rim_phrasings_from_chat_and_vietnamese_reach_the_brim():
    for text in ('Make the water level rise close to the well mouth', 'làm nước cao gần tới miệng giếng', 'nước sát miệng giếng', 'fill the water up to the top'):
        assert WATER_REQUEST.search(text) and water_level(text) == dict(mode='full'), text
    assert water_level('let the water rise a bit') == dict(mode='higher')
