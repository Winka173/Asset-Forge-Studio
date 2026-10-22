"""Authored four-corner castle profile; never arbitrary generated Python execution.

Inputs are a validated data-only spec. Produce named geometry/material zones,
actual structure measurements, packed PBR and an immutable source .blend.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path,value):path.write_text(json.dumps(value,indent=2),encoding='utf-8')


def bounds(objects):
    points=[o.matrix_world@Vector(v) for o in objects for v in o.bound_box]
    return [[min(p[i] for p in points) for i in range(3)],[max(p[i] for p in points) for i in range(3)]]


def material(name,hex_color,resolution,seed,folder):
    color=np.array([int(hex_color[i:i+2],16)/255 for i in (1,3,5)],dtype=np.float32)
    rng=np.random.default_rng(seed);noise=rng.random((resolution,resolution),dtype=np.float32)
    y,x=np.mgrid[0:resolution,0:resolution].astype(np.float32)/resolution
    height=.45+.08*np.sin(x*math.tau*(5 if name=='oak' else 3))+.045*noise
    if name=='oak':height+=.1*np.sin(x*math.tau*40+.8*np.sin(y*math.tau*2))
    data=np.ones((resolution,resolution,4),dtype=np.float32);data[:,:,:3]=np.clip(color*(.88+.18*height[:,:,None]),0,1)
    def texture(label,pixels,noncolor=False):
        image=bpy.data.images.new(name+'_'+label,width=resolution,height=resolution,alpha=True)
        if noncolor:image.colorspace_settings.name='Non-Color'
        image.pixels.foreach_set(pixels.ravel());image.filepath_raw=str(folder/(name+'_'+label+'.png'));image.file_format='PNG';image.save();image.pack();return image
    base=texture('basecolor',data)
    data[:,:,:3]=(.65+.12*noise[:,:,None]) if name!='bronze' else (.32+.1*noise[:,:,None])
    rough=texture('roughness',data,True)
    dy,dx=np.gradient(height);normal=np.stack((-dx*4,-dy*4,np.ones_like(dx)),axis=2);normal/=np.linalg.norm(normal,axis=2)[:,:,None]
    data[:,:,:3]=normal*.5+.5;normalmap=texture('normal',data,True)
    mat=bpy.data.materials.new(name);mat.use_nodes=True;nodes=mat.node_tree.nodes;links=mat.node_tree.links
    bsdf=nodes.get('Principled BSDF');bsdf.inputs['Metallic'].default_value=.7 if name=='bronze' else 0
    for label,image,socket in [('basecolor',base,'Base Color'),('roughness',rough,'Roughness')]:
        node=nodes.new('ShaderNodeTexImage');node.image=image;links.new(node.outputs['Color'],bsdf.inputs[socket])
    node=nodes.new('ShaderNodeTexImage');node.image=normalmap;converter=nodes.new('ShaderNodeNormalMap');converter.inputs['Strength'].default_value=.35
    links.new(node.outputs['Color'],converter.inputs['Color']);links.new(converter.outputs['Normal'],bsdf.inputs['Normal'])
    return mat


def finish(obj,name,mat):
    obj.name=name;obj.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    bevel=obj.modifiers.new('authored_edge_highlights','BEVEL');bevel.width=.018;bevel.segments=2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return obj


def cube(name,center,size,mat):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center);obj=bpy.context.object;obj.dimensions=size;return finish(obj,name,mat)


def cylinder(name,center,radius,depth,mat,vertices=32,radius_top=None):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices,radius1=radius,radius2=radius if radius_top is None else radius_top,depth=depth,location=center)
    return finish(bpy.context.object,name,mat)


def join(name,objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0];bpy.ops.object.join();result=bpy.context.object;result.name=name;return result


def brick_wall(name,axis,start,end,position,height,base,thickness,mat,rng):
    parts=[];courses=7;length=end-start;brick=length/max(2,round(length/(height*.7)))
    for row in range(courses):
        a=start-(brick*.5 if row%2 else 0)
        while a<end-1e-6:
            left=max(start,a);right=min(end,a+brick)
            if right-left>brick*.08:
                center=[(left+right)/2,position,base+(row+.5)*height/courses];size=[right-left-.008,thickness,height/courses-.008]
                if axis=='y':center[0],center[1]=center[1],center[0];size[0],size[1]=size[1],size[0]
                parts.append(cube('stone',center,size,mat))
            a+=brick
    n=max(2,round(length/(thickness*1.8)))
    for i in range(n):
        along=start+(i+.5)*length/n;center=[along,position,base+height+height*.08];size=[length/n*.55,thickness*1.1,height*.16]
        if axis=='y':center[0],center[1]=center[1],center[0];size[0],size[1]=size[1],size[0]
        parts.append(cube('merlon',center,size,mat))
    return join(name,parts)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);args=parser.parse_args(sysargs())
    req=json.loads(Path(args.request).read_text(encoding='utf-8'));spec=req['spec'];out=Path(req['output']).resolve()
    if out.exists():raise ValueError('New immutable assembly directory required')
    out.mkdir(parents=True);textures=out/'textures';textures.mkdir();bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1
    width,depth,height=spec['bounds_m'];seed=req['seed'];rng=np.random.default_rng(seed);tex=req['texture_size']
    if min(width,depth,height)<=0 or max(width,depth,height)>1000:raise ValueError('Invalid assembly bounds')
    colors=spec['material_colors'];mats={k:material(n,colors[k],tex,seed+i,textures) for i,(k,n) in enumerate([('stone','limestone'),('wood','oak'),('roof','slate'),('metal','bronze')])}
    w,d,h=width,depth,height;base=h*.025;thickness=min(w,d)*.055;x=w*.36;y=d*.36;r=min(w,d)*.10
    floor=cube('foundation',(0,0,base/2),(w,d,base),mats['stone'])
    keep=cube('keep',(0,d*.04,base+h*.31),(w*.32,d*.34,h*.62),mats['stone'])
    # A hipped roof with a ridge and explicit height, never a tower substituted for keep.
    z=base+h*.62;verts=[(-w*.18,-d*.15,z),(w*.18,-d*.15,z),(w*.18,d*.23,z),(-w*.18,d*.23,z),(-w*.10,d*.04,h),(w*.10,d*.04,h)]
    mesh=bpy.data.meshes.new('keep_roof_mesh');mesh.from_pydata(verts,[],[(0,1,5,4),(1,2,5),(2,3,4,5),(3,0,4),(0,3,2,1)]);mesh.update()
    obj=bpy.data.objects.new('keep_roof',mesh);bpy.context.collection.objects.link(obj);bpy.context.view_layer.objects.active=obj;obj.select_set(True);obj.data.materials.append(mats['roof'])
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project();bpy.ops.object.mode_set(mode='OBJECT')
    for label,xx,yy in [('nw',-x,y),('ne',x,y),('sw',-x,-y),('se',x,-y)]:
        cylinder('corner_tower_'+label,(xx,yy,base+h*.32),r,h*.64,mats['stone'])
        for tier in range(10):
            zz=base+h*.64+tier*h*.017;radius=r*1.12*(1-tier/11)
            cylinder('roof_'+label+'_'+str(tier),(xx,yy,zz+h*.0085),radius,h*.017,mats['roof'],radius_top=radius*.85)
        cylinder('finial_'+label,(xx,yy,base+h*.82),r*.06,h*.06,mats['metal'],radius_top=0)
        for course in (1,3,5):cylinder('tower_band_'+label+'_'+str(course),(xx,yy,base+course*h*.1),r*1.018,h*.025,mats['stone'])
    wallheight=h*.30;gap=w*.09
    wall_specs=[('north','x',-x,x,y),('west','y',-y,y,-x),('east','y',-y,y,x),('south_west','x',-x,-gap,-y),('south_east','x',gap,x,-y)]
    walls=[brick_wall('curtain_wall_'+name,axis,a,b,pos,wallheight,base,thickness,mats['stone'],rng) for name,axis,a,b,pos in wall_specs]
    spring=base+h*.18;outer=gap+w*.035
    for side,sign in [('left',-1),('right',1)]:cube('gate_pier_'+side,(sign*(gap+w*.0175),-y,base+h*.09),(w*.035,thickness*1.7,h*.18),mats['stone'])
    pieces=[]
    for i in range(14):
        a=i*math.pi/14+.008;b=(i+1)*math.pi/14-.008;vs=[]
        for yy in (-y-thickness*.85,-y+thickness*.85):
            vs.extend([(math.cos(t)*rr,yy,spring+math.sin(t)*rr) for rr,t in [(gap,a),(outer,a),(outer,b),(gap,b)]])
        me=bpy.data.meshes.new('voussoir');me.from_pydata(vs,[],[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]);me.update()
        ob=bpy.data.objects.new('voussoir',me);bpy.context.collection.objects.link(ob);ob.data.materials.append(mats['stone']);pieces.append(ob)
    gate=join('gate_arch',pieces)
    # Authored windows, wood shutters and lintels remain separate material zones.
    for side in (-1,1):
        for row in range(2):
            for column in (-1,0,1):
                cube('keep_window',(column*w*.075,d*.04+side*d*.171,base+h*(.23+row*.19)),(w*.04,d*.012,h*.075),mats['wood'])
                cube('window_lintel',(column*w*.075,d*.04+side*d*.176,base+h*(.28+row*.19)),(w*.055,d*.023,h*.016),mats['stone'])
    bpy.context.view_layer.update();meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];low,high=bounds(meshes)
    towers=[o for o in meshes if o.name.startswith('corner_tower_')];wallmeshes=[o for o in meshes if o.name.startswith('curtain_wall_')]
    contacts=[]
    for wall in wallmeshes:
        lo,hi=bounds([wall]);touch=[]
        for tower in towers:
            tl,th=bounds([tower])
            if all(min(hi[i],th[i])-max(lo[i],tl[i])>=-1e-4 for i in range(3)):touch.append(tower.name)
        contacts.append(dict(wall=wall.name,touches=touch))
    # Geometric clearance at the opening, above the foundation and below spring.
    portal=[[-gap*.85,-y-thickness,base+.005],[gap*.85,-y+thickness,spring-.005]];obstructions=[]
    for ob in meshes:
        if ob==floor:continue
        lo,hi=bounds([ob])
        if all(min(hi[i],portal[1][i])-max(lo[i],portal[0][i])>1e-4 for i in range(3)):obstructions.append(ob.name)
    checks=dict(keep_count=sum(o.name=='keep' for o in meshes)==1,corner_tower_count=len(towers)==4,curtain_wall_count=len(wallmeshes)==5,
        wall_tower_contacts=all(c['touches'] for c in contacts),gate_arch_present=gate.name in bpy.data.objects,gate_clearance=not obstructions,
        declared_bounds=all(abs((high[i]-low[i])-v)<=max(.005,v*.002) for i,v in enumerate((w,d,h))))
    if not all(checks.values()):raise ValueError('Castle structure failed: '+json.dumps(checks)+' obstructions='+str(obstructions))
    # UV every authored mesh lacking coordinates. No geometry or global remesh reduction.
    bpy.ops.object.select_all(action='DESELECT')
    for ob in meshes:
        if not ob.data.uv_layers:
            ob.select_set(True);bpy.context.view_layer.objects.active=ob;bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.uv.smart_project();bpy.ops.object.mode_set(mode='OBJECT');ob.select_set(False)
    tower_names={o.name for o in towers}
    bpy.ops.object.select_all(action='SELECT');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'assembly.blend'))
    bpy.ops.export_scene.gltf(filepath=str(out/'raw.glb'),export_format='GLB',export_yup=True,export_animations=False)
    # Real importer proof, not just a successful exporter return code.
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(out/'raw.glb'))
    reopened=[o for o in bpy.context.scene.objects if o.type=='MESH'];names={o.name for o in reopened}
    if not {'keep','gate_arch',*tower_names}<=names:raise ValueError('Named components lost during GLB reopen')
    report=dict(schema_version=1,profile='four_corner_castle_v1',blender_version=bpy.app.version_string,script_sha256=sha(__file__),spec=req['spec'],spec_sha256=req['spec_sha256'],seed=seed,
        checks=checks,contacts=contacts,portal_clearance=portal,portal_obstructions=obstructions,bounds_xyz_blender=[low,high],
        components=[dict(name=o.name,triangles=sum(len(p.vertices)-2 for p in o.data.polygons)) for o in reopened],
        texture_resolution=tex,texture_method='Authored seeded procedural basecolor/roughness/tangent normal, embedded in GLB',
        export_reopen='PASS',output_sha256=sha(out/'raw.glb'),artistic_approval=False,limitations=req['spec']['limitations'])
    write(out/'assembly.json',report)


def sysargs():
    import sys
    return sys.argv[sys.argv.index('--')+1:]


if __name__=='__main__':main()
