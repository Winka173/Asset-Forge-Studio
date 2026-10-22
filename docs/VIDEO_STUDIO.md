# Video Studio implementation ledger

Authority: `doc/Asset_Forge_Studio_Video_Studio_Cinematic_Director_V1.md`, including
the mandatory Audio Director extension. The proposed flow is adapted to the
existing Create workflow and one project-scoped Library, not a separate app.

## Initial P0 slice

- Implemented: multi-GLB Library version selection and file import; Three.js scene
  viewport with hierarchy, object roles, editable transforms and transform gizmo;
  local draft restore; bounded undo/redo; immutable scene versions with parent
  links, source hashes and optimistic save conflict detection.
- Implemented: explicit orbit/dolly shot list, subject selection, camera distance
  and angles, studio/moonlight lights, optional clearly labelled studio floor.
  No automatic populated environment or semantic storyboarding is implied.
- Implemented: Cycles CPU headless subprocess in the existing durable scheduler,
  PNG frame receipts, checked frame reuse, real frame progress, FFmpeg H.264,
  FFprobe contract checks and full decode; version-scoped atomic MP4 delivery,
  manifest and existing Library/Production integration. Source GLBs are immutable.
- Implemented: native 1080p/24/64-sample Maximum preset and visibly separate native
  360p/12/8-sample Draft preset. No silent fallback, AI upscaling or quality claim.
- Implemented: source .blend plus reproducible scene JSON; silent output is
  explicit. Audio is not represented as complete.
- Verification: backend test creates a real 8-second/96-frame two-GLB cinematic
  using licensed Khronos fixtures and two camera movements; tests full decode,
  atomic delivery hash and 96-frame reuse on actual retry. Final Windows UI and
  packaging evidence must be recorded separately before shipping this slice.

## Audit

Existing global scheduler, subprocess lifecycle, GPU lock, CPU slots, production
control, SQLite assets/artifacts/jobs, project scope, local auth, Library and
immutable 3D pipeline remain in use. Scene snapshots are additive artifacts in
the existing database; no second queue or Library. Scene ID/hash/source hash and
renderer script hash are pinned in each job. Imported code/workflow archives are
not executed. Inputs are self-contained GLB candidates already validated by AFS.

Blender 4.5.14 and local FFmpeg/FFprobe are installed. Media discovery currently
uses environment overrides, PATH and the existing local TRELLIS installation's
media binaries; packaging does not bundle those binaries or install a tool.
GPU video/audio inference is not installed/verified by this slice. Render CPU
work can overlap other jobs through existing resource limits and does not hold
the heavy GPU slot. There is no mid-inference AI resume claim.

## Open acceptance and next slices

1. Complete P0: exact prompt-based camera revisions and ripple cuts; preserve
   source, old video and per-shot cache while invalidating only affected work.
2. Modular environment assembly, connectors/ground snap/collision/visibility
   diagnostics, reusable scenes and authored anchors. Initial numeric transforms
   do not prove gap-free geometry or unobstructed camera framing.
3. Real named Aetherward hero/boss/crystal and 10+ environment modules, sanctuary
   scene and approved 8–15-second render. Fixture instances are not replacements
   for these missing game assets. A manifest entry is not a generated GLB.
4. Timeline trim/split/reorder/replace, proxies, keyframes, comparisons,
   publication/restore, per-shot caching and hard shutdown recovery acceptance.
5. Audio import and cue sheet, multitrack mix and synchronized edits, stems,
   ducking, real metering, subtitles from verified timing and voice profiles.
   Music/SFX/TTS adapters remain optional and require model/license/hardware tests.
6. ComfyUI ownership/runtime audit, selected-model download and verified Wan 2.2
   5B T2V/I2V before enabling AI video; optional LTX/Hunyuan later. No paid fallback.
7. Wider aspect ratios, target presets, alpha/stems, object/camera/VFX refinements,
   shot identity locks and maximum quality/throughput benchmarks.

## Limits

Initial prompt text is preserved as direction; camera behavior comes from the
visible shot controls, not an unverified local LLM. Imported animation can play;
unrigged objects do not gain walking, fighting or believable motion. No arbitrary
BLEND import, retargeting, music, TTS, lip sync, complete map or AI video is
claimed. .blend contains the composed source scene; scene JSON/shot parameters
are needed to reproduce the animated camera sequence. The first source pose
thumbnail is an actual rendered frame, not artistic approval. Source/input
commercial rights remain separate. Aetherward's gameplay architecture is not
changed and a video is not a playable Unity level.

Earlier auto-rig audit continues separately: official UniRig source was checked
out under `.local/research`, not installed into existing environments; WSL is
absent. Native CUDA extension dependencies and embedded licenses still need
review. No UniRig/SkinTokens weights have been downloaded or a rig claimed.
