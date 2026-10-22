# ASSET FORGE STUDIO — VIDEO STUDIO + MULTI-ASSET CINEMATIC DIRECTOR
## Complete Claude Code Implementation Prompt & Practical Aetherward Examples
Version: 1.0 · Target: Existing AFS (Tauri 2 + React/TypeScript + Python FastAPI + SQLite) · Local-first Windows

> **GIAO CHO CLAUDE CODE:** Bạn đang làm việc trong repository Asset Forge Studio HIỆN TẠI. Đây là yêu cầu triển khai tính năng thật, không chỉ thiết kế giao diện hoặc viết tài liệu. Audit trước khi sửa; tận dụng Production Queue, Library, GPU scheduler, Blender pipeline và versioning hiện có; không big rewrite. Làm từng vertical slice hoạt động và test thật. Báo cáo bằng tiếng Việt. Không tự nhận đã chạy AI, dựng map hoặc export khi chưa có bằng chứng.

# 1. PRODUCT GOAL

Create a first-class **Video Studio / Cinematic Director** in AFS, with an accessible workflow:

**Select Project → Provide Prompt + Media/GLBs → Build/Select Scene → Auto Storyboard → Render/Generate → Preview → Refine using natural language → Compare versions → Export MP4 → Library.**

Support:
- Text-to-Video (AI-generated clips)
- Image-to-Video (concept/game screenshot → movement)
- GLB-to-Video (deterministic rendered asset cinematic)
- **Multiple GLBs in one composed scene**, including environment/map modules, characters, bosses, weapons, props, lights and atmospheric effects
- Video-to-Video via supported engines, and deterministic FFmpeg edits
- Hybrid 3D + AI Video
- Prompt-driven iterative editing on an existing timeline: "zoom closer", "cut seconds 4–6", "make it more epic", "change camera", "add smoke", "replace shot 3"
- Storyboards, timelines, captions and audio
- Aspect ratio templates for cinematic trailers and social clips
- Quality-aware locally scheduled video jobs without paid API dependencies

Do not change Aetherward's underlying game architecture: it is a Unity 2D/2.5D Crystal Defense game. Cinematic video may be rendered from 3D GLBs or generated AI video; it is not automatically a playable Unity scene.

# 2. EXISTING REPOSITORY AUDIT AND INTEGRATION

Audit actual modules and their current status:
- Tauri React routes/components and Python subprocess management
- FastAPI backend, database migrations, Project/Library models
- Production Workspace, queue, pause/resume, retry, status events
- GPU scheduler, CUDA device monitoring, Blender subprocesses
- Existing GLB import/export, stable asset IDs, revision history
- Project Art Bible, camera/scale conventions and export profiles
- Model downloader, dependency installation, license notices
- FFmpeg/FFprobe/Blender installation and support on Windows
- ComfyUI install/runtime/compatible nodes and workflows if available

Document implemented/partial/missing/blocked; create incremental migrations and tests. Reuse existing components and IDs. No second queue, no duplicate Library or redundant local GPU manager. Bind services to loopback only, defend against path traversal, shell injection and unsafe arbitrary workflow execution.

# 3. CINEMATIC PROJECT AND SCENE DATA MODEL

A **CinematicProject** belongs to an existing AFS Project and contains:
- Project ID, cinematic ID, original user prompt, effective spec and provenance
- Scene(s), storyboard, shot list, timeline, audio, transitions, export targets
- Source asset references to existing AFS Library (stable asset IDs AND pinned versions)
- Media imports (image/video/audio)
- Quality/engine selection and generated revisions
- Technical QA, artistic review, export/publish records
- Mutable draft pointer, immutable revision snapshots and source hashes

A **Scene** is a reusable composed 3D environment:
- 1..N imported GLBs or generated meshes (not only one model)
- Parent-child object hierarchy and semantic tags (hero, boss, crystal, ground, wall, prop, background, FX anchor)
- Named object transforms: position/rotation/scale; coordinate system and units; ground plane and pivot
- Terrain geometry or modules; paths, structures and repeatable decorations
- Cameras, lights, volumetrics, fog, particles, animations, rig clips
- Material overrides stored as NON-DESTRUCTIVE layers
- Named anchors: `crystal_center`, `boss_spawn`, `hero_01..hero_06`, `camera_hero`, `combat_lane`, etc.
- Source license/provenance and map compatibility metadata

Use a real Scene Composer with object list, hierarchy, inspector, transform gizmos, camera navigation, snapshots, preset lighting. Prefer existing three.js/react-three-fiber or app viewer integration if already present and functioning; Blender remains render authority. Make scene configurations serializable to JSON and reproducible in Blender Python scripts. Support undo/redo, save/reopen, missing-asset resolution and version pinning.

