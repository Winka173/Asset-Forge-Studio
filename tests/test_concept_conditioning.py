"""No simulated inference: token packing and real installed-file admission guards."""
import copy
import hashlib
from pathlib import Path

import pytest

from apps.api import jobs, store
from engines.concept_adapter import CONCEPT_ADAPTER
from engines.concept_conditioning import POLICY, identity, token_plan, verify_request, verify_weights, window_ids
from engines.quality import fingerprint


@pytest.fixture
def locked_request():
    if not CONCEPT_ADAPTER.installed:pytest.skip('Requires the actual separate installed SDXL environment')
    source, _ = CONCEPT_ADAPTER.paths()
    config = dict(conditioning=identity(CONCEPT_ADAPTER.weights(), source/'venv', store.ROOT/'engines'),
        input_prompt='One complete castle, ivory walls and midnight blue roofs.', negative_prompt='contact sheet, cropped',
        inference_steps=50, resolution=1024, seed=43, guidance=7, composition_policy=3)
    return dict(kind='concept', prompt=config['input_prompt'], negative_prompt=config['negative_prompt'],
        steps=50, size=1024, seed=43, effective_config=config, effective_config_hash=fingerprint(config))


def verify(req):
    source, _ = CONCEPT_ADAPTER.paths()
    return verify_request(req, CONCEPT_ADAPTER.weights(), source/'venv', store.ROOT/'engines')


def test_actual_environment_and_small_configuration_files_are_pinned(locked_request):
    report = verify(locked_request)
    assert report['status'] == 'verified' and report['policy_id'] == POLICY['id']
    value = report['identity']
    assert value['runtime_versions']['torch'] and value['runtime_versions']['diffusers']
    assert {'tokenizer/vocab.json', 'tokenizer_2/merges.txt', 'unet/config.json'} <= value['model_config_sha256'].keys()
    assert value['code_sha256']['sdxl_worker.py'] == hashlib.sha256((store.ROOT/'engines/sdxl_worker.py').read_bytes()).hexdigest()


@pytest.mark.parametrize('fault', ['worker', 'tokenizer', 'runtime', 'policy', 'guidance', 'prompt', 'negative', 'steps', 'seed', 'size'])
def test_real_worker_blocks_stale_or_changed_contract_without_creating_process(tmp_path, monkeypatch, locked_request, fault):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    request = copy.deepcopy(locked_request)
    locked = request['effective_config']['conditioning']
    if fault == 'worker':locked['code_sha256']['sdxl_worker.py'] = '0'*64
    elif fault == 'tokenizer':locked['model_config_sha256']['tokenizer/vocab.json'] = '0'*64
    elif fault == 'runtime':locked['runtime_versions']['torch'] = 'stale-version'
    elif fault == 'policy':locked['policy']['id'] = 'unimplemented-policy'
    elif fault == 'guidance':request['guidance_scale'] = 1
    elif fault in ('prompt', 'negative'):request['prompt' if fault == 'prompt' else 'negative_prompt'] += ' changed'
    elif fault in ('steps', 'seed', 'size'):request[fault] += 1
    request['effective_config_hash'] = fingerprint(request['effective_config'])
    job = jobs.enqueue(request)
    jobs.Worker().execute(job)
    result = jobs.get(job['id'])
    assert result['status'] == 'BLOCKED' and result['error']
    assert result['payload']['effective_config'] == request['effective_config']
    folder = tmp_path/'jobs'/job['id']
    assert not (folder/'process.json').exists() and not (folder/'output').exists()


def test_legacy_request_remains_explicitly_unpinned_without_claiming_new_identity():
    report = verify_request({}, Path('unused'), Path('unused'), Path('unused'))
    assert report['status'] == 'legacy_default_unpinned' and report['policy_id'] == POLICY['id']


@pytest.mark.parametrize('count', [0, 1, 74, 75, 76, 410, 4800])
def test_packing_retains_every_token_and_original_bos_eos_padding(count):
    tokens = list(range(count))
    values = {direction: {'clip_l': tokens if direction == 'positive' else [], 'clip_g': tokens if direction == 'positive' else []} for direction in ('positive', 'negative')}
    report = token_plan(values, 'source', 'negative')
    recovered = []
    for i, n in enumerate(report['measured']['positive']['clip_l']['content_tokens_by_window']):
        ids = window_ids(tokens, i, -1, -2, -3)
        assert len(ids) == 77 and ids[0] == -1 and ids[n+1] == -2
        recovered.extend(ids[1:n+1])
        assert ids[n+2:] == [-3]*(75-n)
    assert recovered == tokens
    assert report['measured']['negative']['clip_g']['empty_windows'] == report['chunks']


def test_excess_tokens_are_rejected_instead_of_truncated():
    with pytest.raises(ValueError, match='4800'):
        token_plan({'positive': {'clip_l': list(range(4801))}, 'negative': {'clip_l': []}}, 'source', '')


def test_measured_inventory_must_match_the_admitted_weight_hashes():
    # Inventory math only. This does not fabricate files or successful weights.
    req = dict(weights=str(Path('weights')), effective_config=dict(conditioning={}, checkpoint=dict(files={str(Path('weights/unet.safetensors')): 'expected'})))
    verify_weights(req, {'unet.safetensors': 'expected'})
    with pytest.raises(ValueError, match='weights changed'):verify_weights(req, {'unet.safetensors': 'changed'})
    with pytest.raises(ValueError, match='weights changed'):verify_weights(req, {})
