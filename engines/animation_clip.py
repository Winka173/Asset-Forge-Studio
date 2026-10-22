"""Lossless clip retiming: append new time accessors, keep original geometry/skin bytes."""
import copy
import json
import math
import struct
from pathlib import Path
import numpy as np
from apps.api.inspection import glb_document


def read(path):
    document=glb_document(path);data=Path(path).read_bytes();offset=12;binary=None
    while offset<len(data):
        length,kind=struct.unpack_from('<I4s',data,offset);offset+=8
        if kind==b'BIN\x00':
            if binary is not None:raise ValueError('Multiple GLB binary chunks are unsupported')
            binary=data[offset:offset+length]
        offset+=length
    if binary is None or len(document.get('buffers',[]))!=1:raise ValueError('Animation edits require one embedded GLB buffer')
    return document,binary


def time_values(document,binary,index):
    accessor=document['accessors'][index]
    if accessor.get('componentType')!=5126 or accessor.get('type')!='SCALAR' or accessor.get('sparse') or accessor.get('normalized'):
        raise ValueError('Animation times require non-sparse float32 SCALAR accessors')
    view=document['bufferViews'][accessor['bufferView']]
    if view.get('buffer',0)!=0:raise ValueError('External animation buffers are unsupported')
    stride=view.get('byteStride',4);count=accessor['count'];relative=accessor.get('byteOffset',0);start=view.get('byteOffset',0)+relative
    if count<1 or stride<4 or stride%4 or start%4 or relative<0 or start<0 or relative+(count-1)*stride+4>view['byteLength'] or start+(count-1)*stride+4>len(binary):raise ValueError('Animation time accessor is outside its buffer view')
    values=np.ndarray((count,),dtype='<f4',buffer=binary,offset=start,strides=(stride,)).copy()
    if not np.isfinite(values).all() or np.any(values<0) or np.any(np.diff(values)<=0):raise ValueError('Animation key times must be finite, non-negative and strictly increasing')
    return values


def clips(path):
    document,binary=read(path);result=[]
    for index,animation in enumerate(document.get('animations',[])):
        values=[time_values(document,binary,s['input']) for s in animation.get('samplers',[])]
        if not values:raise ValueError('Animation has no samplers')
        start=min(float(v[0]) for v in values);end=max(float(v[-1]) for v in values)
        supported=all(s.get('interpolation','LINEAR') in ('LINEAR','STEP') for s in animation['samplers'])
        result.append(dict(index=index,name=animation.get('name') or f'Clip {index+1}',start_seconds=start,end_seconds=end,duration_seconds=end-start,channels=len(animation.get('channels',[])),samplers=len(values),retime_supported=supported,retime_limitation=None if supported else 'Cubic-spline tangent retiming is not validated'))
    return dict(clips=result,skins=len(document.get('skins',[])),bones=sum(len(s['joints']) for s in document.get('skins',[])))


def write(path,document,binary):
    data=json.dumps(document,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode();data+=b' '*((-len(data))%4)
    binary=bytes(binary);binary+=b'\x00'*((-len(binary))%4)
    content=struct.pack('<4sII',b'glTF',2,12+8+len(data)+8+len(binary))+struct.pack('<I4s',len(data),b'JSON')+data+struct.pack('<I4s',len(binary),b'BIN\x00')+binary
    Path(path).write_bytes(content)


def retime(source,target,index,speed):
    if not math.isfinite(speed) or not .25<=speed<=4:raise ValueError('Clip speed must be between 0.25 and 4')
    document,binary=read(source);metadata=clips(source)
    if not 0<=index<len(metadata['clips']):raise ValueError('Choose an existing animation clip')
    info=metadata['clips'][index]
    if info['duration_seconds']<=0:raise ValueError('Cannot retime a zero-duration clip')
    result=copy.deepcopy(document);data=bytearray(binary);remap={}
    for sampler in result['animations'][index]['samplers']:
        if sampler.get('interpolation','LINEAR') not in ('LINEAR','STEP'):raise ValueError('This verified route supports LINEAR and STEP clips only; cubic-spline tangents require separate retiming validation')
        original=sampler['input']
        if original not in remap:
            times=time_values(document,binary,original)/speed
            # Float32 resampling must remain strictly monotonic after conversion.
            if not np.isfinite(times).all() or np.any(np.diff(times)<=0):raise ValueError('Retimed key times lost float32 precision')
            data.extend(b'\x00'*((-len(data))%4));offset=len(data);raw=times.astype('<f4').tobytes();data.extend(raw)
            view=len(result['bufferViews']);result['bufferViews'].append(dict(buffer=0,byteOffset=offset,byteLength=len(raw)))
            accessor=len(result['accessors']);result['accessors'].append(dict(bufferView=view,componentType=5126,count=len(times),type='SCALAR',min=[float(times[0])],max=[float(times[-1])]))
            remap[original]=accessor
        sampler['input']=remap[original]
    result['buffers'][0]['byteLength']=len(data)
    write(target,result,data)
    after=clips(target)['clips'][index]
    return dict(operation='retime_existing_clip',clip_index=index,speed=speed,before=info,after=after,original_binary_prefix_preserved=bytes(data[:len(binary)])==binary,
                geometry_skin_materials_unchanged=all(document.get(k)==result.get(k) for k in ('meshes','skins','nodes','materials','images','textures','samplers','scenes','scene')),artistic_quality='not_reviewed')


def single_clip(source,target,index):
    document,binary=read(source);document['animations']=[document['animations'][index]];write(target,document,binary)
