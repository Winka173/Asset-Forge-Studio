ASSET FORGE STUDIO — UNIVERSAL GAME ASSET PLATFORM
Claude Code implementation master prompt — V2 reviewed | Windows + Unity + Unreal | Local-first
Context: This is a NEW instruction set covering every requirement discussed since the request to generate maps and other game assets. The previous agent has NOT received those requirements. Read and apply this document as a single cohesive expansion specification. Continue the EXISTING Asset Forge Studio (AFS) repository; do not scaffold a replacement application.

0. Mission and non-negotiable principles
Build AFS into a modular local-first Windows desktop game asset production platform: from text, reference images, video, structured manifests, or existing game assets to editable, versioned, validated asset packages usable in Unity and Unreal Engine. Support the existing 3D model workflow and extend to maps/levels, environments, characters, rigging, animation/motion, VFX, materials, sprites/2D, UI, audio, cinematics, and modular equipment/props. Preserve the current product's Single Asset Studio, Batch Studio, Quality Lock, GPU scheduler, Library, project Art Bibles, and Windows desktop workflow. Do not pretend a feature is complete because it renders a preview: produce real importable artifacts, with honest status if blocked.

Hard requirements:
1. Audit the repository, available runtimes, existing AI engines, installed MCP servers, licenses and actual Windows build status before changes. Do not assume any proposed integration is already installed or working.
2. Preserve working pipelines, data, prompts, golden references, and approved masters. No broad rewrite, mass rename, or destructive migration.
3. Local-first, zero mandatory per-generation API cost. Never silently call a paid cloud endpoint, consume API credits, or require a Claude subscription for normal end-user generation. Claude Code is used to DEVELOP the app, not as an unavoidable production runtime. Provide local LLM planning with deterministic schema-based fallback. Flag electricity, hardware, disk, optional software licensing and developer-agent subscription as separate costs.
4. License-aware: source code licenses, model-weight licenses, commercial asset rights, redistribution restrictions and game engine licensing are distinct. Verify each; mark unknown/research-only as blocked for commercial preset until reviewed. Do not claim all open weights are commercially usable.
5. 16 GB VRAM baseline: Windows 11, RTX 5070 Ti 16 GB VRAM, 64 GB RAM. Do not assume 24 GB models run natively. Benchmark offload/quantization only as opt-in experimental profiles with measured quality/performance; never silently downgrade Quality Lock.
6. Quality parity: Batch is Single Asset quality pipeline × N. The scheduler changes when jobs run, never the effective generation configuration. Pin model/checkpoint hashes, seeds, resolutions, steps, candidate counts, texture/bake settings and QA rules. Out-of-memory means wait/cleanup/block, not silent lower-quality fallback.
7. Windows desktop first: continue the existing Tauri 2 (or audited current desktop implementation) + React/TypeScript + Python backend architecture. After EACH completed feature or significant fix, run tests, produce a NEW Windows desktop production build, launch it and smoke-test the changed feature when Windows GUI is available. Preserve last known-good build. If build/launch is impossible in the execution environment, report BLOCKED with evidence; never fabricate success. Put this rule in CLAUDE.md.
8. Scope is ambitious: implement by vertical slices with working outputs, not dozens of fake tabs. A module is marked available only after real inference/procedural processing, export and target-engine import tests succeed. All other modules must show clearly labeled Planned/Experimental/Unavailable statuses, not fake Generate buttons.
1. Product structure and UX
Keep the simple primary navigation:
- Projects: game-specific Art Bible, target engine(s), units, palettes, golden references, style constraints, quality presets and reusable asset families.
- Create Studio: Single / Batch; select asset type (3D Model, Character, Rig/Animation, Map/Environment, VFX, Material, Sprite/2D, UI, Audio, Cinematic). Input panel adapts to type; show expected actual output and estimated dependencies; separate Analyze/Plan, Generate, Review, Approve and Export.
- Results/Review: 3D viewer and engine-specific preview; multiple candidates, comparison, visual/technical QA, manual approval, version history and regeneration of selected stages.
- Library: filter by game, asset type, tags, state, source, engine, versions; maintain immutable approved master and derivative packages.
- Jobs: persistent stage-level DAG, GPU/CPU resources, resume/retry/cancel, honest progress, logs and failure causes.
- Integrations/Settings: installed engines, MCP connections, Unity/Unreal/Blender paths, licenses, models, storage, export profiles and benchmark dashboard.
The UI must not overwhelm users with CUDA/seed/LOD settings by default. Keep an expandable Advanced section. Every interactive control must be functional. Allow users to edit parsed batch manifests before spending GPU time. Support prompt-to-many-assets, import JSON/CSV/Markdown manifests, style locking, family/dependency relationships and selective retry/export.
2. Unified asset contract and orchestration
Design a typed, versioned Asset Manifest with at least:
- project_id, asset_id, asset_type, family_id, version, status, target_engines, units, coordinate_system;
- input text/reference files/hashes, Art Bible and golden reference IDs;
- effective generation config: engine/version/checkpoint/hash/seed/inference settings, precision, candidate count, quality preset, QA profile;
- dependency DAG, stage checkpoints, source master, derivatives, license provenance, toolchain versions;
- expected vs actual output files with hashes, import-test reports and preview artifacts;
- engine-specific metadata (pivots, sockets, collision, terrain layers, retarget profiles, particle parameters, etc.).
Use an internal canonical representation wherever practical (mesh + PBR + scene graph + procedural metadata + timelines), but do NOT pretend one universal format captures all Unity/Unreal-native features. Each target needs a native importer/assembler. Maintain deterministic transforms/units and explicit coordinate conversion. Version schemas, migrations and rollback; store user data outside application install/build folders. Never overwrite approved masters.

