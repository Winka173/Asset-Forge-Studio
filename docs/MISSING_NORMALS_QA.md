# Neural GLB inspection without source normals

An actual TRELLIS v1 castle exposed an inspection stall after successful local
inference. The output has 634,688 vertices, 1,269,640 triangles and no glTF
`NORMAL` attributes. The API environment intentionally does not depend on SciPy.
Accessing `mesh.vertex_normals` selected Trimesh's no-SciPy fallback, which scans
all faces separately for each vertex. The isolated research inspector was
terminated after diagnosing that quadratic path; the completed neural output
was retained and reused.

`surface_diagnostics.py` now reads loaded normals directly when present. If
absent, it accumulates angle-weighted geometric normals using NumPy in bounded
65,536-face chunks, then normalizes each vertex sum. Time is linear in faces
and vertices; memory includes the per-vertex accumulator and bounded face
temporaries. There is no new dependency and no changes to the GLB, geometry,
materials, stored normals or generation configuration. The computed normals
exist only for diagnostics and are explicitly labelled **derived**.

The exact real neural file inspected in **1.75 seconds** after this change.
Its SHA-256 remained
`45cb98d6e1f6ab9c6287073e54eb90ddd6bf141e3c292f3556a2ee53ca8484d9`.
This is a measurement on this machine, not a universal latency guarantee.
The interrupted earlier inspection did not complete, so there is no invented
before/after speedup ratio.

Five surface tests pass, including independent small-mesh upstream normal
comparison, isolated/degenerate vertices, scale changes, actual GLB import
without `NORMAL`, and a guard that forbids calling the problematic property.
Loaded source normals still follow the original path. Nineteen related
geometry/texture/quality tests pass. Existing QA cache identities already hash
this validator, so changed measurements cannot silently reuse its old identity.

The native acceptance imports this actual million-triangle castle into an
isolated packaged Windows Library, performs selected-version reinspection,
checks the exact bundled validator hash, opens the real model and measurements,
closes/reopens Windows and verifies persistent metadata, zero generation jobs,
unchanged source and `not_reviewed` artistic status. No procedural stand-in,
new texture/PBR, artistic approval or game-delivery claim belongs to this test.

Evidence: [actual API inspection](evidence/missing_normals_actual_v0917.json),
`desktop/verify-missing-normals.mjs`, and the final native/build reports after
the mandatory Windows completion loop.