**Critical:** A GLB character/boss alone does not include a map. A cinematic scene needs environment GLBs (ground tiles, walls, pillars, arches, ruins, rocks), lighting, camera, and optional sky/fog/VFX. AFB/AFS must NEVER pretend a single boss GLB magically contains a populated environment.

# 4. THREE WAYS TO GET A MAP / ENVIRONMENT

## A. Existing composed map
- Import an existing complete map GLB, BLEND scene, or supported Unity-exported environment with hierarchy intact where practical.
- Detect transforms, materials, dimensions and missing textures.
- Offer map as a Scene preset.
- Do not require rebuilding if a valid compatible environment already exists.

## B. Assemble a map from modular GLBs (recommended for Aetherward)
- Select biome/project preset and/or environment GLBs from Library.
- Scene Composer places repeatable tile/path/wall modules, ruins, pillars, obelisks, foliage, ground props, crystals.
- Generate an arena plan with preserved central crystal zone and approach lanes.
- Snap compatible modules via measured dimensions/connectors, then detect gaps, overlaps, floating objects, collisions, inconsistent scale and camera obstruction.
- Apply seeded variation to rotation/decoration; keep critical landmarks constant.
- Allow user to specify style and composition with natural language.
- Generate extra supporting props ONLY if needed and supported; preserve pinned references.
- Keep decorative background separate from navigable/collision geometry. No need to write gameplay AI navigation for a purely cinematic scene.

## C. AI-assisted concept/background
- Generate/receive a reference image and use image-to-video when a full 3D map is not needed.
- Alternatively use a 2.5D projected background plus selected real 3D foreground assets.
- Label the resulting video as AI/hybrid: not a reusable fully modeled 3D map.
- Do not claim exact geometry, camera freedom or identity preservation from flat reference imagery.

Provide scene-building modes: **Auto Scene** (default), **Assisted Layout**, **Manual Scene Editor**.

When Auto Scene is requested and required models are missing:
- Search the project's Library by tags/category/element/asset ID.
- Select related compatible pieces with an auditable resolution log.
- Fallback to actual available environment; optionally queue missing prop generation only if explicitly permitted by user settings.
- Ask for input only if a critical asset is missing and a wrong substitute would compromise identity.
- Missing one decorative prop must not block the whole video.

# 5. MULTI-GLB COMPOSITION AND ANIMATION

Enable user to add any number of relevant GLBs using:
- `Add from Library`, drag-and-drop files, bulk select, attach asset collections, `Use Environment Pack`, `Use Saved Scene`
- Per-object transform/pivot/scale/visibility/material overrides
- Parenting/attachments: weapon → hand socket, aura → crystal, armor → compatible body
- Save assembled scenes as reusable presets and preview with real materials
- Repeated props as instances when supported to reduce memory
- Collision/penetration basic checks, ground snap, asset bounds and scale normalization

Animation reality:
- If GLBs have compatible skeletal animation, retarget or play clips after verifying bone naming, rest pose, skin weights, orientation, timings.
- For non-rigged GLBs, support camera/object transforms, light/material animation, particle-based movement; do NOT promise believable walking/fighting without rig or actual animation.
- Expose animation readiness: `Rigged + Clips`, `Rigged No Clips`, `Unrigged`, `Retarget Supported`, `Missing Animation`.
- Offer verified rigging/retarget plugins ONLY if available; don't fabricate generated combat animation.
- Support cinematic choreography timeline: boss emergence, crystal pulsing, hero silhouettes, shield, shockwave, elemental beams, projectiles and impact events.
- Do not permanently bake one-shot VFX into GLB master meshes.

# 6. AI VIDEO ENGINES — VERIFIED LOCAL ADAPTERS

Create a capability-based `VideoEngineAdapter` registry with real checks:
- Wan 2.2 TI2V-5B through supported local ComfyUI workflow: default experimental AI video path after successful test on 16GB VRAM.
- LTX locally through compatible maintained workflow: optional, check version/VRAM/disk/license and audio support.
- Wan 2.2 14B: experimental capability gate, only with proven compatible memory-offload/quantization.
- HunyuanVideo 1.5: optional after verified local install and license.
- Blender 4.5 + FFmpeg: the reliable 3D cinematic and deterministic edit/render pipeline.

For ComfyUI: use actual HTTP and WebSocket APIs and run appropriate workflow JSON; detect existing service, model paths, nodes, versions and ownership; don't terminate unrelated user sessions. Persist job IDs, progress, outputs, errors; recover from disconnect. Download only selected models after showing license and disk demands. Never assume 16GB can run every model. Honor RAM/VRAM/drive limits, offload intelligently without silently lowering quality.