Provide a typed plugin/adapter API for analyze -> plan -> prepare -> generate -> postprocess -> validate -> review -> export -> import_test. Modules can contribute stages without coupling the entire app to one engine. Separate lightweight CPU/I/O jobs from heavyweight GPU tasks; use one shared resource scheduler with default one heavy GPU job at a time. Blender GPU bake/render shares that queue. Keep model processes/environments isolated and load weights lazily. Preserve checkpoints across restart and Windows app rebuild.
3. Asset types — REQUIRED input / process / output contracts
3.1 Static 3D models / modular props / equipment
Inputs: text, image(s), multi-view references, dimensions, intended usage, style, existing mesh, desired attachment sockets, LOD/texture quality.
Process: concept approval if required; local image-to-3D or procedural generation; candidate tournament; mesh cleanup, UV, PBR, baking, LOD, collider/pivot/sockets, validation.
Outputs: immutable high-quality master (.blend and/or GLB as actually generated), optimized GLB/FBX, textures/maps, LOD meshes, thumbnails, manifest, Unity prefabs and Unreal import assets generated through real Editor tooling. Do not fabricate PBR channels or LODs.
3.2 Characters / creatures / monsters
Inputs: text, concept/multi-view, body proportions, topology goals, outfit/equipment, expression/face requirements, target rig, engine avatar/skeleton profile.
Process: generate/repair geometry; topology suitability checks; separate rigging and skinning stage; attachment sockets; optional facial rig; preview poses; test deformation.
Outputs: source mesh, PBR textures, rigged FBX/glTF when valid, skeleton and skin weights, sockets, retarget profile, Unity humanoid/generic avatar as appropriate and Unreal skeletal mesh/skeleton. Unrigged mesh must NEVER be mislabeled rigged.
3.3 Animation / motion
Inputs: existing compatible rig/skeleton, text action specification, video/mocap/BVH, timing, root-motion policy, reference clips.
Process: motion estimation or generation where available; retargeting; contact/foot sliding/penetration QA; looping, event markers and blending checks.
Outputs: FBX/BVH or other supported motion source, clips, root-motion and event metadata, Unity AnimationClips/Animator integration and Unreal AnimSequences/retarget assets via Editor. If no viable free local generator exists, provide an honest import/retarget pipeline first, not a fake text-to-animation claim.
3.4 Maps / levels / terrain
Inputs: master prompt, world dimensions/units, top-down sketch, heightmap, biome maps, reference art, camera/gameplay genre, lanes, navigation/build zones, spawn points, landmarks, seed, performance budget.
Process: use a deterministic, schema-validated World Plan with editable terrain masks, roads/rivers, gameplay layout, prop dependency list, reusable procedural generators, scatter rules, nav/collision, map assembly, validation. Use deterministic procedural terrain/layout first where AI map generation is not reliable. Reuse Library assets; generate missing props as sub-jobs only with approval/budget controls.
Outputs: source heightmaps/masks (appropriate bit depth), terrain layers/materials, mesh props, placement/scene graph JSON, roads/rivers, biome/scatter rules, gameplay metadata, overview/minimap and actual Unity Scene + TerrainData + prefabs and actual Unreal Level + Landscape/Actors/PCG setup produced and saved by respective Editor adapters. A single GLB is NOT a finished game level; do not rename files to .unity/.umap without Editor serialization. Validate playable navigation, spawn/build areas and scale where project context permits.
3.5 Environments / foliage / biome kits
Inputs: biome prompt, season, palette, density, modular rules, environmental references, platform budget.
Outputs: modular trees/rocks/cliffs/roads/ruins, material variants, terrain/foliage masks, instancing/scatter definitions, collision/LOD and native Unity/Unreal placement assets. Ensure deterministic seeds and editable scatter parameters.
3.6 VFX / spell effects
Inputs: effect description, style references, duration, loop behavior, element, event timeline, camera distance, performance budget, target render pipeline.
Process: create or source procedural flipbooks, noise/flow textures, meshes, gradients, shader graphs/parameters and particle timing; assemble native effects with engine-specific adapters.
Outputs: RGBA flipbooks, masks, VFX meshes, shader parameters, preview, Unity VFX Graph or Particle System prefab (pipeline-dependent), Unreal Niagara System and events/parameters if actually created. A rendered video alone does NOT count as real-time VFX. Flag unsupported node/material translations.
3.7 Materials / shaders
Inputs: text/image references, surface properties, tile size, target PBR workflow, desired engine pipelines.
Outputs: verified base color, normal, roughness/metallic, AO/height when generated, tiling metadata, material graphs/instances via native adapters. Handle color space, normal conventions and channel packing per engine; do not invent missing maps.
3.8 Sprites / 2D animations / UI
Inputs: text/concept, style, dimensions, transparent background, frame list, layout/wireframe, DPI, typography constraints.
Outputs: transparent PNG/WebP as appropriate, spritesheets/atlas + frame metadata, Unity sprite importer and Unreal Paper2D or UMG resources when supported, UI layout definitions and editable design sources when available. A flat image alone is not an editable UMG/UI Toolkit screen. Require consistent character silhouette and frame registration for sprite animations.
3.9 Audio / music
Inputs: text description, reference audio, duration, BPM/loop boundaries, game event, language, license constraints.
Outputs: WAV/OGG, clean loop points, loudness/peak metadata, source attribution and import settings. Only enable local generative audio after validating model rights and performance. Avoid claiming voices/music are cleared for commercial use without verified terms.
3.10 Cinematics
Inputs: storyboard, dialogue/script, existing character rigs, animation, cameras, timing, lighting, scene references.
Outputs: editable camera/animation timelines, shot manifests, source audio and native Unity Timeline / Unreal Sequencer setup through Editor tooling where available. A pre-rendered MP4 may be a preview, not the sole editable cinematic deliverable.

