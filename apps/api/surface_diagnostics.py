"""Scale-independent triangle/shading observations, not automatic artistic judgments."""
import hashlib
from pathlib import Path
import numpy as np


def measure(mesh):
    diagonal=float(np.linalg.norm(np.ptp(mesh.vertices,axis=0)))
    imported='vertex_normals' in mesh._cache.cache
    normals=np.asarray(mesh.vertex_normals)
    finite_normals=bool(np.isfinite(normals).all())
    zero=thin=opposed=0;areas=0.;quality=[]
    for start in range(0,len(mesh.faces),65536):
        faces=mesh.faces[start:start+65536];tri=mesh.vertices[faces]
        a=tri[:,1]-tri[:,0];b=tri[:,2]-tri[:,0];cross=np.cross(a,b);double_area=np.linalg.norm(cross,axis=1)
        denominator=(a*a).sum(1)+(b*b).sum(1)+((b-a)**2).sum(1)
        q=np.divide(2*np.sqrt(3)*double_area,denominator,out=np.zeros_like(double_area),where=denominator>0)
        quality.append(q);areas+=float(double_area.sum()/2);zero+=int((double_area==0).sum());thin+=int((q<.001).sum())
        if finite_normals:
            dots=np.einsum('ij,ij->i',cross,normals[faces].mean(axis=1))
            opposed+=int((dots<0).sum())
    q=np.concatenate(quality)
    return dict(triangles=len(mesh.faces),zero_area_triangles=zero,very_thin_triangles=thin,triangle_quality_p01=float(np.percentile(q,1)),
        faces_opposing_mean_vertex_normal=opposed if finite_normals else None,finite_vertex_normals=finite_normals,
        vertex_normals_source='loaded GLB normals' if imported else 'computed by loader; source GLB normals unavailable',
        surface_area_source_units_squared=areas,bounding_diagonal_source_units=diagonal)


def summarize(rows):
    keys=('triangles','zero_area_triangles','very_thin_triangles')
    return dict(schema_version=1,validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        geometry_count=len(rows),totals={k:sum(r[k] for r in rows) for k in keys},
        faces_opposing_mean_vertex_normal=sum(r['faces_opposing_mean_vertex_normal'] or 0 for r in rows),
        all_vertex_normals_finite=all(r['finite_vertex_normals'] for r in rows),meshes=rows,
        thin_triangle_definition='2*sqrt(3)*double_area / sum(edge_length_squared) < 0.001; equilateral=1, degenerate=0',
        status='MEASURED_OBSERVATIONS_NOT_ART_APPROVAL',
        limitations=['Opposed geometric/mean vertex normals can explain shading artifacts but do not prove holes or inward surfaces.',
            'Thin triangles can be intentional; no arbitrary artistic pass/fail threshold is applied.',
            'Counts are unique local meshes, not transformed instances. No UV overlap, intersection, manifold or texture certification.'])
