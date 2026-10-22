"""Validate actual embedded core glTF images and material bindings, not PBR aesthetics.

No network, inferred texture detail, resizing or generated maps. Images are decoded
one at a time; decoded RGBA hashes use strips to avoid another full pixel copy.
"""
import base64
import binascii
import hashlib
import io
from pathlib import Path
from urllib.parse import unquote_to_bytes
from PIL import Image

MAX_PIXELS = 8192 * 8192
MAX_ENCODED_BYTES = 256 * 1024**2


def index(values, value, label):
    if type(value) is not int or not 0 <= value < len(values):raise ValueError(f'Invalid embedded texture {label} index: {value}')
    return values[value]


def integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:raise ValueError(f'Invalid embedded texture {label}')
    return value


def data_uri(uri):
    if not isinstance(uri, str) or not uri.startswith('data:') or ',' not in uri:raise ValueError('Embedded texture requires a self-contained data URI')
    header, encoded = uri[5:].split(',', 1)
    if len(encoded) > MAX_ENCODED_BYTES * 4 // 3 + 8:raise ValueError('Embedded texture data URI exceeds supported size')
    parts = header.split(';')
    try:data = base64.b64decode(encoded, validate=True) if 'base64' in parts[1:] else unquote_to_bytes(encoded)
    except (ValueError, binascii.Error) as exc:raise ValueError('Invalid embedded texture data URI encoding') from exc
    if len(data) > MAX_ENCODED_BYTES:raise ValueError('Embedded texture exceeds supported size')
    return parts[0], data


def image_bytes(path, doc, binary, image):
    if ('uri' in image) == ('bufferView' in image):raise ValueError('Embedded image must have exactly one uri or bufferView')
    if 'uri' in image:
        mime, data = data_uri(image['uri'])
        if image.get('mimeType') and image['mimeType'] != mime:raise ValueError('Embedded image data URI / mimeType mismatch')
        return mime, data
    view = index(doc.get('bufferViews', []), image['bufferView'], 'bufferView')
    buffer_id = view.get('buffer'); buffer = index(doc.get('buffers', []), buffer_id, 'buffer')
    offset = integer(view.get('byteOffset', 0), 'byteOffset'); length = integer(view.get('byteLength'), 'byteLength', 1)
    declared = integer(buffer.get('byteLength'), 'buffer byteLength', 1)
    if length > MAX_ENCODED_BYTES or offset + length > declared:raise ValueError('Embedded image exceeds buffer bounds or supported size')
    if 'uri' in buffer:
        _, data = data_uri(buffer['uri'])
        if len(data) != declared:raise ValueError('Embedded image buffer data URI byteLength mismatch')
        data = data[offset:offset+length]
    else:
        if buffer_id != 0 or binary is None or not declared <= binary[1] <= declared + 3:raise ValueError('Embedded image BIN byteLength mismatch')
        with Path(path).open('rb') as stream:
            stream.seek(binary[0]+offset); data = stream.read(length)
        if len(data) != length:raise ValueError('Truncated embedded image bufferView')
    return image.get('mimeType'), data


def measure(path, doc, binary):
    images = []
    for number, image in enumerate(doc.get('images', [])):
        mime, data = image_bytes(path, doc, binary, image)
        if mime not in ('image/png', 'image/jpeg'):raise ValueError(f'Embedded image {number}: unsupported MIME {mime}; use core PNG/JPEG')
        try:
            with Image.open(io.BytesIO(data)) as actual:
                if actual.format != {'image/png':'PNG','image/jpeg':'JPEG'}[mime]:raise ValueError('Embedded image bytes do not match declared MIME')
                width, height = actual.size
                if width * height > MAX_PIXELS:raise ValueError('Embedded image exceeds supported 8192-square pixel budget')
                actual.verify()
            with Image.open(io.BytesIO(data)) as actual:
                actual.load(); digest = hashlib.sha256()
                for y in range(0, height, 64):
                    with actual.crop((0,y,width,min(y+64,height))) as strip:
                        with strip.convert('RGBA') as rgba:digest.update(rgba.tobytes())
                images.append(dict(index=number,name=image.get('name'),width=width,height=height,mime_type=mime,
                    encoded_bytes=len(data),encoded_sha256=hashlib.sha256(data).hexdigest(),decoded_rgba_sha256=digest.hexdigest(),
                    storage='embedded',decode='PASS'))
        except (OSError,Image.DecompressionBombError,Image.DecompressionBombWarning) as exc:raise ValueError(f'Embedded image {number} cannot decode: {exc}') from exc
    textures = doc.get('textures', []); bindings = []
    for number, material in enumerate(doc.get('materials', [])):
        pbr = material.get('pbrMetallicRoughness', {})
        channels = dict(base_color=pbr.get('baseColorTexture'),metallic_roughness=pbr.get('metallicRoughnessTexture'),
            normal=material.get('normalTexture'),occlusion=material.get('occlusionTexture'),emissive=material.get('emissiveTexture'))
        for channel, info in channels.items():
            if info is None:continue
            texture_id = info.get('index'); texture = index(textures, texture_id, 'material texture')
            source_id = texture.get('source'); index(images, source_id, 'image source')
            texcoord = integer(info.get('extensions',{}).get('KHR_texture_transform',{}).get('texCoord',info.get('texCoord',0)), 'texCoord')
            if 'sampler' in texture:index(doc.get('samplers',[]),texture['sampler'],'sampler')
            uses = 0
            for mesh in doc.get('meshes', []):
                for primitive in mesh.get('primitives', []):
                    if primitive.get('material') != number:continue
                    uses += 1; attrs = primitive.get('attributes',{}); key = f'TEXCOORD_{texcoord}'
                    if key not in attrs:raise ValueError(f'Textured material {number} uses missing {key}')
                    accessor = index(doc.get('accessors',[]),attrs[key],key)
                    position = index(doc.get('accessors',[]),attrs.get('POSITION'),'POSITION')
                    if accessor.get('type') != 'VEC2' or accessor.get('count') != position.get('count'):raise ValueError(f'Textured material {number} has invalid {key} shape/count')
            bindings.append(dict(material_index=number,material_name=material.get('name') or f'Material {number+1}',channel=channel,
                texture_index=texture_id,image_index=source_id,texcoord=texcoord,primitive_uses=uses,
                encoding='sRGB' if channel in ('base_color','emissive') else 'linear',
                packed_channels='G=roughness, B=metallic' if channel=='metallic_roughness' else 'R=occlusion' if channel=='occlusion' else None))
    # Validate all texture source/sampler references, including unused texture entries.
    for texture in textures:
        index(images,texture.get('source'),'image source')
        if 'sampler' in texture:index(doc.get('samplers',[]),texture['sampler'],'sampler')
    return dict(schema_version=1,validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        status='VALIDATED_EMBEDDED_IMAGES',images=images,bindings=bindings,
        checks=dict(image_decode='PASS',embedded_image_bounds='PASS',material_texture_references='PASS',texture_coordinate_declarations='PASS'),
        limitations=['Checks decoded PNG/JPEG images, references and declared UV shape/count, not UV overlap, texel density, shader fidelity or artistic detail.',
            'Resolution and decoded pixel hashes do not establish AI detail, PBR plausibility or Meshy equivalence. No texture or source is modified.'])