Do not make paid APIs mandatory. Do not silently upload files to remote providers.

# 7. PROMPT-TO-STORYBOARD + SMART VIDEO EDITING

Support natural language at BOTH initial creation and revision stages.

## A. Intent planner
Parse intent into strongly typed, validated operations:
- `CAMERA_ZOOM`, `CAMERA_ORBIT`, `CAMERA_DOLLY`, `CAMERA_TRACK`, `CAMERA_PAN`, `CAMERA_ANGLE`
- `TRIM_TIME_RANGE`, `SPLIT_CLIP`, `DELETE_RANGE`, `REORDER_SHOTS`, `REPLACE_SHOT`, `EXTEND_SHOT`
- `LIGHTING_CHANGE`, `COLOR_GRADE`, `SPEED_RAMP`, `SLOW_MOTION`, `SHAKE`, `TRANSITION`
- `ADD_3D_OBJECT`, `REMOVE_3D_OBJECT`, `MOVE_OBJECT`, `CHANGE_MATERIAL`, `ADD_VFX`
- `REGENERATE_SHOT`, `REGENERATE_AI_VIDEO`, `VIDEO_UPSCALE`, `FRAME_INTERPOLATE`
- `MUSIC`, `SFX`, `TITLE`, `CAPTION`, `AUDIO_MIX`

For each request:
1. Resolve user intent from text and selected playhead, shot or time range.
2. Show optional change summary and scope; Auto mode proceeds on non-destructive edits.
3. Build edit plan with affected clips, objects and stages.
4. Prefer direct timeline/Blender/FFmpeg operations when exact deterministic result is possible.
5. Use AI regeneration only when it is materially needed and the workflow exists.
6. Create a NON-DESTRUCTIVE new revision/version.
7. Preview affected shots; run real QA and export.

Examples:
- "Zoom closer on the crystal between seconds 3–5" → 3D camera dolly/zoom if Blender source is available; otherwise crop/keyframe zoom on video with clear framing/resolution limitations.
- "Cut out 00:08–00:12" → NLE time-range delete ripple edit via FFmpeg/timeline, NO AI rerun.
- "Make shot 2 more epic" → ask NO question if a useful default exists: increase dramatic rim light, low-angle camera, more purposeful particle VFX, SFX/music impact, tighter pacing, but preserve art direction and legibility; use actual editable sources; if only flat MP4 exists, apply available color/audio/timeline changes or optional AI video-to-video.
- "Replace the boss with the Aether Devourer and show it emerging" → actual GLB swap + scene rerender if rig/animation path exists; do not claim full organic animation if unrigged.
- "Change the map to Frostfall Bastion" → load new composed scene/modules, preserve hero/boss/crystal references and revalidate placement.

## B. Revision semantics
- Original prompt immutable; store delta prompt with target scope.
- A user can choose whole video / scene / shot / clip / time range / selected object.
- Versioning v1/v2/v3, compare, restore, branch from earlier revision.
- Queue re-render only the invalidated region/stages; unchanged approved footage reused.
- Preserve current published video until user promotes a version.

## C. Manual controls
- Visual shot/clip selection on timeline, in/out handles, playhead, frame preview.
- Click/drag 3D scene objects, camera preview, named anchors.
- Optional keyframe editor for camera/object/lighting.
- Prompt remains primary; manual refinement is an escape hatch.

# 8. STORYBOARD AND MULTI-SHOT CINEMATICS

Generate a storyboard from a prompt, favor 4–10s shots as compatible with actual AI-video inference windows; for long final videos combine independent real shots. Each Shot stores:
`id, sceneId, sourceRefs, targetDuration, intent, generationMode, camera, subject, action, blocking, lighting, mood, transitionIn/Out, audioCue, exactTimeRange, renderStatus, qaStatus, versionHash`.

Allow:
- Fully deterministic Blender-rendered scene shots.
- AI-generated shots from prompts or rendered 3D reference frames.
- Hybrid sequences (start with Blender for accuracy, AI continuation for fluid motion) with honest provenance.
- Shot ordering, cut, trim, speed changes and transitions.
- Longer outputs (30s, 1m, 3m, 10m) only by honest editing of real available footage—not fake infinitely long AI single shots or repetitive loops disguised as footage.

Enable **Shot Lock** and **Asset Identity Lock** when exact hero/boss/model continuity matters. Document that AI I2V does not guarantee exact rig/mesh identity.

# 9. VIDEO TIMELINE / EDITOR

