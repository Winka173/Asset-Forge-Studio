"""Real GLB bytes and deliberate invalid resources, never simulated AI outputs."""
import base64
import copy
import hashlib
import io
import json
import struct
import numpy as np
import pytest
import trimesh
from PIL import Image
from apps.api.inspection import glb_layout,inspect_glb


@pytest.fixture
def textured(tmp_path):
    image = Image.new('RGBA',(16,8),(30,60,90,255))
    image.putpixel((3,2),(220,130,40,127))
    mesh = trimesh.creation.box()
    mesh.visual = trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),material=trimesh.visual.material.PBRMaterial(
        baseColorTexture=image,metallicRoughnessTexture=image,normalTexture=image,occlusionTexture=image,emissiveTexture=image))
    path = tmp_path/'actual-textured-box.glb';path.write_bytes(mesh.export(file_type='glb'))
    return path, image


def rewrite(path,change):
    doc,binary = glb_layout(path);doc=copy.deepcopy(doc)
    data=path.read_bytes()[binary[0]:binary[0]+binary[1]] if binary else b''
    changed=change(doc,data)
    if changed is not None:data=changed
    encoded=json.dumps(doc).encode();encoded+=b' '*((-len(encoded))%4)
    chunks=struct.pack('<II',len(encoded),0x4E4F534A)+encoded
    if binary:chunks+=struct.pack('<II',len(data),0x004E4942)+data
    path.write_bytes(struct.pack('<4sII',b'glTF',2,12+len(chunks))+chunks)


def test_embedded_pixels_channels_references_and_dimensions_are_measured(textured):
    path,image=textured;source=hashlib.sha256(path.read_bytes()).hexdigest()
    report=inspect_glb(path)['texture_diagnostics']
    assert report['status']=='VALIDATED_EMBEDDED_IMAGES' and len(report['images'])==5  # Exporter writes one image per binding.
    actual=report['images'][0]
    assert (actual['width'],actual['height'],actual['storage'])==(16,8,'embedded')
    assert actual['decoded_rgba_sha256']==hashlib.sha256(image.tobytes()).hexdigest()
    assert {b['channel'] for b in report['bindings']}=={'base_color','metallic_roughness','normal','occlusion','emissive'}
    assert next(b for b in report['bindings'] if b['channel']=='metallic_roughness')['packed_channels']=='G=roughness, B=metallic'
    assert all(b['primitive_uses']==1 for b in report['bindings'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==source


def test_valid_image_data_uri_keeps_identical_decoded_pixels(textured):
    path,image=textured
    def change(doc,data):
        image_doc=doc['images'][0];view=doc['bufferViews'][image_doc.pop('bufferView')]
        encoded=data[view.get('byteOffset',0):view.get('byteOffset',0)+view['byteLength']]
        image_doc['uri']='data:image/png;base64,'+base64.b64encode(encoded).decode()
    rewrite(path,change)
    assert inspect_glb(path)['texture_diagnostics']['images'][0]['decoded_rgba_sha256']==hashlib.sha256(image.tobytes()).hexdigest()


@pytest.mark.parametrize('fault', ['corrupt_pixels','bad_bounds','wrong_mime','missing_image','bad_texture','missing_uv','wrong_uv_count','nonfinite_uv'])
def test_invalid_texture_never_passes_technical_qa(textured,fault):
    path,_=textured
    def change(doc,data):
        if fault=='corrupt_pixels':
            view=doc['bufferViews'][doc['images'][0]['bufferView']];raw=bytearray(data);start=view.get('byteOffset',0);raw[start:start+8]=b'NOT_A_PN';return bytes(raw)
        if fault=='bad_bounds':doc['bufferViews'][doc['images'][0]['bufferView']]['byteOffset']=len(data)+4
        if fault=='wrong_mime':doc['images'][0]['mimeType']='image/jpeg'
        if fault=='missing_image':doc['textures'][0]['source']=999
        if fault=='bad_texture':doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index']=-1
        attrs=doc['meshes'][0]['primitives'][0]['attributes']
        if fault=='missing_uv':attrs.pop('TEXCOORD_0')
        if fault=='wrong_uv_count':doc['accessors'][attrs['TEXCOORD_0']]['count']+=1
        if fault=='nonfinite_uv':
            acc=doc['accessors'][attrs['TEXCOORD_0']];view=doc['bufferViews'][acc['bufferView']];raw=bytearray(data)
            start=view.get('byteOffset',0)+acc.get('byteOffset',0);raw[start:start+4]=struct.pack('<f',float('nan'));return bytes(raw)
    rewrite(path,change)
    with pytest.raises(ValueError):inspect_glb(path)


def test_constant_material_does_not_invent_missing_texture_maps(tmp_path):
    path=tmp_path/'actual-clay-box.glb';path.write_bytes(trimesh.creation.box().export(file_type='glb'))
    result=inspect_glb(path)['texture_diagnostics']
    assert result['images']==result['bindings']==[] and result['checks']['image_decode']=='PASS'
