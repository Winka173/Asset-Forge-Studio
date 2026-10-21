# ASSET FORGE STUDIO — QUALITY-FIRST UPGRADE V2

> APPEND this document to the existing `Asset_Forge_Studio_Claude_Code_Master_Prompt.md`. Claude Code remains lead. This upgrade takes precedence where conflicting. Respond and report in Vietnamese. Goal: output should approach the user's Meshy 7.1 Archer Tower golden model while running locally without paid per-generation services. **No unvalidated promise of parity**.

## 0. Hard product priorities
1. Quality before throughput and UI breadth. MVP is successful only when it produces, diagnoses, and iteratively improves a real 3D asset that can be compared against the Meshy golden reference.
2. Never equate more triangles, larger textures or more inference steps with better quality; evaluate meaningful geometry, PBR fidelity, silhouette, coherent rear surfaces and Unity gameplay-camera rendering.
3. Build the **quality loop** first and postpone broad 349-asset batch generation, extra dashboard polish and packaging until validated.
4. User controls installation/download of models; never call paid APIs or third-party cloud without explicit authorization. Respect weight and output commercial licenses.
5. Process different AI model workers **sequentially** on a 16 GB GPU; maintain isolated environments and release GPU memory after every inference.

## 1. Golden Benchmark & scoring dataset (P0)
Create a local `benchmarks/archer_tower_t3/` with:
- Approved concept image, exported Meshy 7.1 golden GLB (user supplies), material files, metadata and checksum.
- Locked camera views: front 3/4, side, back, top, isometric gameplay at target mobile and 1440p PC resolutions, fixed lighting/environment/exposure, scale reference next to 1.8m character and wall.
- Benchmark outputs from each local engine with identical reference and explicitly recorded preprocessing, inference steps, seed, triangle count, duration, peak VRAM and failure modes.
- Side-by-side synchronized turntables, normal/depth/silhouette/texture overlays; do not use synthetic or guessed 'Unity screenshot'.
- Review rubric (scored separately, not a magic weighted quality claim): silhouette/proportions; roof and crenellation geometry; front-back coherence; texture/PBR consistency; key details such as crystal and balcony; defects/holes; UV quality; camera-scale appearance; artist judgment.
- Optional machine similarity scores (multi-view LPIPS/SSIM/CLIP or comparable) only when implemented correctly, disclosed as proxies not objective artistic truth. Human approval mandatory. No declared 'within 10%' without real human rating + measured definition.

## 2. Multi-candidate tournament (P0)
- For each approved concept, generate configurable N seeds per supported engine, initially N=2 then N=4 only when resource budget allows.
- Render at fixed camera and lighting; reject empty, broken, incomplete, upside-down, dimensionally impossible or malformed meshes before judging appearance.
- Score per dimension, preserve ALL seeds/results in immutable version history; user reviews a contact sheet and chooses best candidate.
- Allow a second round using the best seed/variant only if the engine actually supports meaningful seed/conditioning reuse; no fake iterative refinement promises.
- Track GPU-hours, storage and estimated electricity; queue, resumability, cleanup and artifacts retention policy.

## 3. Image-conditioning studio (P0)
- User-supplied approved image as primary source; foreground segmentation/masking, background consistency, crop, perspective normalization, neutral shadow/light separation, and sharpness checks.
- Multi-view **only with actual corresponding consistent inputs**; an independently invented back view is NOT ground truth. Provide side/back concept generation through optional user-approved image model, show cross-view inconsistencies and require review.
- If model accepts only one image, use validated best front-three-quarter image. Do NOT concatenate collages and pretend the model can read multiple angles.
- Provide key geometric constraints in the manifest (height, base footprint, camera yaw, symmetry, exact number of balconies, door orientation, separable parts) even if current generator cannot enforce them; enforce afterward in Blender where practical.
- Per-game style 'Golden Reference' gallery, explicit color/material palette, camera-angle sheets and style-drift warnings.

## 4. Engines and compatibility (P0)
- Implement adapter test matrix: TripoSG, Stable Fast 3D, Hunyuan3D 2.1 shape, and optionally SPAR3D if license/hardware validated. Audit 2026-relevant maintained engines before installing; prefer working real CUDA stack over list of unsupported fashionable models.
- 16GB GPU: avoid promising native Hunyuan3D 2.1 Paint (official stated 21GB), TRELLIS.2 official 24GB; test low-memory offload only if concrete supported builds exist. Prefer CPU/offload alternatives for texture where benchmark proves quality, and make texture generation independently replaceable.
- Each adapter declares verified supported prompt/image modalities, output geometry versus texture maps, CUDA and Torch builds, VRAM actually measured, current license, commercial terms, output restrictions, and reproducibility.
- Do not assume public Tripo web service quality matches open-source TripoSG.

