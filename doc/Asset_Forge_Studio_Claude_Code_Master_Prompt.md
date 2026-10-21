# ASSET FORGE STUDIO — MASTER IMPLEMENTATION PROMPT FOR CLAUDE CODE

## 0. Role and mission
You are Claude Code, the lead engineer and technical art director. Build a **LOCAL-FIRST, FREE-PER-GENERATION, MULTI-GAME AI ASSET FACTORY** called **Asset Forge Studio** for a solo developer creating Unity games. This is a real software implementation request, not merely an architecture proposal. Work incrementally, commit verified changes, and clearly distinguish working features from stubs and unavailable dependencies. Reply and report in Vietnamese. Do not purchase services, call paid APIs, or upload user content without explicit consent.

User environment to audit rather than assume: Windows 11, RTX 5070 Ti (typically 16 GB VRAM; detect actual), 64 GB RAM, Blender 4.5, Unity 6 / Unity URP, VS Code, Python, optional WSL2/Docker. Support future more powerful GPUs. The system must work with no running cloud provider; optional adapters for paid cloud services can be added later but are disabled by default. Protect existing game repositories; build this as its own project.

## 1. Primary user experience
A beautiful local web UI (React + TypeScript, modern dark theme, drag-drop, keyboard-friendly) with these screens:
1. Dashboard: queued/completed/failed jobs, GPUs, VRAM, installed model engines, storage, time and metadata.
2. Game Library: create projects (Runavelle, Aetherward, Forgebound, Machine Brigade and arbitrary games); each with Art Bible, style presets, color palette, scale (1 unit = 1 meter for Unity), camera, license policy, naming standards and game-specific constraints.
3. Asset Catalog: category, model name/id, family/tier/variant, target dimensions (W×D×H meters), reference image(s), source prompt, generation engine, seed, settings, lineage, exports, acceptance status; search, batch select and sort.
4. Concept Studio: text brief, image upload, image crop/background removal, reference library, multi-view reference management, approval checkpoint. DO NOT pretend local 3D image generators are general-purpose text-to-3D. A separate optional locally-running text-to-image backend may be connected only if installed and tested. Without it, support user-provided concept images and templated prompt export.
5. 3D Lab: select supported image-to-3D engine, choose presets Quality/Balanced/Fast, set seed, resolution, memory guard, optional mask; enqueue generation, show status/logs, view mesh in WebGL, inspect back/side/top, wireframe, UVs, triangle counts, texture channels, dimensions and manifold warnings.
6. Asset Workshop: non-destructive scale/orient/pivot correction, mesh cleaning, separation, decimation/retopology tools, normal/AO baking when valid, UV, texture maps, PBR correction, LOD generation, collision geometry and optional modular segmentation. Blender headless operations are versioned and repeatable; manual Blender editing is supported. **Do not promise that aggressive decimation always preserves details; validate and bake where appropriate.**
7. Validation Studio: side-by-side source/LOD/render preview, camera-scale silhouette test, intersection and disconnected-geometry checks, normal orientation, texture seams, UV overlap when undesirable, missing maps, dimensions/tolerances, skeletal/rig validity, naming, license metadata, Unity import report and performance budget. Keep explicit status: PASS / FAIL / NEEDS_REVIEW / NOT_TESTED.
8. Export Center: GLB/glTF, FBX via Blender where supported, source .blend, OBJ if requested, PBR texture maps, LODs, metadata manifest, preview PNGs, optional Unity prefab/package pipeline. Never claim a Unity scene screenshot without running Unity.
9. Batch Factory: CSV/JSON manifest import (including 349-asset style catalogs); concurrency and GPU memory checks; each item independent; checkpoints, cancel/resume/retry, run history; no automatic mass generation until sample approval.