Build a practical editable local non-linear timeline:
- Multi-track video, image, audio, title and VFX tracks.
- Trim, split, ripple delete, reorder, replace shot, transitions, keyframe zoom/crop/pan, speed ramp, fade, reverse where safe.
- Editable titles and optional subtitles.
- Drag assets from Library.
- Undo/redo, autosave, save/open, zoom timeline, waveforms where possible.
- Fast low-resolution proxy previews, final quality retained.
- Keyboard shortcuts, context menus.
- `Undo last refinement` and `Compare before/after`.
- Always preserve original source and versioned edit decision list (EDL).

Use FFmpeg/FFprobe for deterministic media work; avoid encoding entire final video on every minor edit. Cache intermediate clips by content hash and invalidate only changed sections.

# 10. REAL GLB CINEMATIC RENDER PIPELINE

Use the installed Blender (4.5 if available) in a headless Python-driven pipeline, preserving source:
- Import all pinned GLBs of the scene.
- Resolve textures, transforms, normal/tangent/material and animation clips.
- Apply game Art Bible color/light presets.
- Build camera(s), shot keyframes, VFX emitters, compositing passes.
- Render image sequences then encode video using FFmpeg (H.264 MP4 default).
- Save source `.blend` and procedural scene JSON/scripts (optional but preferred) for genuine non-destructive rerendering.
- Keep separate staging and final output directories, atomic final commit.
- Render resumption from completed valid frames, not inside unsupported GPU inference.
- Validate frames, audio, fps, resolution, total duration and stream decode.

Camera/lighting presets: dolly-in, turntable, orbit, crane, tracking, top-down, isometric, hero reveal; dark fantasy, studio, molten, frost, storm, magical cyan.
Support rigged animation where available; mark blockers for unknown rigs and unrigged characters.

# 11. PRODUCTION QUEUE AND RESOURCE SAFETY

One global durable queue for 3D and video tasks, single heavy GPU stage at a time by default on a 16GB 5070 Ti; overlap CPU preprocessing and FFmpeg jobs safely.

Stages as applicable:
`Analyze → Resolve Sources → Assemble Scene → Storyboard → Prepare Models → Generate/Animate Shots → Blender Render → Postprocess → Timeline Assemble → Technical QA → Encode → Export → Library`.

Show real job/shot stage, progress, GPU status, actual outputs and logs. Never invent progress percentage when underlying stage cannot measure it. Pause finishes current safe stage, close/reopen resume; cancel/retry separate; bounded retry. Preserve completed shots. Respect Maximum Quality and no silent downgrade. Support Draft/Balanced/High/Maximum/Custom with clear native vs upscaled distinctions.

# 12. LIBRARY, EXPORT, VERSIONING

Video assets appear automatically in existing Library with thumbnail, duration, fps, pixel size, audio state, engine, scene, provenance, output path, version, QA, publish status.

Asset Detail:
- Real video player / shot strip / timeline
- Original prompt, revisions, object/scene references, source versions
- `Refine with Prompt`, `Open Scene`, `Compare Versions`, `Re-export`, `Open Folder`, `Promote Version`
- Reuse project presets and original media

Default export:
- MP4 H.264, selectable 16:9 / 9:16 / 1:1 / 4:5, user-selectable output size and FPS
- Presets: Game Trailer, YouTube, Shorts, TikTok, Instagram/Facebook
- Optional image sequence, alpha rendering when supported, separate audio/stems

Technical QA independent of artistic approval. Never replace published final video silently.

# 13. UI FEATURES

`Video Studio / Create`: Project, mode, prompt, references, optional Scene, aspect ratio, duration, quality, Generate.
`Scene Composer`: Library assets panel, 3D viewport, hierarchy, inspector, map preset selector, placement, cameras, lights, staging.
`Production`: shared job list, live stages, per-shot output, errors, log viewer.
`Video Detail`: player, editable timeline, prompt-based refiner, versions, export.

The default flow must allow simple requests with missing optional details. Use explicit → inherited → inferred → defaulted provenance; critical questions only. Advanced settings collapsed by default.

# 14. PERFORMANCE / RIGHTS / SAFETY

- Protect local sources; no remote upload without opt-in.
- Verify model weights, workflows, source licenses and commercial usage restrictions.
- Avoid unauthorized music/video/character reuse.
- Use safe import paths; contain child processes; do not execute untrusted source code from imported archive/workflow.
- Optimize GPU RAM, thumbnails, proxies, model memory offload, instancing, storage. Benchmark rather than promise performance.
- Disk preflight, model/version checks, clear failures and actionable remedies.
- Camera should never accidentally clip central hero/boss/crystal; auto visibility tests at keyframes.
- Cinematic art direction should not be confused with actual gameplay screenshots.
- Record exact source version and hashes.

# 15. IMPLEMENTATION ORDER

