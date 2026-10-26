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
        raise ValueError('Unknown engine ' + self.id)

    def probe(self):
        source, python = self.paths()
        weights = source / 'MODELS/hub/models--microsoft--TRELLIS.2-4B/refs/main'
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
# TRELLIS.2 is the only 3D engine (native PBR); shape-only engines and their texturers were removed on 2026-10-26.
SHAPE_ENGINES = ()


# Measured on this RTX 5070 Ti (16 GB VRAM, 64 GB RAM) with the house concept, 2026-10-24 (data/engine-compare/house-t2).
REQUIREMENTS = {
    'trellis2_community': dict(peak_vram_gb=16, free_ram_gb=25, seconds=290),  # 22.8 GiB resident peak measured 2026-10-25
}

ADAPTERS: dict[str, EngineAdapter] = {
    'trellis2_community': LocalAdapter('trellis2_community', 'local Windows StableProjectorz bundle, source hashes per run', 'EVALUATION_ONLY_PENDING_AUDIT', ('image_to_mesh', 'seed', 'pbr', 'stage_cpu_offload'), 10),
}
