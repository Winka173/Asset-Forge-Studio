"""Read-only core PBR roundtrip checks. This does not certify rendered appearance.

Only static single-material core glTF is scoped. Unsupported shaders and explicit
material revisions are NotEvaluated, never a fabricated preservation pass.
"""
import hashlib
import io
import math
from pathlib import Path

from PIL import Image

from .inspection import glb_layout
from .texture_diagnostics import image_bytes, index, measure

FACTOR_TOLERANCE = 1e-6


class Unsupported(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def factor(value, length=None):
    values = value if length is not None else [value]
    if not isinstance(values, list) or (length is not None and len(values) != length):
        raise ValueError('Invalid core PBR factor shape')
    if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError('Core PBR factors must be finite numbers between zero and one')
    return values if length is not None else value


def snapshot(path):
    doc, binary = glb_layout(path)
    for key in ('meshes', 'materials', 'nodes', 'textures', 'images', 'samplers'):
        if not isinstance(doc.get(key, []), list):
            raise ValueError(f'Invalid glTF {key} array')
    if doc.get('animations') or doc.get('skins') or doc.get('extensionsUsed'):
        raise Unsupported('Animations, skins or extension shaders are outside core roundtrip scope')
    meshes = doc.get('meshes', [])
    if len(meshes) != 1 or len(meshes[0].get('primitives', [])) != 1:
        raise Unsupported('Requires one mesh and one primitive')
    primitive = meshes[0]['primitives'][0]
    if any(k.startswith('COLOR_') for k in primitive.get('attributes', {})):
        raise Unsupported('Vertex colors require separate correspondence checks; maps/factors alone are insufficient')
    if meshes[0].get('extensions') or primitive.get('extensions') or any(node.get('extensions') for node in doc.get('nodes', [])):
        raise Unsupported('Mesh/primitive/node extensions are outside core roundtrip scope')
    if len(doc.get('materials', [])) != 1 or type(primitive.get('material')) is not int or primitive['material'] != 0:
        raise Unsupported('Requires one explicitly bound core material')
    if primitive.get('mode', 4) != 4 or primitive.get('targets') or any(k.startswith(('JOINTS', 'WEIGHTS')) for k in primitive.get('attributes', {})):
        raise Unsupported('Only static triangle primitives are scoped')
    if sum('mesh' in node for node in doc.get('nodes', [])) != 1:
        raise Unsupported('Requires one static mesh instance')
    material = doc['materials'][0]
    pbr = material.get('pbrMetallicRoughness', {})
    if not isinstance(pbr, dict):
        raise ValueError('Invalid core PBR object')
    if material.get('extensions') or pbr.get('extensions') or any(material.get(k) is not None for k in ('normalTexture', 'occlusionTexture', 'emissiveTexture')):
        raise Unsupported('Additional shader channels/extensions are outside initial scope')
    alpha = material.get('alphaMode', 'OPAQUE')
    cutoff = material.get('alphaCutoff', .5)
    sided = material.get('doubleSided', False)
    if alpha not in ('OPAQUE', 'MASK', 'BLEND') or type(sided) is not bool:
        raise ValueError('Invalid core alpha mode/doubleSided')
    if type(cutoff) not in (int, float) or not math.isfinite(cutoff) or cutoff < 0:
        raise ValueError('Invalid finite alpha cutoff')
    factors = dict(base_color=factor(pbr.get('baseColorFactor', [1., 1., 1., 1.]), 4),
        metallic=factor(pbr.get('metallicFactor', 1.)), roughness=factor(pbr.get('roughnessFactor', 1.)),
        emissive=factor(material.get('emissiveFactor', [0., 0., 0.]), 3), alpha_cutoff=cutoff if alpha == 'MASK' else 0.)
    # Reuse the actual bounds/MIME/decode/reference/UV declaration validator.
    textures = measure(path, doc, binary)
    maps, samplers = {}, {}
    for channel, key in [('base_color', 'baseColorTexture'), ('metallic_roughness', 'metallicRoughnessTexture')]:
        info = pbr.get(key)
        if info is None:
            maps[channel] = None
            continue
        if not isinstance(info, dict):
            raise ValueError('Invalid material texture binding')
        if info.get('extensions') or info.get('texCoord', 0) != 0:
            raise Unsupported('Only direct TEXCOORD_0 bindings are scoped')
        texture = index(doc.get('textures', []), info.get('index'), 'material texture')
        if texture.get('extensions'):
            raise Unsupported('Texture extensions are outside core scope')
        image_id = texture.get('source')
        image = index(textures['images'], image_id, 'image source')
        mime, data = image_bytes(path, doc, binary, doc['images'][image_id])
        if mime == 'image/png' and data[24] > 8:
            raise Unsupported('Higher-than-8-bit PNG precision is not certified by decoded RGBA8 hashes')
        value = dict(width=image['width'], height=image['height'])
        if channel == 'base_color':
            value['rgba_sha256'] = image['decoded_rgba_sha256']
        else:
            # Core glTF uses G roughness/B metallic; the unused R/A must not
            # become false failures when an exporter repacks an equivalent map.
            hashes = {c: hashlib.sha256() for c in 'GB'}
            with Image.open(io.BytesIO(data)) as actual:
                for y in range(0, actual.height, 64):
                    with actual.crop((0, y, actual.width, min(y+64, actual.height))).convert('RGBA') as strip:
                        for c in 'GB':
                            with strip.getchannel(c) as pixels:
                                hashes[c].update(pixels.tobytes())
            value['channel_sha256'] = {c: h.hexdigest() for c, h in hashes.items()}
        maps[channel] = value
        samplers[channel] = doc.get('samplers', [])[texture['sampler']] if 'sampler' in texture else None
    return dict(maps=maps, factors=factors, alpha_mode=alpha, double_sided=sided, samplers=samplers)


def equal_factors(a, b):
    def equal(x, y):
        if isinstance(x, list):
            return isinstance(y, list) and len(x) == len(y) and all(equal(i, j) for i, j in zip(x, y))
        return math.isclose(x, y, rel_tol=0, abs_tol=FACTOR_TOLERANCE)
    return all(equal(a[key], b[key]) for key in a)


def compare(source, target, *, intentional_material_edit=False):
    validator = hashlib.sha256()
    for name in ('pbr_preservation.py', 'inspection.py', 'texture_diagnostics.py'):
        validator.update(name.encode()); validator.update(Path(__file__).with_name(name).read_bytes())
    report = dict(schema_version=1, validator_sha256=validator.hexdigest(), status='NotEvaluated', checks={},
        scope='Unmodified static single-mesh single-material core PBR source to Blender LOD0',
        factor_absolute_tolerance=FACTOR_TOLERANCE, artistic_quality='NotEvaluated', sampler_fidelity='NotEvaluated',
        limitations=['Decoded core PBR pixels/factors only; no geometry, UV correspondence, hierarchy, normal, render or artistic certification.',
            'Sampler declarations are observations; unspecified filters are not certified equivalent to explicit filters.',
            'Unsupported shaders and intentional material revisions do not receive a preservation Pass.'])
    try:
        report.update(source_sha256=digest(source), target_sha256=digest(target))
        if intentional_material_edit:
            raise Unsupported('Explicit material revision; unchanged-channel verification is not implemented for this route')
        a = snapshot(source)
        target_doc, _ = glb_layout(target)
        if not target_doc.get('materials'):
            raise ValueError('Target lost the original core PBR material')
        b = snapshot(target)
        report.update(source=a, target=b)
        report['checks'] = dict(base_color_rgba=a['maps']['base_color'] == b['maps']['base_color'],
            metallic_roughness_gb=a['maps']['metallic_roughness'] == b['maps']['metallic_roughness'],
            core_factors=equal_factors(a['factors'], b['factors']), alpha_mode=a['alpha_mode'] == b['alpha_mode'],
            double_sided=a['double_sided'] == b['double_sided'])
        report['sampler_observation'] = dict(declarations_equal=a['samplers'] == b['samplers'])
        report['status'] = 'Pass' if all(report['checks'].values()) else 'Fail'
        if report['status'] == 'Fail':
            report['reason'] = 'Unrequested PBR change: ' + ', '.join(k for k, ok in report['checks'].items() if not ok)
    except Unsupported as exc:
        report['reason'] = str(exc)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError) as exc:
        report.update(status='Fail', reason='Invalid PBR roundtrip input: ' + str(exc))
    try:
        if report.get('source_sha256') != digest(source) or report.get('target_sha256') != digest(target):
            report.update(status='Fail', reason='PBR source/target changed during measurement')
    except OSError as exc:
        report.update(status='Fail', reason='PBR source/target unavailable after measurement: ' + str(exc))
    return report
