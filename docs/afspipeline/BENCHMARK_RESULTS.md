# Benchmark evidence

No human-accepted adaptive art benchmark has completed. Two new real technical delivery paths completed; sample counts and rejected/interrupted attempts remain visible.

## Preserved tower baseline (2026-10-22)

Recovered the actual 2026-10-21 seed-43 tower result from the retained data-reset backup. Read-only verification: `python scripts/verify_tower_preservation.py`. `../evidence/tower_quality_preservation.json` binds the source PNG, original generation receipt, raw GLB and un-decimated `raw_master.npz` by SHA-256. Historical request: TRELLIS.2 community model revision `af44b45f2e35a493886929c6d786e563ec68364d`, seed 43, 24 steps, 1024 cascade, 4096 texture output. The actual exported GLB has 984,215 triangles and two embedded images; retained native geometry has 6,702,958 triangles. Density is inventory, not an artistic quality score. The user's exact preferred historical seed is not independently confirmed.

Reconstruction from a shape reference must retain the image-to-3D route. The authored castle profile is a separate limited structural workflow and must never replace source reconstruction or be described as equivalent neural art. Existing Maximum remains pinned at 32 steps/1024 cascade/4096 for TRELLIS.2; no speed-driven downgrade is authorized. No Meshy GLB or human-approved calibration set is available.

Fresh replay: `python scripts/verify_tower_replay.py`, run `.local/tower-replay/20261022T103810Z`, completed real inference, Blender, export/reimport and selective GLB delivery in 376.58 s. Inference 173.09 s, peak Torch allocated 3,447,986,688 bytes/reserved 3,760,193,536 bytes (not whole-device VRAM). `python scripts/compare_tower_native_master.py --replay .local/tower-replay/20261022T103810Z` verified exact array equality for vertices, faces, sparse PBR attributes and coordinates against the preserved seed-43 native master. Evidence: `tower_replay_real.json`, `tower_native_master_comparison.json`. Delivered GLB has 984,911 triangles and two embedded images. Its hash differs from the old GLB: remeshing/UV export is not claimed bitwise deterministic. Exact native-field equality is stronger than a density proxy but does not independently certify raster texture baking or all finishing quality.

The replay's direct legacy API request used no normalization height. Fixed metric benchmark renders consequently show the approximately 1 m tower small in a castle-sized camera frame. This is not an empty mesh; final bounds are measured and the interactive viewer fits them. Do not count these small benchmark renders as adequate visual art acceptance. Auto workflows still resolve their own explicit/provisional dimensions. Preserve fixed benchmark cameras instead of silently fitting competing models to different scales.

Measured replay resources: `tower_replay_resources.json`: 318 whole-device nvidia-smi samples, peak 6,266 MiB, peak utilization 99%. Whole-machine RAM peak 48,617,463,808 bytes during inference, worker tree RSS peak 23,522,455,552 bytes. Blender whole-machine peak 30,382,047,232 bytes, worker tree RSS peak 5,026,295,808 bytes. These scopes include desktop/system memory where stated; do not compare them to exclusive CUDA allocated counters as the same metric. Packaged Windows 0.9.1 viewer acceptance passed with a full-size interactive tower preview, screenshot `tower_native_viewer.png`; no new inference was triggered by viewing.

Windows 0.9.2 retained-tower verification: actual front/back/side/top/bottom and initial three-quarter screenshots are in `../evidence/tower_views_v092/`; viewer receipt `tower_native_viewer_v092.json`. These expose the real generated backside for review and preserve the same GLB/hash; camera changes do not regenerate or alter the asset. Render evidence is not a human-accepted backside quality score.

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
