"""Offline, capability-aware adapters. Unavailable engines cannot silently fall back to paid services."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from apps.api import store
from apps.api.inspection import inspect_glb


class EngineAdapter(Protocol):
    id: str
    version: str
    license: str
    capabilities: tuple[str, ...]
    input_modalities: tuple[str, ...]
    output_formats: tuple[str, ...]
    min_vram_gb: float
    installed: bool
    def probe(self) -> dict: ...
    def estimate(self, job: dict) -> dict: ...
    def generate(self, job: dict, progress: Callable) -> tuple[list[str], Path, dict]: ...
    def cancel(self, job: dict) -> dict: ...
    def verify_outputs(self, output: Path) -> dict: ...


@dataclass
class LocalAdapter:
    id: str
    version: str
    license: str
    capabilities: tuple[str, ...]
    min_vram_gb: float
    input_modalities: tuple[str, ...] = ('single_image',)
    output_formats: tuple[str, ...] = ('glb',)

    def paths(self):
        if self.id == 'trellis2_community':
            source = Path.home() / 'Tools/trellis2/code'
            return source, source / 'venv/Scripts/python.exe'
        return store.WORKSPACE / '.local/engines/TripoSG', store.WORKSPACE / '.local/envs/triposg/Scripts/python.exe'

    def probe(self):
        source, python = self.paths()
        weights = (source / 'MODELS/hub/models--microsoft--TRELLIS.2-4B/refs/main') if self.id == 'trellis2_community' else (store.WORKSPACE / 'models/triposg/transformer/diffusion_pytorch_model.safetensors')
        return {'id': self.id, 'version': self.version, 'installed': source.is_dir() and python.is_file() and weights.is_file(),
                'source': str(source), 'python': str(python), 'inference': 'see immutable run evidence',
                'capabilities': self.capabilities, 'input_modalities': self.input_modalities, 'output_formats': self.output_formats,
                'min_vram_gb': self.min_vram_gb, 'license': self.license}

    @property
    def installed(self):
        return self.probe()['installed']

    def estimate(self, job):
        return {'required_free_vram_gb': self.min_vram_gb, 'duration_seconds': None,
                'note': 'memory guard, not a guarantee; exact runtime/storage measured per output'}

    def generate(self, job, progress):
        if not self.probe()['installed']: raise ValueError('Engine environment or offline weights missing')
        source, python = self.paths()
        request = dict(job)
        request['engine_path'] = str(source)
        if self.id == 'trellis2_community':
            request.update({'purpose': 'evaluation_only', 'allow_existing_rmbg_evaluation': not job.get('supplied_alpha_input'),
                            'min_free_vram_gb': self.min_vram_gb})
            command = [str(python), '-B', '-u', str(store.ROOT / 'engines/trellis2_worker.py'), '--request', job['request_path'], '--allow-community-evaluation']
            cwd = source
        else:
            request.update({'weights': str(store.WORKSPACE / 'models/triposg'), 'dense_depth': 7, 'octree_depth': 9, 'decode_chunk_size': 10000,
                            'min_free_vram_gb': self.min_vram_gb})
            command = [str(python), '-B', '-u', str(store.ROOT / 'engines/triposg_worker.py'), '--request', job['request_path']]
            cwd = store.ROOT
        progress({'event': 'prepared', 'engine': self.id, 'estimate': self.estimate(request)})
        return command, cwd, request

    def cancel(self, job):
        from apps.api.jobs import kill_tree
        process = job.get('process')
        if process is None: raise ValueError('Cancel requires the owned worker subprocess handle')
        if process.poll() is None: kill_tree(process)
        return {'status': 'TERMINATED', 'checkpoint_resume': False, 'retry': 'new immutable attempt'}

    def verify_outputs(self, output):
        return inspect_glb(output / 'raw.glb')


HOME = Path.home()
# Engines that build a shape from an alpha image and are textured by MV-Adapter in the same job.
SHAPE_ENGINES = ('triposg', 'trellis_v1', 'hunyuan3d21')
MVADAPTER = dict(engine=store.WORKSPACE / '.local/engines/MV-Adapter', python=store.WORKSPACE / '.local/envs/mvadapter/Scripts/python.exe')
# Shape stage per engine: environment, worker, extra request fields and the files that prove the weights are present.
SHAPES = {
    'triposg': dict(python=store.WORKSPACE / '.local/envs/triposg/Scripts/python.exe', worker='engines/triposg_worker.py', source=store.WORKSPACE / '.local/engines/TripoSG',
                    extra=dict(weights=str(store.WORKSPACE / 'models/triposg'), dense_depth=7, octree_depth=9, decode_chunk_size=10000, min_free_vram_gb=8),
                    required=[store.WORKSPACE / 'models/triposg/transformer/diffusion_pytorch_model.safetensors'], checkpoints=[store.WORKSPACE / 'models/triposg']),
    'trellis_v1': dict(python=store.WORKSPACE / '.local/envs/trellis_v1/Scripts/python.exe', worker='engines/sparse_research_worker.py', source=store.WORKSPACE / '.local/engines/TRELLIS-v1',
                       extra=dict(engine='trellis_v1', weights=str(HOME / 'Tools/trellis2/code/MODELS/hub/models--microsoft--TRELLIS-image-large/snapshots/25e0d31ffbebe4b5a97464dd851910efc3002d96')),
                       required=[HOME / 'Tools/trellis2/code/MODELS/hub/models--microsoft--TRELLIS-image-large/snapshots/25e0d31ffbebe4b5a97464dd851910efc3002d96/pipeline.json'],
                       checkpoints=[HOME / 'Tools/trellis2/code/MODELS/hub/models--microsoft--TRELLIS-image-large']),
    'hunyuan3d21': dict(python=store.WORKSPACE / '.local/envs/hunyuan3d21/Scripts/python.exe', worker='engines/hunyuan_worker.py', source=HOME / 'Tools/hunyuan3d21/code',
                        extra=dict(engine_path=str(HOME / 'Tools/hunyuan3d21/code'), models=str(HOME / 'Tools/hunyuan3d21/models'), hf_home=str(HOME / 'Tools/hunyuan3d21/hf_home'), steps=50, octree_resolution=384),
                        required=[HOME / 'Tools/hunyuan3d21/models/tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1/config.yaml'], checkpoints=[HOME / 'Tools/hunyuan3d21/models/tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1']),
}


# Experimental second texturer: TRELLIS.2 texturing (upstream source; the bundle's venv, MODELS and offline checkpoints).
TRELLIS2_TEXTURE = dict(python=str(HOME / 'Tools/trellis2/code/venv/Scripts/python.exe'), upstream_path=str(HOME / 'Tools/trellis2-upstream'),
                        models_path=str(HOME / 'Tools/trellis2/code/MODELS'), flexgemm_path=str(HOME / 'Tools/flexgemm-src'))


def trellis2_texture_ready():
    models = Path(TRELLIS2_TEXTURE['models_path'])
    return (Path(TRELLIS2_TEXTURE['python']).is_file() and (Path(TRELLIS2_TEXTURE['flexgemm_path']) / 'flex_gemm/kernels/triton/__init__.py').is_file() and (Path(TRELLIS2_TEXTURE['upstream_path']) / 'trellis2/pipelines/trellis2_texturing.py').is_file()
            and any((models / 'hub/models--microsoft--TRELLIS.2-4B/snapshots').glob('*/texturing_pipeline.json'))
            and (models / 'dinov3/model.safetensors').is_file() and (models / 'RMBG-2.0/model.safetensors').is_file())


def texture_ready():
    weights = list((HOME / '.cache/huggingface/hub/models--huanngzh--mv-adapter/snapshots').glob('*/mvadapter_ig2mv_sdxl.safetensors'))
    return MVADAPTER['python'].is_file() and all((MVADAPTER['engine'] / 'checkpoints' / name).is_file() for name in ('RealESRGAN_x2plus.pth', 'big-lama.pt')) and bool(weights)


@dataclass
class TexturedShapeAdapter(LocalAdapter):
    """A shape engine followed by MV-Adapter texturing in the same GPU job (engines/textured_shape_worker.py)."""

    def paths(self):
        shape = SHAPES[self.id]
        return shape['source'], shape['python']

    def checkpoint_roots(self):
        return [*SHAPES[self.id]['checkpoints'], MVADAPTER['engine'] / 'checkpoints']

    def probe(self):
        shape = SHAPES[self.id]; source, python = self.paths()
        ready = python.is_file() and source.is_dir() and all(p.is_file() for p in shape['required'])
        return {'id': self.id, 'version': self.version, 'installed': ready and texture_ready(), 'shape_installed': ready, 'texture_installed': texture_ready(),
                'source': str(source), 'python': str(python), 'inference': 'see immutable run evidence', 'capabilities': self.capabilities,
                'input_modalities': self.input_modalities, 'output_formats': self.output_formats, 'min_vram_gb': self.min_vram_gb, 'license': self.license}

    def generate(self, job, progress):
        if not self.probe()['installed']: raise ValueError('Shape environment, texture environment or offline weights missing')
        shape = SHAPES[self.id]
        request = dict(job, engine=self.id, shape_request=dict(shape['extra'], engine_path=shape['extra'].get('engine_path', str(shape['source']))),
                       shape_command=[str(shape['python']), '-B', '-u', str(store.ROOT / shape['worker'])], shape_cwd=str(store.ROOT),
                       texture_engine_path=str(MVADAPTER['engine']), texture_python=str(MVADAPTER['python']), texture_worker=str(store.ROOT / 'engines/mvadapter_texture_worker.py'),
                       uv_size=int(job.get('texture_size') or 4096), u2net_home=str(HOME / 'Tools/hunyuan3d21/u2net'))
        if job.get('texturer') == 'trellis2':
            if not trellis2_texture_ready(): raise ValueError('TRELLIS.2 texturing source, environment or offline weights missing')
            request.update(texturer='trellis2', trellis2_texture=dict(TRELLIS2_TEXTURE, worker=str(store.ROOT / 'engines/trellis2_texture_worker.py')))
        command = [str(MVADAPTER['python']), '-B', '-u', str(store.ROOT / 'engines/textured_shape_worker.py'), '--request', job['request_path']]
        progress({'event': 'prepared', 'engine': self.id, 'estimate': self.estimate(request)})
        return command, store.ROOT, request


# Measured on this RTX 5070 Ti (16 GB VRAM, 64 GB RAM) with the house concept, 2026-10-24 (data/engine-compare/house-t2).
REQUIREMENTS = {
    'trellis2_community': dict(peak_vram_gb=16, free_ram_gb=25, seconds=290),  # 22.8 GiB resident peak measured 2026-10-25
    'triposg': dict(peak_vram_gb=14.3, shape_seconds=67, texture_seconds=225),
    'trellis_v1': dict(peak_vram_gb=14.3, shape_seconds=43, texture_seconds=159),
    'hunyuan3d21': dict(peak_vram_gb=14.3, shape_seconds=145, texture_seconds=154),
}

ADAPTERS: dict[str, EngineAdapter] = {
    'trellis2_community': LocalAdapter('trellis2_community', 'local Windows StableProjectorz bundle, source hashes per run', 'EVALUATION_ONLY_PENDING_AUDIT', ('image_to_mesh', 'seed', 'pbr', 'stage_cpu_offload'), 10),
    'triposg': TexturedShapeAdapter('triposg', 'fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c+optional-diso; MV-Adapter 4277e00', 'MIT (TripoSG); Apache-2.0 (MV-Adapter); SDXL OpenRAIL++-M',
                                    ('image_to_mesh', 'seed', 'basecolor_texture'), 14),
    'trellis_v1': TexturedShapeAdapter('trellis_v1', '442aa1e1afb9014e80681d3bf604e8d728a86ee7; MV-Adapter 4277e00', 'MIT (TRELLIS); Apache-2.0 (MV-Adapter); SDXL OpenRAIL++-M',
                                       ('image_to_mesh', 'seed', 'basecolor_texture'), 14),
    'hunyuan3d21': TexturedShapeAdapter('hunyuan3d21', 'Hunyuan3D-2.1 shape DiT; MV-Adapter 4277e00', 'Tencent Hunyuan Community License (not EU/UK/KR); Apache-2.0 (MV-Adapter)',
                                        ('image_to_mesh', 'seed', 'basecolor_texture'), 14),
}
