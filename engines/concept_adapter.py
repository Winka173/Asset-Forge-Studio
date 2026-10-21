"""Independent local text-to-concept adapter; cached weights only."""
from pathlib import Path
from apps.api import store
from apps.api.inspection import inspect_image
from .adapters import LocalAdapter


class SDXLAdapter(LocalAdapter):
    def paths(self):
        source = Path.home() / 'Tools/sdxl'
        return source, source / 'venv/Scripts/python.exe'

    def weights(self):
        return Path.home() / '.cache/huggingface/hub/models--stabilityai--stable-diffusion-xl-base-1.0/snapshots/462165984030d82259a11f4367a4eed129e94a7b'

    def probe(self):
        source, python = self.paths(); weights=self.weights()
        files=['model_index.json','unet/diffusion_pytorch_model.fp16.safetensors','vae/diffusion_pytorch_model.fp16.safetensors',
               'text_encoder/model.fp16.safetensors','text_encoder_2/model.fp16.safetensors']
        return dict(id=self.id, installed=python.is_file() and all((weights/p).is_file() for p in files),
                    source=str(source), python=str(python), weights=str(weights), capabilities=self.capabilities,
                    input_modalities=self.input_modalities, output_formats=self.output_formats,
                    min_vram_gb=self.min_vram_gb, license=self.license)

    def generate(self, job, progress):
        if not self.installed: raise ValueError('Local SDXL environment or cached weights missing; no auto-download')
        _, python = self.paths(); req=dict(job, weights=str(self.weights()))
        progress(dict(event='prepared',engine=self.id))
        return [str(python),'-B','-u',str(store.ROOT/'engines/sdxl_worker.py'),'--request',job['request_path']], store.ROOT, req

    def verify_outputs(self, output): return inspect_image(output/'concept.png')


CONCEPT_ADAPTER = SDXLAdapter('sdxl_local','SDXL base 1.0 / cached revision 46216598',
    'CreativeML Open RAIL++-M weights; Apache-2.0 diffusers; output restrictions apply',
    ('text_to_concept','seed','stage_cpu_offload','long_prompt_chunks'),6,('text',),('png',))
