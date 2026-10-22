"""Actual GLB/PNG mutations; semantic losses and unsupported scopes stay distinct."""
import hashlib
import io
import json
import shutil
import struct

import numpy as np
import pytest
import trimesh
from PIL import Image

from apps.api.inspection import glb_layout
from apps.api.pbr_preservation import compare


@pytest.fixture
def pair(tmp_path):
    image = Image.new('RGBA', (16, 8), (30, 60, 90, 255))
    mesh = trimesh.creation.box()
    mesh.visual = trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices), 2)),
        material=trimesh.visual.material.PBRMaterial(baseColorTexture=image, metallicRoughnessTexture=image))
    source, target = tmp_path/'source.glb', tmp_path/'target.glb'
    source.write_bytes(mesh.export(file_type='glb'))
    shutil.copyfile(source, target)
    return source, target


def mutate(path, edit):
    doc, binary = glb_layout(path)
    with path.open('rb') as stream:
        stream.seek(binary[0]); data = stream.read(binary[1])
    replacement = edit(doc, data)
    if replacement is not None:
        data = replacement
    encoded = json.dumps(doc).encode(); encoded += b' '*(-len(encoded) % 4)
    data += b'\0'*(-len(data) % 4)
    chunks = struct.pack('<II', len(encoded), 0x4E4F534A)+encoded+struct.pack('<II', len(data), 0x004E4942)+data
    path.write_bytes(struct.pack('<4sII', b'glTF', 2, 12+len(chunks))+chunks)


def pixel_edit(doc, data, channel):
    pbr = doc['materials'][0]['pbrMetallicRoughness']
    key = 'baseColorTexture' if channel == 'base' else 'metallicRoughnessTexture'
    image = doc['images'][doc['textures'][pbr[key]['index']]['source']]
    view = doc['bufferViews'][image['bufferView']]; start = view.get('byteOffset', 0)
    with Image.open(io.BytesIO(data[start:start+view['byteLength']])) as original:
        actual = original.convert('RGBA')
    color = list(actual.getpixel((0, 0))); color[{'base': 0, 'R': 0, 'G': 1, 'B': 2}[channel]] += 1
    actual.putpixel((0, 0), tuple(color))
    out = io.BytesIO(); actual.save(out, format='PNG'); encoded = out.getvalue(); actual.close()
    image['bufferView'] = len(doc['bufferViews'])
    doc['bufferViews'].append(dict(buffer=0, byteOffset=len(data), byteLength=len(encoded)))
    doc['buffers'][0]['byteLength'] = len(data)+len(encoded)
    return data+encoded


def test_equal_core_data_is_measured_without_mutating_inputs(pair):
    source, target = pair
    original = [hashlib.sha256(p.read_bytes()).hexdigest() for p in pair]
    report = compare(source, target)
    assert report['status'] == 'Pass' and all(report['checks'].values())
    assert report['artistic_quality'] == report['sampler_fidelity'] == 'NotEvaluated'
    assert report['source']['maps']['metallic_roughness']['channel_sha256'].keys() == {'G', 'B'}
    assert original == [hashlib.sha256(p.read_bytes()).hexdigest() for p in pair]


@pytest.mark.parametrize('fault', ['base', 'G', 'B', 'missing_map', 'missing_material', 'factor', 'alpha', 'sided'])
def test_unrequested_semantic_loss_fails(pair, fault):
    source, target = pair
    def edit(doc, data):
        mat = doc['materials'][0]; pbr = mat['pbrMetallicRoughness']
        if fault in ('base', 'G', 'B'):return pixel_edit(doc, data, fault)
        if fault == 'missing_map':pbr.pop('baseColorTexture')
        if fault == 'missing_material':doc['materials'] = []
        if fault == 'factor':pbr['roughnessFactor'] = .2
        if fault == 'alpha':mat['alphaMode'] = 'BLEND'
        if fault == 'sided':mat['doubleSided'] = not mat.get('doubleSided', False)
    mutate(target, edit)
    assert compare(source, target)['status'] == 'Fail'


def test_unused_mr_red_and_explicit_sampler_are_observations_not_false_loss(pair):
    source, target = pair
    def edit(doc, data):
        doc['samplers'] = [dict(magFilter=9729, minFilter=9987)]
        for tex in doc['textures']:tex['sampler'] = 0
        return pixel_edit(doc, data, 'R')
    mutate(target, edit)
    report = compare(source, target)
    assert report['status'] == 'Pass'
    assert report['sampler_observation']['declarations_equal'] is False
    assert report['sampler_fidelity'] == 'NotEvaluated'


@pytest.mark.parametrize('value', [True, float('nan'), 2., '1', None])
def test_malformed_factors_fail_closed(pair, value):
    source, target = pair
    mutate(target, lambda doc, data: doc['materials'][0]['pbrMetallicRoughness'].update(metallicFactor=value))
    assert compare(source, target)['status'] == 'Fail'


def test_float32_export_rounding_is_not_a_material_change(pair):
    source, target = pair
    mutate(source, lambda doc, data: doc['materials'][0]['pbrMetallicRoughness'].update(roughnessFactor=.1))
    mutate(target, lambda doc, data: doc['materials'][0]['pbrMetallicRoughness'].update(roughnessFactor=.10000000149))
    assert compare(source, target)['status'] == 'Pass'