**P0: Reliable composition + rendered video**
1. Audit; schema/model migration and adapter contract.
2. Import multiple GLBs, Scene Composer, modular environment template.
3. Blender scene/shot render with a real GLB and real environment modules.
4. MP4 H.264, preview, Library, shared Production Queue.
5. Prompt-driven camera zoom, trim, cut, lighting and rerender.
6. Versioning, resume and tests.

**P1: AI video + hybrid + longer timeline**
7. ComfyUI + verified Wan 2.2 5B T2V/I2V on actual hardware.
8. Storyboard generator; shot segmentation and reference image conditioning.
9. Timeline editing, source locks, partial rerender/replacement.
10. Audio, titles, scene transitions, aspect-ratio exports.

**P2: Optional advanced capabilities**
11. Verified LTX adapter; optional others when compatible/licensed.
12. Rig/retarget solutions if genuine tools exist.
13. Auto scene population and natural-language object manipulation.
14. Advanced video-to-video, motion controls, cinematic templates.

Finish each P0 vertical slice functionally; don't defer a complete working path until P2. Don't add fake toggles or stub buttons.

# 16. MANDATORY REAL ACCEPTANCE TESTS

A. Import a real hero GLB, boss GLB, crystal GLB and 10+ environment modules. Place all in one Scene with distinct hierarchy; save/reopen and verify positions.
B. Build an Aetherward ruined sanctuary cinematic scene from module selection. Verify arena coverage, central crystal, foreground/background and no glaring overlaps/floating items.
C. Render a REAL 8–15s 3D cinematic with at least two camera movements, atmospheric light and actual audio or silent track; FFprobe validates file.
D. Refine with: "Zoom into the crystal at seconds 3–5"; verify correct shot interval changes and old version preserved.
E. Refine with: "Cut seconds 6–8"; verify duration shrinks accordingly WITHOUT AI inference.
F. Refine with: "Make boss reveal more epic"; verify concrete staged changes to camera, lighting/VFX/music and only affected shot rerendered.
G. Select an alternate environment preset; preserve pinned character versions.
H. Close app mid-render; reopen; reuse completed frames/shots and finish.
I. Queue 3D generation alongside video render; verify GPU-heavy stages serialize.
J. Verify same scene/source hashes yield reproducible camera and object layout.
K. Generate a real Wan text-to-video and image-to-video ONLY if installed models and compatible hardware exist; otherwise label unverified/blocked accurately.
L. Build Windows desktop app and smoke test Create → Scene → Production → Library → Refine → Export.

Status vocabulary: VERIFIED / IMPLEMENTED_UNVERIFIED / BLOCKED / NOT_IMPLEMENTED. Report actual commands, files, logs and outputs, not promises.

---

# 17. PRACTICAL AETHERWARD CINEMATIC — READY-TO-RUN EXAMPLE

This section illustrates the exact desired user workflow and provides a test scenario. The names/IDs below are from the Aetherward 462-asset proposed manifest; AFS MUST resolve whether real GLBs have been generated and imported. A prompt manifest entry is NOT an existing GLB.

## Required / recommended input assets

From AFS Library, add these **real generated GLBs**:
- `AEW-0349` — Aether Crystal — Pristine (central object)
- `AEW-0157` — The Sepulcher Regent — Phase I (boss)
- `AEW-0001` — Ignis — Base (hero)
- Ruined Aether Sanctuary environment modules:
  - `AEW-0181` Ground Tile A
  - `AEW-0182` Ground Tile B
  - `AEW-0183` Path Segment
  - `AEW-0184` Path Junction
  - `AEW-0185` Wall Segment
  - `AEW-0186` Wall Corner
  - `AEW-0187` Broken Pillar
  - `AEW-0188` Standing Pillar
  - `AEW-0189` Archway
  - `AEW-0191` Obelisk
  - `AEW-0192` Ritual Platform
  - `AEW-0194` Background Landmark
- Optional: `AEW-0353` Aether Crystal — Critical for damage-state shot
- Optional: actual hero/weapon/FX geometry, ambience/music sources with proper license

If these GLBs do not exist, queue their generation or import equivalent authentic project assets. Do not silently substitute a different boss.

## Example steps in the app

