"""Restricted named-zone recoloring; data-only, geometry and other materials retained."""
import hashlib
from pathlib import Path
import numpy as np
import bpy


def signature(objects):
    values={}
    for obj in objects:
        vertices=np.array([obj.matrix_world@v.co for v in obj.data.vertices],dtype=np.float64)
        polygons=[tuple(p.vertices) for p in obj.data.polygons]
        values[obj.name]=dict(vertices=vertices,polygons=polygons)
    return values


def compare(before,objects):
    after=signature(objects)
    if before.keys()!=after.keys():raise ValueError('Material edit changed mesh identities')
    maximum=0.
    for name,old in before.items():
        new=after[name]
        if old['polygons']!=new['polygons'] or old['vertices'].shape!=new['vertices'].shape:raise ValueError('Material edit changed topology')
        delta=float(np.abs(old['vertices']-new['vertices']).max()) if old['vertices'].size else 0.
        maximum=max(maximum,delta)
        if delta>1e-6:raise ValueError('Material edit changed geometry')
    return dict(mesh_count=len(after),topology_unchanged=True,max_world_vertex_delta_m=maximum)


def recolor(objects,request,output):
    selected=set(request['material_names']);target=request['color_hex']
    color=np.array([int(target[i:i+2],16)/255 for i in (1,3,5)],dtype=np.float32);changed=[]
    materials={m.name:m for o in objects for m in o.data.materials if m}
    if not selected<=materials.keys():raise ValueError('Pinned roof material not present')
    for name in selected:
        mat=materials[name]
        users=[o.name for o in objects if mat in list(o.data.materials)]
        if any(not(n.startswith('roof_') or n.endswith('_roof')) for n in users):raise ValueError('Roof material is shared outside roof; edit refused')
        bsdf=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None) if mat.use_nodes else None
        if not bsdf:raise ValueError('Unsupported roof shader')
        socket=bsdf.inputs['Base Color'];old_factor=list(socket.default_value);image_hashes=[]
        if socket.is_linked:
            linked=socket.links[0].from_node
            if linked.type!='TEX_IMAGE' or not linked.image:raise ValueError('Only direct basecolor image input is supported')
            image=linked.image.copy();linked.image=image
            pixels=np.empty(len(image.pixels),dtype=np.float32);image.pixels.foreach_get(pixels);data=pixels.reshape((-1,4))
            old_hash=hashlib.sha256(pixels.tobytes()).hexdigest()
            luminance=data[:,:3]@np.array([.2126,.7152,.0722],dtype=np.float32);average=max(float(luminance.mean()),.001)
            data[:,:3]=np.clip(color[None,:]*(luminance/average)[:,None],0,1)
            image.pixels.foreach_set(data.ravel());image.update()
            if image.packed_file:image.unpack(method='REMOVE')
            image.filepath_raw=str(Path(output)/('edited_roof_'+hashlib.sha256(name.encode()).hexdigest()[:12]+'.png'));image.file_format='PNG';image.save();image.pack()
            socket.default_value=(1,1,1,1)
            image_hashes.append(dict(before_pixels_sha256=old_hash,after_pixels_sha256=hashlib.sha256(data.tobytes()).hexdigest(),resolution=list(image.size)))
        else:socket.default_value=(*color,old_factor[3])
        changed.append(dict(material=name,meshes=users,color_hex=target,previous_factor=old_factor,images=image_hashes))
    return dict(method='Named roof basecolor edit; luminance detail, UV, normals and roughness retained',changed=changed,artistic_approval=False)