For every module define supported/unsupported input modalities, file formats, fidelity levels, QA, licenses and engine compatibility. If a local generation model is unavailable, provide a genuine procedural/import-based capability with transparent limitations.
4. Unity and Unreal — actual engine integration
Unity: support a configurable supported Editor version and render pipeline (URP/HDRP/Built-in where explicitly tested). Build an AFS Unity Editor package/importer to import meshes/textures, construct materials, prefabs, LODGroups, colliders, avatars, animation clips, terrain, scenes, particle/VFX assets and test scenes as relevant. Expose Editor batchmode automation with structured logs and import validation. Handle centimeters/meters, Y-up, normals, tangent space, pivots, transparency, shader differences and texture channel packing. Report unsupported conversions.

Unreal: support a configurable verified Unreal Engine version. Build an AFS Unreal Editor plugin or Python/Editor Utility integration to import source assets and create real UAssets/Blueprint/Level/Landscape/Niagara/animation resources where supported. Use Unreal Editor to save .umap and .uasset; do not attempt fake raw serialization. Validate transforms, Z-up conversion, centimeters, collision, Nanite eligibility, material instances, skeletal rigs, LODs and shader compatibility. Allow Unreal support to remain experimental until actual end-to-end import tests pass.

Provide a Validation Project for each engine with consistent lighting/camera/test assets, automated import checks, preview screenshots and metrics. Differentiate source_generated, exported, imported, engine_validated, human_approved, game_ready. Game ready requires explicit target-platform criteria, not merely a successful file export.
5. MCP integrations: audit, connect, isolate
Evaluate these candidates using their official repositories, current maintenance status, compatibility, permissions and licenses (do not assume installed):
- Blender MCP: https://github.com/ahujasid/blender-mcp
- Unity MCP: https://github.com/CoplayDev/unity-mcp
- Unreal MCP candidate: https://github.com/DeVoe09/UnrealMCP (verify current project status and choose an actively maintained alternative if justified).
MCP is primarily for Claude Code/agent-assisted inspection and editing, not a mandatory runtime dependency for every user batch job. For reliable bulk production use Blender Python headless, Unity Editor batchmode scripts and Unreal Editor Python/Editor Utility automation. Build an optional AFS MCP server exposing scoped tools for projects, manifests, jobs, QA, review and export. Make all connections opt-in, localhost-only or otherwise authenticated, least privilege; restrict arbitrary script execution, file access and remote execution. Track Connected vs Installed vs Tested separately. App must still run without MCP or Claude Code.
6. Local AI engines and tools — evaluate, do not blindly install
Audit existing adapters before adding candidates:
- 3D geometry: TripoSG, Stable Fast 3D, Hunyuan3D 2.1 Shape, TRELLIS v1, Hi3DGen; optional TRELLIS.2 only with measured viable 16 GB approach. Consider Hunyuan multi-view/other verified candidates if benchmark justifies.
- Texture/PBR: local texture generators and baking workflows; Hunyuan3D 2.1 Paint only if VRAM/license constraints actually allow (official configurations may exceed 16 GB).
- Concept/reference: local image generation via ComfyUI or direct engine adapter. ComfyUI is a workflow orchestrator, NOT an image/3D model by itself; require locally installed checkpoints and node dependencies, and record workflow JSON, versions, seeds and outputs. Support prompt-to-image, reference conditioning, inpainting, masks, and texture workflows only when validated. Do not require ComfyUI for image-to-3D jobs that already have approved reference images. Never infer gameplay layout or exact geometry from a pretty concept image without procedural constraints.
- Prompt planning: local LLM via Ollama/llama.cpp or equivalent, with schema validation and deterministic non-LLM fallback for structured manifests.
- Animation: local motion tools/retargeting (Blender, compatible motion models where feasible); do not promise text-to-motion without evidence.
- Procedural maps: Blender Geometry Nodes, Unity Terrain/Splines, Unreal PCG, open procedural tooling. Houdini Engine is OPTIONAL and must not be required for free workflow due to possible licensing.
- Validation: glTF Validator, mesh checks, texture validation, Blender import/export tests, native Unity/Unreal import tests.
For each candidate record: repo/commit, source and weight license, commercial restrictions, weight size, dependency versions, CUDA/Windows/WSL compatibility, measured peak VRAM/RAM/runtime, output quality, failure rate and installation instructions. Isolate incompatible environments. Use Golden Runavelle Archer Tower reference as a repeatable benchmark; compare equal input, seed when supported, candidates, renders and actual Unity import. Only promote engines that provide measured benefits. No paid AI API dependency.
7. Project-aware generation, batch, quality and consistency
Use the user's real project examples without inventing extra projects: Runavelle, Aetherward, Forgebound. Each has its own Art Bible and output defaults. Do not assume all three share the same art style. Runavelle has an approved Archer Tower reference that must be supplied/located and used for benchmark rather than fabricated.