1. Open AFS → Project `Aetherward` → `Video Studio` → `New Cinematic`.
2. Select `3D Cinematic (Blender)` to keep the exact boss/crystal appearance. Choose 16:9, 1920×1080 final render, 24 fps, 20 seconds, High/Maximum Quality according to local preflight.
3. Click `Add Assets from Library` and select Crystal + Boss + Ignis.
4. Click `Environment` → `Ruined Aether Sanctuary` → `Auto Assemble` and load the modular environment pack listed above. Use a clear central crystal zone, a hero on the left foreground, boss at distant ruin archway, paths leading toward crystal, broken pillars, mist and atmospheric lighting.
5. Confirm visually in `Scene Composer` that objects do not float, walls do not intersect main subjects, and camera framing leaves a readable crystal/boss silhouette. Save scene as `Aetherward_Sanctuary_Boss_Reveal`.
6. Paste the **cinematic prompt** below in the main Prompt field and click `Generate`.
7. In Production, inspect real shot results, open completed video in Library, choose `Refine with Prompt` for revisions.
8. Export MP4. If 20 seconds cannot render with available resources, keep shot-based rendering and report precisely what remains.

## Initial cinematic prompt — copy into Video Studio

Create a premium 20-second dark mythic arcane fantasy cinematic for Aetherward using the EXACT GLB assets attached to this scene. Preserve model identity, geometry, materials and recognizable silhouettes. Scene: a ruined ancient aether sanctuary at night. At the center stands a luminous blue-white Aether Crystal on a ritual dais. Ignis, an armored fire hero, stands defensively to one side. Deep beyond a cracked stone archway, the Sepulcher Regent emerges from purple-black fog. Broken pillars, weathered stone paths, arcane obelisks, floating dust and controlled magical embers fill the environment. Atmosphere is mature, mysterious, ominous, painterly stylized 2.5D; cinematic yet readable, no childish/chibi proportions, no exaggerated neon saturation.

Shot 1 (0–4s): high wide establishing shot; slowly descend toward the sanctuary with moonlit haze; show crystal and the ruined perimeter.
Shot 2 (4–8s): smooth dolly in toward the Aether Crystal; cyan runes begin to pulse; surrounding stone reflects subtle blue light.
Shot 3 (8–13s): low-angle over-the-shoulder hero framing; rack attention toward the shadowy archway; the Sepulcher Regent becomes visible with a threatening pose.
Shot 4 (13–17s): cinematic boss reveal; slight camera orbit and controlled violet rim light; slow smoke movement and an arcane shockwave without obscuring its silhouette.
Shot 5 (17–20s): cut back to the crystal and hero, quick light pulse, title text "AETHERWARD" on the final beat, fade to black.

Camera motion should be physically plausible and avoid mesh intersections. Add tasteful atmosphere and strong sound cues if licensed sounds are available; otherwise render clean silent video and leave audio slots ready. Preserve safe margins for 16:9 cropping. Render each shot independently for iterative editing, assemble to final 1080p 24fps H.264 MP4, retain editable scene/timeline data.

## Example follow-up prompts — after video is generated

**1) Zoom closer, no full regeneration**
"At 00:04–00:08, move the camera 35% closer to the Aether Crystal and lower the angle slightly. Keep the crystal fully visible, preserve all other shots and do not change any models. Rerender only shot 2."

**2) Cut footage exactly**
"Remove 00:08–00:10 from the current video, close the gap with a clean hard cut and ripple all later clips left. Do not regenerate any AI video."

**3) Make boss reveal cooler**
"Improve only shot 4. Make the Sepulcher Regent reveal more intimidating: camera closer and slightly lower, stronger violet rim light, denser but localized swirling fog, one brief arcane shockwave synced with a deep impact SFX if available. Do not change the boss mesh, armor or environment. Keep the boss silhouette readable. Export as a new version."

**4) Change environment while keeping cast**
"Duplicate this cinematic as a new version. Replace the Ruined Aether Sanctuary environment with a Frostfall Bastion modular scene from my Library. Keep the exact same Ignis, boss and Crystal asset versions, maintain the core shot sequence, change the lighting to cold moonlight, add subtle drifting snow, and rerender only affected 3D shots."

**5) Make a vertical short**
"Create a 9:16, 15-second teaser from the same footage. Preserve hero and boss visibility with shot-by-shot reframing instead of blind center crop. Use stronger pacing, title at the end, no new AI generation unless a shot cannot be reframed safely."

**6) Increase spectacle without breaking continuity**
"Create v3 from v2: increase the cinematic impact of the final five seconds with a faster push-in, subtle chromatic aberration only on the shockwave, stronger crystal bloom within highlight clipping limits, and more dramatic audio. Keep subject and background geometry unchanged."

# 18. FINAL INSTRUCTION

Implement the workflow above inside the existing application, not as an unrelated demo project. Begin with functional multi-GLB scene composition, modular environment assembly, Blender renders and exact natural-language video editing; only then layer optional AI video generation and advanced V2V.

The final target UX is:

