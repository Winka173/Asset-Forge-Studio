"""Validated native mesh/PBR stage boundary, independent of diffusion and Blender."""
import hashlib
import json
from pathlib import Path
import numpy as np

VERSION=1


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def identity(request):
    return {key:request.get(key) for key in ('seed','steps','pipeline_type','texture_size','export_triangle_target','effective_config_hash')}


def inspect_arrays(arrays,grid_size):
    v,f,a,c=(arrays[key] for key in ('vertices','faces','attrs','coords'))
    if v.ndim!=2 or v.shape[1]!=3 or not len(v) or not np.isfinite(v).all():raise ValueError('Native checkpoint has empty/nonfinite vertices')
    if f.ndim!=2 or f.shape[1]!=3 or not len(f) or not np.issubdtype(f.dtype,np.integer) or f.min()<0 or f.max()>=len(v):raise ValueError('Native checkpoint has empty/invalid geometry indices')
    if a.ndim!=2 or a.shape[1]!=6 or not len(a) or not np.isfinite(a).all():raise ValueError('Native checkpoint PBR field is invalid')
    if c.ndim!=2 or c.shape!=(len(a),3) or not np.issubdtype(c.dtype,np.integer) or c.min()<0 or c.max()>=grid_size:raise ValueError('Native checkpoint PBR coordinates are invalid')
    return dict(vertices=len(v),triangles=len(f),pbr_voxels=len(a),bounds_native=[v.min(axis=0).tolist(),v.max(axis=0).tolist()],
        checks=dict(finite_geometry=True,nonempty_geometry=True,valid_indices=True,finite_sparse_pbr=True,valid_sparse_coordinates=True),
        limitations=['Not a topology, self-intersection, UV or artistic approval. Native coordinate system and sparse PBR remain unchanged.'])


def save(output,arrays,request,source_sha256,revision,layout,voxel_size):
    output=Path(output);grid=512 if request['pipeline_type']=='512' else 1024
    measured=inspect_arrays(arrays,grid)
    target=output/'raw_master.npz';receipt=output/'mesh_checkpoint.json'
    if target.exists() or receipt.exists():raise ValueError('Native checkpoint must be immutable')
    temporary=output/'raw_master.npz.part'
    with temporary.open('wb') as stream:np.savez_compressed(stream,**arrays)
    temporary.replace(target)
    metadata=dict(schema_version=VERSION,stage='decoded_geometry_and_sparse_pbr',native_file=target.name,native_sha256=digest(target),
        source_sha256=source_sha256,model_revision=revision,identity=identity(request),grid_size=grid,voxel_size=float(voxel_size),
        attr_layout={name:[value.start,value.stop] for name,value in layout.items()},geometry=measured,
        resume_scope='GLB remesh/UV/PBR finishing only; not mid-diffusion inference resume',artistic_approval=False)
    temporary=receipt.with_suffix('.part');temporary.write_text(json.dumps(metadata,indent=2),'utf-8');temporary.replace(receipt)
    return metadata


def verify(receipt,request,source_sha256,revision,receipt_sha256=None,load_arrays=False):
    receipt=Path(receipt)
    if receipt_sha256 and digest(receipt)!=receipt_sha256:raise ValueError('Native checkpoint receipt checksum changed')
    metadata=json.loads(receipt.read_text('utf-8'))
    if metadata.get('schema_version')!=VERSION or metadata.get('stage')!='decoded_geometry_and_sparse_pbr':raise ValueError('Unsupported native checkpoint')
    if metadata['source_sha256']!=source_sha256 or metadata['model_revision']!=revision or metadata['identity']!=identity(request):raise ValueError('Native checkpoint source/config/model mismatch')
    grid=512 if request['pipeline_type']=='512' else 1024
    if metadata['grid_size']!=grid or abs(metadata['voxel_size']-1/grid)>1e-9:raise ValueError('Native checkpoint voxel scale changed')
    if metadata['attr_layout']!=dict(base_color=[0,3],metallic=[3,4],roughness=[4,5],alpha=[5,6]):raise ValueError('Unsupported native checkpoint PBR layout')
    if metadata['native_file']!='raw_master.npz':raise ValueError('Native checkpoint path is invalid')
    source=receipt.parent/metadata['native_file']
    if digest(source)!=metadata['native_sha256']:raise ValueError('Native checkpoint checksum changed')
    if not load_arrays:return metadata
    with np.load(source,allow_pickle=False) as data:arrays={key:data[key] for key in ('vertices','faces','attrs','coords')}
    if inspect_arrays(arrays,metadata['grid_size'])!=metadata['geometry']:raise ValueError('Native checkpoint geometry receipt mismatch')
    return metadata,arrays
