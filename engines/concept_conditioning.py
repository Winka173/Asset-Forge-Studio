"""Versioned SDXL conditioning identity and measured token-window diagnostics.

No Torch/model import here: the API can validate admission without loading AI.
The legacy mathematical policy is frozen, including empty negative windows.
"""
import hashlib
import importlib.metadata
import math
import sys
from pathlib import Path

POLICY = dict(id='sdxl_clip_windows_mean_v1', content_tokens=75, sequence_tokens=77,
    max_windows=64, hidden_states='penultimate', pooled='mean_all_clip2_windows',
    padding='bos_content_eos_pad', negative_padding='empty_windows',
    scheduler='DPMSolverMultistepScheduler/dpmsolver++/karras')
PACKAGES = ('torch', 'diffusers', 'transformers', 'accelerate', 'tokenizers', 'safetensors', 'numpy', 'pillow')
DEFAULT_NEGATIVE = 'text, watermark, logo, collage, multiple objects, cropped, cut off, blurry, low quality, floating parts, broken perspective'


class ConditioningError(ValueError):
    """The saved quality contract cannot be executed unchanged."""


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def runtime_versions(environment=None):
    if environment is None:
        return dict(python=sys.version.split()[0], **{name: importlib.metadata.version(name) for name in PACKAGES})
    environment = Path(environment)
    cfg = dict(line.split(' = ', 1) for line in (environment/'pyvenv.cfg').read_text().splitlines() if ' = ' in line)
    installed = {d.metadata['Name'].lower().replace('_', '-'): d.version
        for d in importlib.metadata.distributions(path=[str(environment/'Lib/site-packages')])}
    try:return dict(python=cfg['version'], **{name: installed[name] for name in PACKAGES})
    except KeyError as exc:raise ValueError('SDXL runtime metadata missing; repair the separate environment') from exc


def identity(weights, environment, source, runtime=None):
    weights, source = Path(weights), Path(source)
    required = [f'{name}/{file}' for name in ('tokenizer', 'tokenizer_2')
        for file in ('vocab.json', 'merges.txt', 'tokenizer_config.json', 'special_tokens_map.json')]
    required += ['model_index.json', 'scheduler/scheduler_config.json']
    required += [f'{name}/config.json' for name in ('text_encoder', 'text_encoder_2', 'unet', 'vae')]
    if any(not (weights/file).is_file() for file in required):
        raise ValueError('SDXL tokenizer/model configuration missing; no silent tokenizer fallback')
    configs = sorted(p for p in weights.rglob('*') if p.is_file() and p.suffix in ('.json', '.txt'))
    return dict(schema_version=1, policy=dict(POLICY),
        code_sha256={name: digest(source/name) for name in ('sdxl_worker.py', 'concept_conditioning.py')},
        model_config_sha256={p.relative_to(weights).as_posix(): digest(p) for p in configs},
        runtime_versions=runtime if runtime is not None else runtime_versions(environment))


def verify_request(request, weights, environment, source, runtime=None):
    effective = request.get('effective_config') or {}
    locked = effective.get('conditioning')
    if locked is None:
        return dict(status='legacy_default_unpinned', policy_id=POLICY['id'],
            reason='Legacy job retains the original algorithm; runtime/tokenizer identity was not pinned at admission.')
    if not isinstance(locked, dict) or locked.get('schema_version') != 1 or locked.get('policy') != POLICY:
        raise ConditioningError('Concept conditioning policy is unsupported or changed; resolve a new configuration')
    try:actual = identity(weights, environment, source, runtime)
    except (OSError, ValueError) as exc:raise ConditioningError('Concept conditioning files/runtime unavailable: '+str(exc)) from exc
    if locked != actual:
        changed = sorted(key for key in set(actual) | set(locked) if actual.get(key) != locked.get(key))
        raise ConditioningError('Concept conditioning identity changed: ' + ', '.join(changed) + '; saved quality settings retained')
    values = dict(input_prompt=request['prompt'], negative_prompt=request.get('negative_prompt', DEFAULT_NEGATIVE),
        inference_steps=request['steps'], resolution=request.get('size', 1024), seed=request['seed'],
        guidance=request.get('guidance_scale', 7))
    if any(effective.get(key) != value for key, value in values.items()):
        raise ConditioningError('Concept execution differs from the locked prompt/seed/steps/size/guidance')
    anchor = request.get('style_anchor') or {}
    locked_anchor = effective.get('style_anchor') or {}
    if {k: anchor.get(k) for k in ('sha256', 'scale', 'weight_name')} != {k: locked_anchor.get(k) for k in ('sha256', 'scale', 'weight_name')}:
        raise ConditioningError('Concept style anchor differs from the locked configuration')
    return dict(status='verified', policy_id=POLICY['id'], identity=actual)


def verify_weights(request, actual):
    # The worker already hashes real weights. Bind that measured inventory to the
    # admitted config too; version/config checks are not a weight integrity proof.
    effective = request.get('effective_config') or {}
    if effective.get('conditioning') is None:return
    expected = (effective.get('checkpoint') or {}).get('files')
    measured = {str(Path(request['weights'])/name): value for name, value in actual.items()}
    if not expected or expected != measured:
        raise ConditioningError('Concept checkpoint weights changed after admission; no generation started')


def token_plan(token_ids, prompt, negative):
    """token_ids[positive|negative][clip_l|clip_g] comes from actual tokenizers."""
    chunks = max(1, *(math.ceil(len(tokens)/75) for encoders in token_ids.values() for tokens in encoders.values()))
    if chunks > 64:
        raise ValueError('Concept conditioning exceeds 4800 CLIP tokens; source remains saved, no silent truncation')
    measured = {}
    for direction, encoders in token_ids.items():
        measured[direction] = {}
        for name, tokens in encoders.items():
            counts = [len(tokens[i*75:(i+1)*75]) for i in range(chunks)]
            measured[direction][name] = dict(content_tokens=len(tokens), content_tokens_by_window=counts,
                empty_windows=sum(n == 0 for n in counts), token_ranges=[[i*75, i*75+n] if n else None for i, n in enumerate(counts)])
    return dict(schema_version=2, policy_id=POLICY['id'], chunks=chunks, tokens_not_truncated=True,
        pooled='mean across CLIP-2 chunks', experimental_long_prompt=chunks > 1, measured=measured,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), negative_prompt_sha256=hashlib.sha256(negative.encode()).hexdigest(),
        character_spans='not_available; ranges are tokenizer content-token offsets, not source character/provenance spans',
        limitation='Retaining tokens and measuring empty windows does not prove prompt/style/artistic fidelity.')


def window_ids(tokens, index, bos, eos, pad):
    ids = [bos] + tokens[index*75:(index+1)*75] + [eos]
    return ids + [pad]*(77-len(ids))