**Choose Game → Add boss/hero/crystal GLBs + environment pack → Prompt cinematic → See storyboard/preview → Render → Prompt "zoom/cut/make epic" → Compare v1/v2 → Export MP4.**

---

# 19. AUDIO DIRECTOR — MUSIC, SOUND EFFECTS, DIALOGUE AND VOICE (MANDATORY EXTENSION)

Implement a full **Audio Director** integrated into Video Studio, Scene Composer, Timeline, Production Queue and Library. Audio must not be an afterthought: cinematic prompt and storyboard should produce *explicit editable audio cues* with timestamp, asset references, gain, automation and provenance.

## 19.1 Four audio families
1. **Music / Score:** original cinematic background music, battle tension, ambient music, emotional transitions, intro/outro and loop-aware background scores.
2. **SFX / Foley:** footsteps, armor movement, blade draw, crystal pulse, magical impacts, wind, falling debris, thunder, portals and environmental ambience.
3. **Dialogue / Voice-over:** spoken dialogue by characters, narrator voice, multiple speakers with distinct voices, Vietnamese and English and any other languages a verified engine supports.
4. **Spatial / Environmental audio:** positional 3D mix when source camera and object coordinates exist; pan/attenuation/reverb simulated for stereo output, not false claims of surround sound.

## 19.2 Verified local audio engine adapters
Use a capability and license registry. Prefer per-track engine selection and safe fallback to imported licensed media.
- **Music:** ACE-Step 1.5, when actually installable and compatible. Its project describes local music generation, long tracks, controllable style/lyrics and MIT code; still verify exact checkpoint license, resulting tracks, local hardware and runtime before production claims.
- **Short SFX/Foley:** Stable Audio Open optionally, with checkpoint/model license verified; supports text-to-audio samples up to about 47s according to its publisher, not a guaranteed complete soundtrack. Alternatively procedurally synthesize simple impacts or use appropriately licensed project SFX.
- **English TTS:** Kokoro-82M local, when installed; Apache-2.0 weights and multiple voices, but language/voice availability is model-version-specific.
- **Vietnamese TTS:** investigate VieNeu-TTS open weights/version with precise licensing, especially v3 Turbo vs proprietary v4. Test natural Vietnamese pronunciation before enabling as default; never silently require hosted/proprietary APIs.
- **Optional F5-TTS:** code and *weights* have different license terms; upstream weights carry CC-BY-NC. Do not silently use for commercial game assets. Voice cloning only with explicit authorization of the source speaker.
- **Video-conditioned audio:** optional local MMAudio inference when compatible and licensable; align footsteps/impacts/ambience to visual motion; not a replacement for speech/music.
- **No AI dependency for mixing/editing:** FFmpeg filtergraph and deterministic controls remain fully operational offline.

Don't install all models automatically. Schedule music/SFX/TTS inference on existing AFS GPU queue; never run huge video and audio engines simultaneously by default on 16GB VRAM. Cache outputs and free model memory when done.

## 19.3 Prompt-to-audio plan
Parse cinematic prompt into an **Audio Cue Sheet** with separate BGM, SFX, Dialogue, Ambience tracks.
Each cue: `cueId, timelineStart, timelineEnd, linkedShot, linkedObjectId, sourceRef, speakerId, language, text, desiredMood, generationPrompt, engineId, gainDb, pan, fades, ducking, revision, license, status`.
Support an Auto Audio mode which picks safe defaults and generates needed content, and Manual mode with track controls. Don't generate dialogue if the user requested silent/no dialogue. Do not treat atmospheric tone as permission to invent plot dialogue without user intent; can suggest narration as optional.

## 19.4 Game cinematic specifics
When boss steps or swings, attach impacts to **actual timestamps/animation events** rather than arbitrary evenly spaced noises. Tie crystal magic pulse to shimmer cue, fog/wind to ambience, sword hit to impact; if events are unavailable, use manually authored cue points or observed motion heuristics with confidence markers. Support isolated sound effects, tails, reverbs, distant/near perspective. For the Aetherward 20s example:
- 0–4s: low dark orchestral drone, distant wind, dust/stone ambience.
- 4–8s: cyan crystal harmonic pulse, gentle magical resonance; raise tension subtly.
- 8–13s: armor rustle, restrained footsteps and low bass buildup as boss appears.
- 13–17s: massive but clean magical impact, brief reverb tail, short musical crescendo; never bury important dialogue.
- 17–20s: resolve score to final title hit, delay/reverb decay, fade silence.
Example boss spoken line (only if dialogue explicitly requested): "The crystal shall fall." Use a permitted fictional preset voice, no real-person imitation.

