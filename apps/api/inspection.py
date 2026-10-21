"""Inspect self-contained glTF 2.0; reject external resource access before loaders."""
import io
import json
import struct
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image


def glb_document(path):
    size = Path(path).stat().st_size
    with open(path, "rb") as f:
        header = f.read(12)
        if len(header) != 12:
            raise ValueError("Truncated GLB header")
        magic, version, length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2 or length != size:
            raise ValueError("Expected valid GLB 2.0 with exact declared length")
        chunks = []
        while f.tell() < size:
            raw = f.read(8)
            if len(raw) != 8:
                raise ValueError("Truncated GLB chunk")
            count, kind = struct.unpack("<II", raw)
            if count % 4 or f.tell() + count > size:
                raise ValueError("Invalid GLB chunk bounds/alignment")
            chunks.append((kind, f.read(count)))
    if not chunks or chunks[0][0] != 0x4E4F534A:
        raise ValueError("Missing JSON first chunk")
    doc = json.loads(chunks[0][1])
    if doc.get("asset", {}).get("version") != "2.0":
        raise ValueError("Only glTF 2.0 supported")
    if doc.get("extensionsRequired"):
        raise ValueError("Decode required extensions before import: " + str(doc["extensionsRequired"]))
    for item in doc.get("buffers", []) + doc.get("images", []):
        if "uri" in item and not item["uri"].startswith("data:"):
            raise ValueError("GLB must embed all buffers/textures; external URI rejected")
    return doc


def inspect_glb(path):
    doc = glb_document(path)
    scene = trimesh.load(path, force="scene", process=False)
    rows, all_bounds = [], []
    for node in scene.graph.nodes_geometry:
        transform, key = scene.graph[node]
        mesh = scene.geometry[key]
        if not isinstance(mesh, trimesh.Trimesh) or not len(mesh.faces):
            raise ValueError("Mesh is empty or not triangles")
        vertices = trimesh.transform_points(mesh.vertices, transform)
        if not np.isfinite(vertices).all():
            raise ValueError("Mesh contains NaN/Inf coordinates")
        all_bounds.extend([vertices.min(axis=0), vertices.max(axis=0)])
        welded = mesh.copy()
        welded.merge_vertices(merge_tex=True, merge_norm=True, digits_vertex=8)
        rows.append({"node": node, "triangles": len(mesh.faces), "vertices": len(mesh.vertices),
                     "watertight": bool(mesh.is_watertight), "winding_consistent": bool(mesh.is_winding_consistent),
                     "watertight_after_position_weld_1e8": bool(welded.is_watertight),
                     "topology_note": "Raw GLB vertices can split at UV/normal seams; position-weld result is a proxy, not a hole/intersection proof",
                     "has_uv": getattr(mesh.visual, "uv", None) is not None})
    if not rows:
        raise ValueError("GLB contains no renderable meshes")
    bounds = np.asarray(all_bounds)
    dimensions = bounds.max(axis=0) - bounds.min(axis=0)
    if not np.isfinite(dimensions).all() or dimensions.max() <= 1e-8:
        raise ValueError("Degenerate geometry bounds")
    materials = []
    for m in doc.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        materials.append({"name": m.get("name", "unnamed"),
                          "base_color_texture": "baseColorTexture" in pbr,
                          "metallic_roughness_texture": "metallicRoughnessTexture" in pbr,
                          "normal_texture": "normalTexture" in m,
                          "ao_texture": "occlusionTexture" in m,
                          "emissive_texture": "emissiveTexture" in m,
                          "metallic_factor": pbr.get("metallicFactor", 1),
                          "roughness_factor": pbr.get("roughnessFactor", 1)})
    return {"status": "NEEDS_REVIEW", "triangles": sum(m["triangles"] for m in rows),
            "mesh_instances": len(rows), "dimensions_xyz_m": dimensions.tolist(),
            "bounds_xyz_m": [bounds.min(axis=0).tolist(), bounds.max(axis=0).tolist()],
            "coordinate_system": "glTF Y-up, meters; scale is unapproved source scale",
            "meshes": rows, "materials": materials, "images": len(doc.get("images", [])),
            "checks": {"container": "PASS", "finite_nonempty_geometry": "PASS",
                       "external_resources": "PASS", "uv_overlap": "NOT_TESTED",
                       "self_intersections": "NOT_TESTED", "pbr_plausibility": "NOT_TESTED",
                       "dimensions_approved": "NOT_TESTED", "unity_import": "NOT_TESTED",
                       "human_quality": "NOT_TESTED"}}


def inspect_image(path):
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        if im.width * im.height > 40_000_000:
            raise ValueError("Image exceeds 40 megapixels")
        gray = np.asarray(im.convert("L"), dtype=np.float32)
        sharpness = float(np.var(gray[1:-1, :-2] + gray[1:-1, 2:] + gray[:-2, 1:-1] + gray[2:, 1:-1] - 4 * gray[1:-1, 1:-1])) if min(im.size) > 2 else 0
        alpha = "A" in im.getbands() and im.getextrema()[-1][0] < 255
        return {"width": im.width, "height": im.height, "mode": im.mode,
                "has_transparency": alpha, "laplacian_variance_proxy": sharpness,
                "approval": "NEEDS_REVIEW", "multi_view_consistency": "NOT_TESTED",
                "background": "alpha supplied" if alpha else "unsegmented"}