Batch: a large master prompt -> local planner -> editable asset manifest -> dependency DAG -> concept/approval -> production stages -> per-asset QA -> Library -> engine-specific export. Expand tier families into distinct assets; lock style references, scale and materials. Allow parallel CPU/I/O prep and a default single heavy GPU job; avoid competing GPU Blender render and AI inference. Save checkpoints and resume without redoing completed work. Candidate tournaments/QA remain identical to Single mode. Missing VRAM or engine support causes a visible Blocked state, not quality downgrade.

Quality: preserve source masters, texture resolution, inference steps, model versions, candidate counts, UV/bake/LOD and reference comparison. Separate technical QA (geometry, manifold where appropriate, UV, missing textures, dimensions, rig deformation, file validity, engine import) from artistic approval (silhouette, style, consistency). No fake metrics or guaranteed Meshy parity.
8. Windows packaging, offline behavior, security
Preserve existing Windows desktop app and persistent data. Frontend should not need a manually started terminal/browser. Python backend as a managed sidecar/runtime; AI weights and isolated engine environments can be managed externally by a first-run installer with explicit consent. Provide GPU/Blender/Unity/Unreal detection, storage selection, license acceptance, dependency health and real logs. Do not embed multi-GB weights into every incremental desktop build.

After every completed feature:
implement -> unit/integration tests -> frontend typecheck -> backend tests -> Windows production build -> launch -> desktop smoke test -> report. Keep dist/windows/latest and last known-good; version builds when useful. If running in Linux/cloud, do not claim a Windows executable was built/tested; use Windows runner/host or report blocker. Protect local APIs (bind localhost, origin/auth restrictions), paths, imported archives, MCP tool permissions and subprocess invocations. No arbitrary shell execution from untrusted prompts.
8A. Pipeline routing and explicit I/O (must implement before expanding generators)
Create a Capability Registry for each installed adapter: accepted input modalities, actual outputs, license, VRAM estimate, tested platforms, dependency health, engine support and quality constraints. Route each job by its requested output contract, not by a hardcoded universal chain. Never send every request through ComfyUI or Blender unnecessarily.