## 5. High-fidelity surface pipeline (P0)
- Model generation and material reconstruction are separate stages. Preserve and version: raw geometry; cleaned mesh; UV; base-color; normal; metallic; roughness; AO; emissive; optional opacity/masks.
- Build automated multi-camera texture projection/texture transfer from approved references when legally permitted. Distinguish unseen sides (inpaint/provisional) from source-faithful surfaces. Seam painting, dilation, UV island margins and mipmaps, color-space tags, texel-density targets.
- Blender PBR artist presets for original Runavelle limestone, chestnut oak, midnight-blue slate, aged bronze, navy-gold banners, cyan mana. No simple saturation/contrast hack masquerading as 'quality'.
- High-res upscaling only after geometry and UV are valid; 4K images do not recover nonexistent geometric details. Use 2K/4K selectively based on screen-space and atlas budgets.
- Material QA: albedo under neutral light, highlights/roughness/metallic plausibility, remove baked directional shadows from base color where possible.

## 6. Architectural reconstruction & modular precision (P0)
- Treat AI generated meshes as visual input, NOT mechanically reliable footprints. Blender procedure builds exact foundation, walls, tower sockets, gates, wall pieces and projectile spawn positions with metric dimensions and connector tests.
- For Runavelle golden Archer Tower: keep accepted shape, but reconstruct balcony railing, roof tiles, crenellations, door openings, crystal housing, foundations or other parts as real geometry when image-to-3D fails. Preserve original source for rollback.
- Use semantically separated components (base, wall, roof, flag, crystal, sockets, colliders), versioned .blend and generator scripts. Maintain constraints for later T1/T2/T3 variants.
- Prepare damage/breach modular variants and effects separately, rather than expecting a single AI image-to-3D output to encode gameplay mechanics.

## 7. Smart mesh optimization rather than blind decimation (P1)
- Immutable master at native resolution. Retopology/manual intervention when necessary; bake geometric detail to maps before simplification. Generate LOD0–LOD3 based on camera screen coverage and measured image differences. Preserve silhouettes of roof, horns, weapons, flags and turrets.
- Triangle budget per item from scene benchmark, not arbitrary 200k or 2m. Build simple colliders and physics proxy; do not use millions of master triangles for collisions.
- Profile full representative sieges: multiple towers, walls, Castle, units, 1–2 bosses, light and VFX; record batches, draw calls, vertex load, texture VRAM and overdraw.

## 8. Character / animation special lane (P1)
- Separate route for characters: body architecture, pose, hands/feet count, skinning topology, rig skeleton/compatibility, detachable gear, retargeting, animation QA, attack sockets. AI shape alone does not mean animation-ready.
- Use Blender/auto-rig where supported. Validate idle, locomotion, attack, hit, death, dodge, cast. Explicit FAIL instead of exporting unusable skinned assets.
- For stylized mobile isometric scenes, combat silhouettes and animations take priority over high hidden detail.

## 9. Spectacle pipeline (P1)
- A dedicated Unity URP magic-VFX workflow: Shader Graph, particle/mesh emitters, flipbooks, beams, projectile trails, camera shake/hit stop/audio hooks, scalable quality tiers.
- User goal: huge satisfying magic, but keep General, wall breaches, boss telegraphs and UI visible. Adaptive emitter counts, maximum screen occupancy/opacity and GPU load; benchmark worst-case overlap.
- Do not claim static GLB generation alone satisfies animated ultimate attacks.

## 10. Quality Review UI (P0)
- Comparison view: concept, Meshy golden GLB, local raw GLBs per engine, optimized model, final Unity render; synchronized orbit/zoom/lighting.
- Pinpoint defects on 3D view, create human correction tickets 'roof merged', 'stairs distorted', 'back blank', 'materials muddy', 'crystal missing'.
- Guided repair options: mesh part separation, geometry replacement via Blender kit, texture reprojection, manual sculpt; mark whether each is automated, requires manual action or requires regeneration.
- Pass gates: correct 360-degree geometry, usable material assets, metric footprint, style consistency, real Unity import, human approval. Strict status Not Tested/Failed/Needs Review/Approved.

## 11. Execution roadmap
**Gate A**: working UI import and dual Meshy-vs-local comparison with fixed view renders (no AI engine yet).
**Gate B**: install/test two compatible local engines, generate 2 seeds each for approved tower, compare and save provenance.
**Gate C**: Blender repairs + separate material/PBR pass; demonstrate visible improvements in same-angle captures without cherry-picked lighting.
**Gate D**: export Unity + real screenshots on mobile-compatible and 1440p settings, measure practical game camera quality and performance.
**Gate E**: extend to 1 General + 1 enemy + 1 castle component. Only then batch manufacturing and catalog expansion.

For each gate deliver precise commands, tested outputs, actual screenshots/files, metrics and an honest 'How far from Meshy?' human side-by-side scorecard. If model does poorly, report it; do not hide differences or claim equal quality. Ask user for approval when visual judgment is needed. Build the best feasible local pipeline, not unverifiable marketing claims.
