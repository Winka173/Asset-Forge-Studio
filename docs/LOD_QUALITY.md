# Measured LOD geometry retention

The Blender stage keeps the master and existing ratios/resolutions unchanged. Each derived LOD receives a geometry-only measurement in the same world coordinate system. Source and output files stay immutable.

The validator samples 8,192 points from triangle surfaces with probability proportional to triangle area, using seed 43. It queries the nearest actual triangle surface through Blender BVH in both directions. Reports retain mean, RMS, p95 and maximum observed distances, geometric face-normal angles, actual triangle counts, validator SHA-256, sample count and seed. Compact evidence is attached to the processed candidate for Library and Production. Detailed reports remain with the Blender job.

The UI normalizes distances by the master's bounding diagonal. It does not label these percentages as quality scores. The maximum is the largest sampled distance, not a guaranteed global Hausdorff bound. Small features can escape sampling. Face-normal differences do not validate texture normals, UVs, bake coverage, silhouette, physical scale or artistic fidelity. No new automatic pass/fail threshold or polygon budget is introduced.

Real tower evidence is recorded in `evidence/lod_quality_real_v095.json`. The test uses the retained generated tower through the actual API/CPU Blender queue, reopens exports and verifies unchanged source hashes. `tests/test_lod_quality.py` checks identical, coarsened and deliberately displaced real Blender geometry. Packaged native acceptance is implemented in `desktop/verify-lod-quality.mjs`.

Normal/AO baking remains a research path. `scripts/verify_lod_bake_research.py` produced real 4K maps and common-camera before/after renders, but ray coverage, UV overlap and visual improvement have not been established. AO stays separate; no fabricated roughness/metalness or emission is added. Production integration must validate those limits before enabling the feature.