Example routes (all stages optional only when their output contract permits):
- Text -> local planner -> approved concept via ComfyUI -> image-to-3D engine -> Blender -> QA -> Unity/Unreal import for an image-conditioned 3D building.
- Approved image -> image-to-3D engine -> Blender -> QA -> engine import (skip concept generation).
- Text + layout constraints -> validated World Plan -> procedural terrain/roads/nav -> Library prop placement -> native Unity/Unreal scene assembly -> gameplay QA for maps. Concept imagery is reference, never authoritative coordinates.
- Existing rig + BVH/video/clip -> retarget -> animation QA -> native engine clips for animation. Do not claim text-only motion generation unless a validated local model exists.
- Text + duration -> procedural shader/particle spec (+ optional ComfyUI flipbook) -> native Unity/Unreal VFX -> realtime preview/performance QA for VFX.
- Text -> local audio model -> loop/loudness validation -> WAV/OGG for audio; no Blender stage.
Every stage defines typed input/output artifacts, dependency hashes, skip conditions, failure recovery, checkpoint, resource class, acceptance tests and evidence paths. If a requested output cannot be produced by installed tools, show a clear capability gap and ask for setup/approval instead of silently substituting a preview image.
8B. Generation policies, review gates and cost guardrails
Support three explicitly named modes: Manual (approve every stage), Assisted (approve concept, candidates and master), and Auto Batch (pre-approved low-risk asset families only, stop at failures or policy gates). Default new game-critical asset types to Assisted. An approval applies to a specific artifact hash/config, not to all future regenerated outputs.

