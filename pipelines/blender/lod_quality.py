"""Measured sampled surface deviation in a common world space, never an art score."""
import numpy as np
import hashlib
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def geometry(objects):
    vertices=[];faces=[];offset=0
    for obj in objects:
        mesh=obj.data;mesh.calc_loop_triangles()
        points=np.empty(len(mesh.vertices)*3,dtype=np.float64);mesh.vertices.foreach_get('co',points)
        points=points.reshape(-1,3);matrix=np.array(obj.matrix_world,dtype=np.float64)
        points=points@matrix[:3,:3].T+matrix[:3,3]
        triangles=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',triangles)
        vertices.append(points);faces.append(triangles.reshape(-1,3)+offset);offset+=len(points)
    if not vertices:raise ValueError('LOD surface comparison requires actual geometry')
    v=np.concatenate(vertices);f=np.concatenate(faces)
    if not len(f) or not np.isfinite(v).all():raise ValueError('LOD comparison has invalid geometry')
    return v,f


def surface(vertices,faces,samples,seed):
    triangles=vertices[faces];cross=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]);areas=np.linalg.norm(cross,axis=1)
    cumulative=np.cumsum(areas);total=cumulative[-1]
    if total<=0:raise ValueError('LOD comparison has no positive-area surface')
    random=np.random.default_rng(seed);indices=np.searchsorted(cumulative,random.random(samples)*total)
    uv=random.random((samples,2));root=np.sqrt(uv[:,0]);weights=np.column_stack((1-root,root*(1-uv[:,1]),root*uv[:,1]))
    points=(triangles[indices]*weights[:,:,None]).sum(axis=1)
    normals=cross[indices]/areas[indices,None]
    return points,normals


class SurfaceReference:
    def __init__(self,objects,samples=8192,seed=43):
        vertices,faces=geometry(objects);self.count=len(faces);self.samples=samples;self.seed=seed
        self.diagonal=float(np.linalg.norm(vertices.max(axis=0)-vertices.min(axis=0)))
        self.tree=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)
        self.points,self.normals=surface(vertices,faces,samples,seed)

    def compare(self,objects):
        vertices,faces=geometry(objects);tree=BVHTree.FromPolygons(vertices.tolist(),faces.tolist(),all_triangles=True)
        points,normals=surface(vertices,faces,self.samples,self.seed)
        def measure(points,normals,target):
            distances=[];angles=[]
            for point,normal in zip(points,normals):
                nearest,other,_,distance=target.find_nearest(Vector(point))
                if nearest is None:raise ValueError('No nearest LOD surface found')
                distances.append(distance);angles.append(np.degrees(np.arccos(np.clip(np.dot(normal,other),-1,1))))
            return dict(mean=float(np.mean(distances)),p95=float(np.percentile(distances,95)),sampled_max=float(max(distances)),rms=float(np.sqrt(np.mean(np.square(distances)))),normal_angle_mean_degrees=float(np.mean(angles)))
        forward=measure(self.points,self.normals,tree);reverse=measure(points,normals,self.tree)
        return dict(schema_version=1,validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),method='Area-weighted triangle samples / exact BVH nearest surface at sampled points',samples_per_direction=self.samples,seed=self.seed,
            master_triangles=self.count,target_triangles=len(faces),master_to_lod=forward,lod_to_master=reverse,
            symmetric_p95_relative_diagonal=max(forward['p95'],reverse['p95'])/self.diagonal if self.diagonal else None,
            symmetric_sampled_max_relative_diagonal=max(forward['sampled_max'],reverse['sampled_max'])/self.diagonal if self.diagonal else None,
            coordinate_space='Shared Blender world units; physical metres require calibrated source scale',
            limitations=['Sampled maximum is not the global Hausdorff maximum. Thin features can be missed.',
                'Geometric face-normal deviation is not a texture/shader/artistic rating. No silhouette, UV or bake-coverage certification.'])