## 2. Engine adapter architecture
Define an interface with: `id`, `version`, `license`, `capabilities`, `input_modalities`, `output_formats`, `min_vram_gb`, `installed`, `probe()`, `estimate(job)`, `generate(job, progress)`, `cancel(job)`, `verify_outputs()`.
- TripoSG (official or trusted source, image-to-shape; verify Python/CUDA compatibility and model/license before installation). Repo reference https://github.com/VAST-AI-Research/TripoSG — check whether URL exists; do not assume forks are official.
- Stable Fast 3D (Stability-AI/stable-fast-3d): image-to-mesh, low VRAM candidate. Community License and commercial registration/revenue terms require user review.
- Hunyuan3D-2.1 shape: default only shape on 16 GB; its documented texture backend requires ~21 GB; do not promise native texture on 16 GB; provide CPU-offload/low-VRAM alternatives only if demonstrated by successful test. Review Tencent-specific license.
- Optional SPAR3D image-to-3D (Stability AI; confirm current repo/API/license).
- Optional TRELLIS.2 via more powerful local GPU or validated optimized community fork only after separate opt-in. The official ≥24 GB Linux prerequisite does not fit RTX 5070 Ti 16 GB.
- Local image generation and upscaling/backdrop modules are optional adapters, not dependencies; no mandatory ComfyUI. User explicitly prefers a clean local app and no mandatory ComfyUI.
Use **capability detection**, not hallucinated support. Track provenance and URL/revision for each installed model.

## 3. Technical architecture
Prefer a pragmatic local stack: React + Vite + TypeScript frontend; Python FastAPI backend; SQLite *for this new standalone application only* or JSON-based metadata if simpler—choose and justify; local filesystem for binary assets; Python worker subprocesses with bounded GPU job concurrency; Blender 4.5 headless via `blender -b --python`; optional Electron/Tauri desktop packaging after MVP. Use local-only `127.0.0.1` by default with explicit controls if exposed to LAN.
Use reproducible Python environments per incompatible model (`uv` or venv/conda), not one fragile global environment; detect Windows vs WSL2; document CUDA, Torch, Python version pairings, compilation prerequisites, disk footprint and rollback. Never silently modify unrelated Python/CUDA installations. Dependency/version lock and license inventory mandatory.
Architect folders: `apps/web`, `apps/api`, `workers`, `engines/<adapter>`, `pipelines/blender`, `pipelines/unity`, `schemas`, `tests`, `docs`, `data/projects/<slug>/assets/<asset_id>/versions/<version_id>`.
Job state machine: DRAFT -> REFERENCES_READY -> QUEUED -> RUNNING -> GENERATED -> POSTPROCESSING -> VALIDATING -> REVIEW_REQUIRED -> APPROVED -> EXPORTED; additional FAILED/CANCELLED/BLOCKED with actionable error.
Store immutable generation provenance: all prompt variants, model revision, seed, source images (checksum), intermediate .glb/.obj, final .glb/.fbx, texture maps, Blender scripts/revisions, Unity verification status. Support inspectable edits instead of destructive overwrites.

## 4. Production quality requirements
User wants premium, visually satisfying, spectacular assets and spell effects—but prioritize form language, silhouette, materials, proportions, animation and game camera rather than only polygon count. Use independent high-poly master and optimized LOD. Mesh budgeting is adaptive per type, screen size, performance test, and platform, not a forced 200k cap or requirement for 2M polygons.
- Asset source may be hundreds of thousands or millions of triangles if genuinely useful and editable.
- Produce mobile/PC 1440p LODs from master with bake and test. Make measurable silhouette error/normal error/image diff targets configurable rather than invented fixed thresholds.
- Separate material components into PBR channels (base color, metallic, roughness, normal, AO, emissive) when available and valid; don't invent physically inaccurate maps.
- Do not promise text/image-to-3D will faithfully yield fully rigged/animated humans, production-perfect topology, multi-part walls, or exact dimensions. For complex characters, have a rigging/retopology/manual review step and reusable game-standard skeleton; adapters may connect optional auto-riggers.
- For repeatable modular structures, prioritize dimensionally precise Blender procedural construction. Use generated meshes as aesthetic reference or detailed modules, not as guaranteed dimensionally precise sockets.
- Dedicated VFX generator/assembler for magic is a *separate pipeline*, with meshes, flipbooks, textures, Shader Graph/VFX Graph recipes, pooled prefabs and bounded overdraw. AI 3D alone cannot create all magic gameplay FX.
- Never substitute a screenshot/mockup for 3D mesh or Unity runtime evidence.