Before GPU-intensive batch execution show: asset count, candidate count, dependency fan-out, expected stages, rough time/disk/VRAM ranges when measured data exist, model licensing and missing dependencies. Set configurable caps for total jobs, retries, storage and child asset generation; no infinite retries or surprise hundreds of missing-prop jobs. Expose dry-run manifest review. Batch and Single must share the same effective config and QA rules. Maintain reproducible provenance but do not promise pixel-identical nondeterministic inference.
8C. Engine import compatibility and acceptance gates
Pin one actually installed/testable Unity Editor version and render pipeline (prefer the existing project's configuration), plus one actually installed/testable Unreal version. Maintain a compatibility matrix instead of claiming universal support. Unity editor-only importer/package and Unreal editor plugin/scripts must have their own versioned source and smoke-test scenes. Keep game project modifications opt-in and reversible; never write directly into a production game project without backup or explicit approval.

For each asset family define measurable pass/fail criteria before implementing: file parses, material references resolve, scale/orientation/pivot correct, native import saves/reopens, performance budget is measured where supported, and relevant gameplay semantics work. For maps include road connectivity, reachable spawn-to-goal routes, non-overlapping build zones, collision/nav generation and deterministic seed reproduction. For characters include deformation test poses; for VFX include real-time playback and parameter editing. Artistic quality remains a human decision, not an invented numeric score.
8D. Windows build efficiency and honest evidence
Keep the strict build-after-every-completed-feature policy, but cache Python environments, model weights and unchanged build dependencies. Package a new desktop executable after each feature; create a full installer only at release milestones unless the current packaging requires it. Use a Windows runner/host for Windows builds; cross-compilation alone is not equivalent to GUI smoke testing. Record hashes and location of last-known-good binaries and a build report. If the agent is running in Linux/cloud without a Windows runner, clearly mark the Windows build gate BLOCKED and do not declare feature complete; continue only with explicitly labeled unverified work.
8E. Scope boundaries, sequencing and user approvals
This specification is a roadmap to implement, not proof that the current AFS supports all asset types. First preserve and benchmark the existing 3D quality pipeline. Do not download dozens of weights, install all MCP servers or create empty navigation tabs as a substitute for functionality. Require explicit approval before installing heavyweight models, accepting licenses, modifying game repositories, deleting/overwriting source assets, or using optional paid software. Never silently send private prompts/assets to cloud services. ComfyUI, MCP, local LLM, and engine adapters are modular and optional at runtime; basic existing Single Asset generation must still function when they are absent.
9. Implementation roadmap: execute, don't stop at planning
Phase 0 — Audit and compatibility matrix (mandatory first): inspect repository and CLAUDE.md; identify actual current working features, local model adapters, licenses, MCP, Unity/Unreal/Blender installations, Windows build commands and golden assets. Produce a concise gap matrix and phased implementation plan; then continue coding unless blocked by a genuine prerequisite.

Phase 1 — Shared foundations: versioned Asset Manifest, plugin SDK, dependency DAG, local planning, resource scheduler, immutable masters, license registry, engine target settings, typed job states and honest UI capability badges. Add regression tests preserving Single/Batch Quality Lock. Build Windows.

Phase 2 — Native 3D import validation: Blender MCP optional + reliable Blender Python; real Unity importer + validation project; Unreal importer proof-of-concept where Editor available; model benchmark and glTF Validator. Prove a generated 3D asset imports correctly in Unity, then Unreal. Build Windows after each feature.

Phase 3 — Map/Environment vertical slice: one Runavelle map from text/structured layout -> editable World Plan -> procedural terrain, roads, props, zones, spawn points -> native Unity Scene/Terrain; then Unreal Level/Landscape. Verify editability and navigation metadata, not only screenshots. Build Windows after each feature.

Phase 4 — Character/Rig/Animation: generate/import a character, rig and skin, retarget a real animation clip, validate in Unity then Unreal. Add optional local motion generation only after validated feasibility. Build Windows after each feature.

Phase 5 — VFX/Materials: create a real spell effect with native Unity particle/VFX and Unreal Niagara, including editable parameters and preview. Material pipeline with verified channel conversions. Build Windows after each feature.

Phase 6 — 2D/UI/Audio/Cinematic: implement separate working vertical slices and native engine importers, prioritizing modules with feasible local/free toolchains. Build Windows after each feature.

Phase 7 — Production hardening: mixed-asset batch dependencies, style consistency, import reports, recovery, install UX, engine-version compatibility, benchmarking, documentation, licensing and performance budgets. Build Windows after each feature.

Prioritize completing each slice over opening all modules simultaneously. Do not create placeholders that look finished. If time/context is limited, leave a precise checklist of tested vs untested work, and resume at the next phase; never claim all phases completed without evidence.
10. Acceptance criteria and reporting
For every implemented module, demonstrate:
1. Real input accepted and saved; validated manifest produced.
2. Actual local generation or procedural transformation runs, with recorded tool/model provenance.
3. Source/master and derivatives are saved and reload after desktop restart.
4. Target-engine import runs through real Editor, creating editable native assets where required.
5. QA and errors are visible per asset; human approval is separate.
6. Single/Batch quality parity and license policies are preserved.
7. Windows desktop app is rebuilt and smoke-tested, or accurately reported as blocked.
Minimum integrated demonstrations:
- Runavelle Archer Tower: local 3D -> Blender processing -> Unity prefab + Unreal import validation when available.
- Runavelle map: text/layout -> editable world plan -> terrain + assets + spawn/build zones -> real Unity scene and Unreal level.
- Character: rigged model + one valid animation imported to both engines.
- VFX: editable real-time effect in Unity and Unreal, not merely a rendered video.
Each feature report must include: changes/files, model/tool versions, actual output paths, build version/path, tests, screenshots or logs where available, measured performance, known limitations, license status, and next unblocked action. Do not invent benchmark numbers, successful tests, asset files or engine compatibility.
11. Immediate instruction
Start now in the EXISTING repository. First audit actual code, dependencies, desktop build and integrations. Produce a short prioritized execution plan; validate the existing Single Asset quality baseline before changes; then implement Phase 1 foundations and the first end-to-end Unity validation slice. Implement the ComfyUI adapter only if it fills a verified input/output gap and can run locally within the hardware/license constraints. Do not stop at giving advice. Do not rewrite existing working code or introduce paid APIs. Maintain production-quality code and persist the build-after-every-feature rule in CLAUDE.md.