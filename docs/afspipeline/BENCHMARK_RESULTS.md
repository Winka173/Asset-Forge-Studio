# Benchmark evidence

No human-accepted adaptive art benchmark has completed. Two new real technical delivery paths completed; sample counts and rejected/interrupted attempts remain visible.

| New case (n=1 each) | End-to-end | Geometry stage | Blender | Delivered master | Interpretation |
|---|---:|---:|---:|---|---|
| TripoSG, supplied alpha castle, Maximum shape-only | 437.83 s | 65.61 s including worker/load | 352.83 s | 3,324,960 triangles; 265.08 MiB; 0 embedded images | Valid shape/export, not a textured-quality substitute |
| Castle text + tower style, named authored assembly, Maximum | 260.77 s | 7.30 s | 161.13 s | 39,604 triangles; 63.10 MiB; 12 embedded PBR images, 2048 authored maps | Technical/structural gates pass; no artistic acceptance |
| Roof-red material-only revision | 188.75 s | No inference or new geometry | One Blender job | Staged revision, 95 meshes; identical topology; maximum world vertex delta 0.0 m | Current game copy retained; native promotion test pending |

Castle interpretation/planning: 41.53 s CPU Qwen. Three-render Qwen review: 44.63 s CPU; actual observed subject castle, no severe visible defect. This remains uncalibrated inferred evidence, not a visual PASS. New native test also supplies frozen Art Bible/style context.

TripoSG peak allocated 6,675,701,760 bytes and reserved 8,061,452,288 bytes. Whole-device sampled peak 9,412 MiB (116 samples, includes desktop/other apps). Whole-machine RAM peaks 30.59 GiB for shape flow and 29.72 GiB for castle flow; these are not exclusive engine RAM. Qwen's external Ollama process is not included in the worker-subprocess RSS metric: a recorded zero means unavailable, not zero memory use.

Evidence: `../evidence/adaptive_triposg_real.json`, `adaptive_castle_real.json`, `adaptive_material_real.json`; actual before/after renders `adaptive_castle_before.png`, `adaptive_castle_after.png`. Negative test `adaptive_structure_rejection.json` deliberately removes a real tower mesh: valid GLB container, BLOCKED structure, export rejected, prior delivery unchanged. This exposed and fixed a real empty-node acceptance bug.

Historical engine samples: `../evidence/all_runs.json`; historical real Single/Batch quality parity: `../evidence/maximum_quality_comparison.json`; earlier actual castle output: `../evidence/castle_reference_3d.json`. These do not establish a calibrated artistic acceptance rate, Meshy equivalence or new-environment reliability.

Recent local castle attempts: v21 rejected after two concepts; v21b first concept rejected, second admitted, 3D explicitly interrupted for review; v21c analysis completed, concept explicitly interrupted. Do not count interruptions as a successful/failed model inference benchmark. New JSON evidence will distinguish technical delivery from human artistic acceptance.
