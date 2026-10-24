

def test_an_unrelated_reference_never_becomes_the_shape_source():
    from engines.intent_adapter import aggregate_role
    # 'cho tôi 1 armory' with a watchtower image: the model says the image is unrelated.
    assert aggregate_role(True, 'auto', {'none'}) == 'style'
    assert aggregate_role(True, 'auto', {'source'}) == 'source' and aggregate_role(True, 'auto', {'style', 'none'}) == 'style'
    assert aggregate_role(True, 'source', {'none'}) == 'source' and aggregate_role(False, 'auto', {'source'}) == 'none'