## 5. Multi-game art presets
**Runavelle:** original premium painterly stylized magical medieval kingdom; ivory limestone, chestnut oak, midnight blue slate, bronze, navy/gold banners, cyan mana glow; day warm/night epic. Use approved Archer Tower T3 GLB as *style reference*, not as a proprietary model to copy for every new building. One Unity unit = one meter. Castle/House/Mana Well/Wall-Gate/Archer Tower/Magic Tower/Barracks/Magic Shrine remain 8 current base types, with tiers/branches. New future architecture belongs in separate FUTURE category until explicitly enabled. Assign actual W×D×H, nominal footprint, exact connection points and visibility budget via manifest, signed off after Unity camera preview; do not blindly assume previous suggested scales are repo ground truth. Generals, 12 unit families, enemy factions, boss monsters, biomes. Visual delight from upgrades, magic and siege, but quality tier on mobile.
**Aetherward:** Ravenswatch-inspired original dark painterly fantasy, adult hero silhouettes, mystical Aether Crystal, dynamic party combat; no fixed 12-slot hero towers; six hero party with move/attack animation, dark mythic enemies, readable oversized elemental VFX. Distinct palette from Runavelle.
**Forgebound:** original premium arcane forge fantasy; Backpack Battles is a UX/readability reference only; modular weapon frames/cores/modifiers/runes, Forge Board and workshop, side-view battle, bold rune VFX. Distinct palette and technical requirements.
**Machine Brigade / other games:** user-definable preset; preserve each repo's existing art conventions and avoid auto-applying fantasy materials to modern military assets.

## 6. Exact first MVP milestone
Build a working end-to-end local app before breadth:
1. Hardware/environment audit: report GPU VRAM, OS, WSL2 status, Python/Blender availability and disk headroom.
2. Create project `Runavelle`, asset record `ARCHER_TOWER_T3`, load its existing concept PNG and exported GLB when user places them in import area.
3. Preview imported GLB, show triangles, meshes, materials, dimensions, full rotation, and screenshots via a real 3D viewer.
4. Implement ONE validated local image-to-3D backend that fits detected hardware (prefer Stable Fast 3D for reliability, evaluate TripoSG).
5. Run one actual generation from a permitted input reference (do not auto-spend money or upload to cloud); save generation metadata and source files.
6. Blender headless normalization + generate first LOD + simple collider + preview render + QA report.
7. Export GLB, source .blend, PBR maps where present, metadata JSON; test load in Blender, and Unity if editor is accessible. Clearly label any unverified Unity import.
8. Add queue, stop/retry, history, preset management and a second game profile.
9. Only then integrate more engines, texture pipelines, batch export and VFX assistant.

## 7. License, security and cost
Track each model repository license, weights license, dependencies, generated outputs, commercial use rights, citations/attribution obligations, and source provenance. Commercial game publishing is a requirement: block or warn for uncertain permissions. Stability AI community license has separate commercial conditions; evaluate current official text. Local inference avoids per-generation API credits, **not** GPU/electricity/storage costs or third-party model-license conditions.
No hidden telemetry, network binding, paid calls, cloud inference or repo commits without user approval. Model downloads require explicit confirmation with estimated disk size and source. Validate uploads; guard archive traversal/path injection and subprocess arguments; sandbox risky converters. Do not store secrets in project assets.

## 8. Deliverables and acceptance
- Running developer launch scripts for Windows/WSL2; offline inference after initial download; setup README and troubleshooting guide.
- README; architecture; engine compatibility; art/style bible schema; asset manifest schema; licensing inventory; QA report; tests and demo instructions.
- At least one **real, successful** GLB import and 3D local generation proof on compatible hardware before claiming a working generator.
- Unit tests for job state transitions, artifact paths, manifest import, dimensions, Blender pipeline, and cancel/retry.
- Explicit checks: source does not overwrite current game assets; outputs can be re-opened; 3D viewer reads exported files; no hidden credit use; no missing textures.
- Actual evidence (generated files, logs, screenshots, profiling when available). Never fabricate benchmarks, hardware results or Unity screenshots.

## 9. Execution style
Start immediately with repo scaffold and first usable vertical slice. Be autonomous with sensible defaults, but ask before expensive model downloads, major data deletion, paid services, security-sensitive actions or changes to game repositories. If required source files aren't present, implement importer and provide exact placement instructions. Work in small verified phases. Save progress in `docs/PROGRESS.md` with DONE/FAILED/BLOCKED, logs and next action. Prefer local-first functionality and honest quality reporting over large speculative architecture.

**Ultimate goal:** a polished reusable **Asset Forge Studio** that produces, inspects, improves, versions and exports consistent premium assets for many indie games, without ongoing per-model API fees, with Blender/Unity production quality and scalable GPU/model adapters.
