"""Independent local text-to-concept adapter (FLUX.2 [klein] 4B); cached weights only."""
from pathlib import Path
from apps.api import store
from apps.api.inspection import inspect_image
from .adapters import LocalAdapter

WEIGHTS = Path.home() / 'Models/black-forest-labs__FLUX.2-klein-4B'


class KleinAdapter(LocalAdapter):
    def paths(self):
        # The existing diffusers environment (torch 2.11 + CUDA 12.8, diffusers with Flux2) runs the worker.
        source = Path.home() / 'Tools/sdxl'
        return source, source / 'venv/Scripts/python.exe'

    def weights(self):
        return WEIGHTS

    def probe(self):
        source, python = self.paths(); weights = self.weights()
        files = ['model_index.json', 'transformer', 'text_encoder', 'vae']
        return dict(id=self.id, installed=python.is_file() and all((weights / p).exists() for p in files) and any((weights / 'transformer').glob('*.safetensors')),
                    source=str(source), python=str(python), weights=str(weights), capabilities=self.capabilities,
                    input_modalities=self.input_modalities, output_formats=self.output_formats,
                    min_vram_gb=self.min_vram_gb, license=self.license)

    def generate(self, job, progress):
        if not self.installed: raise ValueError('Local concept environment or FLUX.2 klein weights missing; no auto-download')
        _, python = self.paths(); req = dict(job, weights=str(self.weights()))
        progress(dict(event='prepared', engine=self.id))
        return [str(python), '-B', '-u', str(store.ROOT / 'engines/klein_worker.py'), '--request', job['request_path']], store.ROOT, req

    def verify_outputs(self, output): return inspect_image(output / 'concept.png')


CONCEPT_ADAPTER = KleinAdapter('flux2_klein_local', 'FLUX.2 [klein] 4B (distilled, 4 steps)',
    'Apache-2.0 weights and diffusers code',
    ('text_to_concept', 'seed', 'stage_cpu_offload', 'reference_image'), 13, ('text', 'image'), ('png',))