## 19.5 Voice Director
For each character, save an editable **Voice Profile** containing speaker ID, selected licensed local TTS voice, supported languages, delivery notes, consistent voice preset/seed where supported, speaking rate, pronunciation lexicon, reference authorization and voice asset history.
- Script editor with lines assigned to characters and timeline/shot IDs.
- Natural-language delivery instructions: ominous, whispered, commanding, frightened, calm; only use controls a model supports, otherwise approximate via approved processing and mark limits.
- Voice generation per utterance with timeline placement; trim/pause/time stretching carefully without destroying intelligibility.
- Character voices stay consistent across revisions and projects.
- Subtitle/SRT/VTT generation from exact script and validated TTS timing; optionally use forced alignment or ASR if installed, not guessed timing.
- Optional lip sync only if face rig/morph targets OR a verified mouth animation/2D sprite solution exists. Never claim moving lips on an unrigged GLB automatically.
- Explicit user consent and proper rights for custom voice recordings, no real-person cloning without authorization.

## 19.6 Audio mixing and mastering
Implement multi-track audio timeline with waveform preview, split/trim/drag/fade, gain, panning, mute/solo, per-track effects, reverb, EQ, compressor/limiter when actually supported, keyframed automation, crossfade and music auto-ducking under speech. Provide accessible loudness presets, true-peak safety, clipping/quiet checks and consistent audio export. Preserve all source WAV stems + final AAC/PCM as appropriate. FFprobe technical QA confirms channels, duration, sample rate, silence/clipping metrics when available; avoid promising perfect artistic sound from these measurements.

## 19.7 Prompt refinements on completed video/audio
Route natural language to correct, minimal targeted operations and save versioned changes:
- "Make the background music more intense during the boss reveal" → adjust musical automation or regenerate only music segment, preserve video.
- "Mute music from 8 to 12 seconds so I can hear the boss" → volume keyframes, no AI rerun.
- "Give the boss a deep gravelly voice and say 'The crystal shall fall' at 14 seconds" → create dialogue track via verified TTS, duck BGM, ensure timing/caption.
- "Replace footsteps with heavier stone-armored steps" → regenerate/select SFX and replace affected cues only.
- "Change all dialogue to Vietnamese" → regenerate TTS for translated/verified script, align subtitles and timing, don't change scene/models without need.
- "Cut 4–6 seconds" → ripple-edit linked sound cues, move automation and crossfades safely.
- "Zoom closer while the boss speaks" → camera revision and audio speech preserved.
- "Make it more epic" → propose concrete score, impacts, silence, dynamics, timing and camera/VFX adjustments; no blanket loudness boost or destructive flattening.

## 19.8 Dialogue/music copyrights and transparency
Record `generated/imported`, exact source license, code versus weights license, model version, source assets, permitted commercial status and any required notices. Do not generate copies of named copyrighted songs or impersonate real performers; don't promise output copyright exclusivity. Do not take music from online videos without rights. Optional custom recorded voices only with affirmative consent. Keep project offline-first and avoid unauthorized uploads.

## 19.9 Acceptance tests
1. Create original 20s Aetherward score from a real working local music adapter, or mark engine BLOCKED transparently; basic licensed imported music editing must still function.
2. Generate or import five timed distinct SFX and place them on real shots.
3. Generate two distinct TTS speaker voices through an actually installed model; export intelligible speech, or document unsupported language/engine accurately.
4. Mix music + SFX + dialogue with side-chain ducking, no clipping, synchronized timeline export.
5. Prompt-edit "mute music 8–12s", "voice line at 14s", "make boss hit stronger" and verify only affected audio tracks change, versions retained.
6. Trim or remove a video segment; linked audio and subtitles ripple correctly.
7. Close/reopen app and verify saved audio cue sheet, engine metadata, source references and stem files remain accessible.
8. Test RTX 5070 Ti shared inference scheduler with video GPU + audio GPU jobs, no accidental GPU concurrency or silent quality downgrade.

## 19.10 Definition of Done addition
Video Studio is NOT fully finished without functioning audio import, multitrack mix, timeline sync, voice/dialogue cues, cue-level natural-language refinements, real export and tests. Optional local *AI generation* adapters may be clearly marked BLOCKED when unavailable, but never substitute mocked audio and claim success.

### Audio source reference URLs for verification
- ACE-Step: https://ace-step.github.io/ACE-Step-1.5/en/
- Stable Audio Open: https://stability.ai/news-updates/introducing-stable-audio-open
- Kokoro: https://huggingface.co/hexgrad/Kokoro-82M
- VieNeu-TTS: https://github.com/tuanmuvn/vieneu-tts
- F5-TTS licensing: https://github.com/swivid/f5-tts
- MMAudio official: https://github.com/hkchengrex/MMAudio
- FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
