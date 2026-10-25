"""Unified adapter contract for opt-in CLI research; never production promotion."""
from pathlib import Path
from .adapters import LocalAdapter
from apps.api import store


class SparseResearchAdapter(LocalAdapter):
    def paths(self):
        name = 'TRELLIS-v1' if self.id == 'trellis_v1' else 'Hi3DGen'
        return store.WORKSPACE / '.local/engines' / name, store.WORKSPACE / '.local/envs' / self.id / 'Scripts/python.exe'

    def weights(self):
        if self.id == 'trellis_v1':
            return Path.home() / 'Tools/trellis2/code/MODELS/hub/models--microsoft--TRELLIS-image-large/snapshots/25e0d31ffbebe4b5a97464dd851910efc3002d96'
        return store.WORKSPACE / 'models/hi3dgen'

    def probe(self):
        source, python = self.paths()
        required = [self.weights() / 'pipeline.json', store.WORKSPACE / 'models/dinov2/dinov2_vitl14_reg4_pretrain.pth']
        if self.id == 'hi3dgen': required.append(store.WORKSPACE / 'models/hi3dgen_normal/model_index.json')
        return dict(id=self.id, installed=source.is_dir() and python.is_file() and all(p.is_file() for p in required),
                    source=str(source), python=str(python), weights=str(self.weights()), status='RESEARCH_ONLY',
                    license=self.license, capabilities=self.capabilities, input_modalities=self.input_modalities,
                    output_formats=self.output_formats, min_vram_gb=self.min_vram_gb,
                    note='Presence check only; inspect immutable generation evidence for runtime validation')

    def generate(self, job, progress):
        if not self.installed: raise ValueError('Research environment or offline weights missing')
        source, python = self.paths()
        req = dict(job, engine=self.id, engine_path=str(source), weights=str(self.weights()),
                   experimental=True, commercial_approval='NEEDS_REVIEW')
        progress(dict(event='research_prepared', engine=self.id, official_integration=False))
        return [str(python), '-B', '-u', str(store.ROOT / 'engines/sparse_research_worker.py'), '--request', job['request_path']], store.ROOT, req


RESEARCH_ADAPTERS = {
    'trellis_v1': SparseResearchAdapter('trellis_v1', '442aa1e1afb9014e80681d3bf604e8d728a86ee7',
                                     'MIT core; Apache-2.0 DINO/FlexiCubes; input/dependencies NEEDS_REVIEW', ('image_to_shape', 'seed', 'stage_cpu_offload'), 8),
    'hi3dgen': SparseResearchAdapter('hi3dgen', '2b12d057e82bdeb751edfe7fab82632f7df2c7ba+original-normal-route',
                                   'MIT core; Apache-2.0 StableNormal/YOSO; input/dependencies NEEDS_REVIEW', ('normal_guided_shape', 'seed', 'stage_cpu_offload'), 8),
}