def test_unused_opaque_cutoff_is_ignored_but_mask_threshold_loss_fails(pair):
    source, target = pair
    mutate(source, lambda doc, data: doc['materials'][0].update(alphaCutoff=.2))
    assert compare(source, target)['status'] == 'Pass'
    for path in pair:
        mutate(path, lambda doc, data: doc['materials'][0].update(alphaMode='MASK'))
    assert compare(source, target)['status'] == 'Fail'


def test_extensions_and_intentional_revision_never_receive_preservation_pass(pair):
    source, target = pair
    assert compare(source, target, intentional_material_edit=True)['status'] == 'NotEvaluated'
    mutate(source, lambda doc, data: doc.update(extensionsUsed=['KHR_materials_unlit']))
    report = compare(source, target)
    assert report['status'] == 'NotEvaluated' and not report['checks']


def test_vertex_colors_are_not_certified_by_equal_texture_pixels(pair):
    source, target = pair
    def add_color(doc, data):
        primitive = doc['meshes'][0]['primitives'][0]
        count = doc['accessors'][primitive['attributes']['POSITION']]['count']
        colors = np.ones((count, 4), dtype='<f4').tobytes()
        view_id = len(doc['bufferViews']); accessor_id = len(doc['accessors'])
        doc['bufferViews'].append(dict(buffer=0, byteOffset=len(data), byteLength=len(colors)))
        doc['accessors'].append(dict(bufferView=view_id, componentType=5126, count=count, type='VEC4'))
        primitive['attributes']['COLOR_0'] = accessor_id
        doc['buffers'][0]['byteLength'] = len(data)+len(colors)
        return data+colors
    mutate(source, add_color)
    report = compare(source, target)
    assert report['status'] == 'NotEvaluated' and 'Vertex colors' in report['reason']


def test_high_precision_pixels_are_not_certified_by_quantized_rgba8(pair):
    source, target = pair
    def add_precision(doc, data):
        image = Image.fromarray(np.full((8, 16), 500, dtype=np.uint16))
        stream = io.BytesIO();image.save(stream, format='PNG');encoded = stream.getvalue();image.close()
        binding = doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture']
        image_doc = doc['images'][doc['textures'][binding['index']]['source']]
        image_doc['bufferView'] = len(doc['bufferViews'])
        doc['bufferViews'].append(dict(buffer=0, byteOffset=len(data), byteLength=len(encoded)))
        doc['buffers'][0]['byteLength'] = len(data)+len(encoded)
        return data+encoded
    for path in pair:mutate(path, add_precision)
    report = compare(source, target)
    assert report['status'] == 'NotEvaluated' and 'precision' in report['reason']


def test_real_blender_output_with_injected_material_loss_is_not_registered(pair, monkeypatch, qa_project):
    """Declared negative fault: corrupt the actual export after Blender exits.

    No process, successful QA or exported game asset is fabricated. This proves
    the worker uses the measured failure before candidate registration.
    """
    from apps.api import jobs, store
    from apps.api.local_tools import executable
    if not executable('blender'):
        pytest.skip('Real Blender unavailable; cannot verify worker fault boundary')
    source, _ = pair
    monkeypatch.setattr(store, 'DATA', source.parent)
    qa_project()
    original = store.add_artifact(source, 'candidate', 'Technical PBR fault fixture', dict(project_id='runavelle'))
    job = jobs.enqueue(dict(kind='blender', artifact_id=original['id'], render=False, export_fbx=False))
    unrelated = jobs.enqueue(dict(kind='blender', artifact_id=original['id'], render=False, export_fbx=False))
    real_popen = jobs.subprocess.Popen
    fault = dict(injected=False)

    class FaultAfterRealExit:
        def __init__(self, process):self.process = process
        def __getattr__(self, key):return getattr(self.process, key)
        def poll(self):
            code = self.process.poll()
            if code == 0 and not fault['injected']:
                output = store.DATA/'jobs'/job['id']/'output/LOD0.glb'
                def remove_binding(doc, data):
                    del doc['materials'][0]['pbrMetallicRoughness']['metallicRoughnessTexture']
                mutate(output, remove_binding)
                fault['injected'] = True
            return code

    def launch(command, *args, **kwargs):
        process = real_popen(command, *args, **kwargs)
        return FaultAfterRealExit(process) if any('process_asset.py' in str(part) for part in command) else process

    monkeypatch.setattr(jobs.subprocess, 'Popen', launch)
    with jobs.resource_slot('cpu'):
        jobs.Worker().execute(job)
    assert fault['injected']
    result = jobs.get(job['id'])
    assert result['status'] == 'FAILED' and 'metallic_roughness_gb' in result['error']
    folder = store.DATA/'jobs'/job['id']/'output'
    report = json.loads((folder/'pbr_preservation.json').read_text())
    assert report['status'] == 'Fail' and not report['checks']['metallic_roughness_gb']
    assert not (folder/'pbr_preservation.json.part').exists()
    assert (folder/'LOD0.glb').is_file() and store.digest(source) == original['sha256']
    with store.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] == 1
    assert jobs.get(unrelated['id'])['status'] == 'QUEUED'
