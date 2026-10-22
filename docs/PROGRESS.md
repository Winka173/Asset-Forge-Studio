# Windows 0.8.17 - reference purpose routing - 2026-10-22

Fixed Single Text+Image routing: default new-subject mode creates a separate SDXL concept with measured reference palette, rather than silently reconstructing a style-reference object. Explicit image reconstruction remains available; original prompt and source hashes are retained. Bilingual architecture noun hints are deterministic rules, not an LLM or complete translation. Full semantic style transfer remains unavailable. 96 tests, TypeScript/Vite, Windows packaging/generic smoke and native Create submission/custom-select explanation/restart passed. Actual local Maximum SDXL generated a 1024px castle concept from the Vietnamese castle prompt and tower reference colors in 39.19 seconds (5.60 GB allocated, 7.85 GB reserved in decimal units). This is technical generation evidence, not artistic or Meshy approval. The full Maximum TRELLIS/Blender/export run is still in progress. See evidence/castle_reference_concept.json and reference_routing_native.json.

---

# Windows 0.8.16 - 2026-10-22

95 backend tests and TypeScript/Vite pass. Packaged Windows build and generic smoke pass. Native actual CPU render verifies central generation activity instead of automatic reference imagery, opt-in reference preview, reduced motion, refresh restoration and animation stopping on completion. This is activity artwork, not an incremental generated mesh. Native Audio Director acceptance imports nine real QA recordings, saves/mixes four buses, plays AAC MP4, mutes music, ripple-cuts audio/video, reuses Blender frames and restores cue/version history after restart. See evidence/generation_preview_native.json and evidence/cinematic_audio_native.json. AI audio generation, TTS integration, semantic style transfer and artistic quality remain unverified.

---

# Cinematic targeted revision work - 2026-10-22 (Asia/Saigon)

Implemented deterministic zoom-by-interval, frame-based ripple cut and scoped camera/violet-rim reveal revisions in the existing Video Studio. Immutable scenes retain source hashes, original prompt, quality, motion duration and source frame offsets. Per-motion caches reuse unaffected frames; shared cache leases serialize overlapping writers while retaining the CPU scheduler. Existing delivery manifest edits are rejected. Actual backend renders verify zoom 24 new/72 reused, cut 0 new/72 reused and reveal 48 new/48 reused from an eight-second two-fixture scene. Preliminary packaged UI acceptance passed preview/no-job, Generate Revision, actual MP4 playback, source comparison, cuts and restart. Windows 0.8.15 passed all 94 tests, production build, generic smoke and the final affected native rerun: preview starts no jobs, zoom renders 24/reuses 72 frames, ripple cut renders zero/reuses 72 frames, source comparison plays actual MP4s and all three versions persist after restart. See evidence/cinematic_edits_native.json. No general LLM, audio, fog or generated-motion claim is made. See VIDEO_STUDIO.md.

---

# Model/tool update work - 2026-10-22 (Asia/Saigon)

Settings now compares upstream model revisions, engine source commits and installed tool versions. Portable media installation uses the shared CPU queue, SHA-256-pinned side-by-side files, actual H.264 encode/probe/decode, idle-only activation and rollback. Real backend acceptance upgraded an isolated Library from existing FFmpeg 7.1 to n9.0.2 and decoded the existing 96-frame Blender cinematic. No installed AI environment, weights or user game data were modified. Windows 0.8.14 passed all 92 tests, production packaging, generic native smoke and affected native acceptance: upstream results visible at 1280/1536 widths, opt-out without inference, real portable download/hash/codec QA, activation, restart persistence and rollback. Native testing found and fixed an asynchronous checkbox reset. Rollback disables automatic installation so a later daily check cannot undo it. See evidence/updates_native.json. See UPDATES.md.

---

# Video Studio in progress - 2026-10-22 (Asia/Saigon)

New authority: doc/Asset_Forge_Studio_Video_Studio_Cinematic_Director_V1.md, including Audio Director. Initial P0 work implements pinned multi-GLB scene composition, hierarchy/transforms/gizmos, immutable snapshots, explicit orbit/dolly storyboard, shared CPU Blender rendering, checked frame reuse, H.264/FFprobe/full decode, atomic per-version delivery and Library/Production preview. Backend acceptance rendered a real 8-second two-source fixture cinematic and reused all 96 frames on retry. Windows 0.8.13 passed all 89 tests, packaged smoke and affected native acceptance: two GLBs, transform undo/redo, immutable versions, paused queue/restart, actual 96-frame render, MP4 playback and Library reopening. Evidence: evidence/cinematic_native.json. See VIDEO_STUDIO.md.

Remaining: modular environment assembly and real Aetherward cast/modules, exact prompt camera/time edits, per-shot invalidation, timeline/audio import/mixing/voices, verified AI video/audio adapters, richer render QA and stress recovery. No complete Video Studio, generated sanctuary, AI video, soundtrack or auto-rig claim is made. Existing 0.8.12 animation/3D features remain preserved.

---

# Unity animation work - 2026-10-22 (Asia/Saigon)

Version 0.8.12 adds an explicit, limited existing-animation Unity profile in Library/Production. It reuses the shared CPU scheduler and imports a single untextured Generic skinned clip through Blender FBX, validates real deformation/metric scale/weights, cold-reopens Unity, and tests package import in a second empty project. The authoritative GLB is preserved and default GLB Only does not invoke Unity. Package availability is bound to the exact source version. All 87 backend tests, packaged Windows smoke and native paused-queue/restart/real-Unity/package/export/version-scope acceptance passed. See UNITY_ANIMATION.md and evidence/unity_animation_native.json.

Auto-rigging, humanoid retargeting, new motion generation, textured-animation material parity, root-motion/foot-contact quality and player performance remain open. This technical slice does not close artistic acceptance or broader engine/map/VFX work.

---

# Current work - 2026-10-22 (Asia/Saigon)

The shipped 0.8.10 baseline includes one admitted Production row per asset, real outside pipeline progress, intentional generation attempts with idempotent retries, persistent all-project notifications and validated local Blender/Unity tool discovery. Actual Runavelle 349-file native tests exercise admission and restart without starting 349 GPU jobs. Map versions retain immutable source plans and version-specific real Unity captures.

The 0.8.11 slice adds existing skinned clip retiming through Refine, the shared CPU scheduler, actual headless Blender deformation checks, staged GLB export and explicit publish/rollback. All 86 backend tests, the final packaged Windows smoke and the native pause/restart/refine/playback/publish/rollback acceptance passed; see ANIMATION_RETIME.md and evidence/animation_revision_native.json. This is existing-motion editing, not automatic rigging, retargeting or new motion generation.

Still open: artistic/Meshy acceptance; full multi-engine/commercial benchmark clearance; local visual prompt-fidelity evaluation; auto-rig/retarget and new combat animation; richer text-driven maps and runtime VFX performance. Unreal remains deferred. Long-duration production and arbitrary power-loss recovery coverage remain incomplete. Historical sections below record earlier milestones and do not override this status.

---

# Shared settings and text-first Home - 2026-10-22 (Asia/Saigon)

Windows 0.8.7 passed 75 backend tests and bundled native GLB/export/restart smoke. Project workflow changes now patch only edited fields under one SQLite write lock; nested checkpoints merge independently. Single, Batch and Settings synchronize validated values rather than overwriting another panel's newer recovery policy. The legacy full-settings endpoint and stored format remain compatible. Concurrent partial-update tests verify unrelated settings survive and invalid values leave the record unchanged.

Actual packaged UI acceptance enabled Auto-resume in Settings, changed Single checkpoints, changed Batch mode, reopened Single and Settings, then closed/reopened Windows: all settings persisted, with zero generation jobs. Empty Home now starts with a prompt, optional references and one primary Create action instead of competing image-first CTAs and repeated empty sections. Native screenshots confirm that primary action is visible at 1280x800 and 1536x1000. Evidence: evidence/workflow_settings_native.json. The 0.8.6 responsive workspace rerun additionally passed the actual 349-source manifest, real Archer preview, clean user profile and five affected workspace layouts; evidence/workspace_native.json.

Unrestricted semantic map generation, playable map walkthrough, automatic humanoid rigging/retarget quality, cited reference-game research, automatic standalone transient native repair and Meshy artistic acceptance remain open. These are not proved by UI, procedural FX or the imported motion fixture.

---

# Safe Windows exit - 2026-10-22 (Asia/Saigon)

Windows 0.8.6 passed 74 backend tests, bundled native GLB/export/restart smoke and real Unity close/reopen acceptance. Closing with active work now temporarily holds scheduling, keeps the window open until the current stage saves, then exits without cancelling queued assets. A visible status banner offers Keep studio open; this restores the previous admission state. Independent close generations prevent an earlier cancelled close from racing a later close request.

The temporary exit hold is distinct from an explicit Pause. Recovery restores only the temporary hold, then applies each project's existing auto-resume policy. Later explicit Pause/Resume is never silently reverted. The native test actually generated two effect packages: cancelled a pending close using Keep Open, closed again during the first Unity stage, verified that stage completed before exit, reopened with explicit auto-resume enabled, and observed only the pending second job run. The first package hash remained unchanged, only two jobs existed, no jobs were cancelled/blocked, and artistic status remained not_reviewed. See evidence/exit_checkpoint_native.json. Default manual recovery and real forced-process interruption were verified separately in 0.8.5; no Windows OS reboot or mid-inference resume is claimed.

Open gates remain universal semantic map generation, runtime map walkthrough, automatic humanoid rigging/retarget quality, reference-game research integration, standalone transient native repair and Meshy artistic acceptance. Existing procedural maps/effects and imported-clip preview must not be presented as completion of these gates.

---

# Standalone recovery - 2026-10-22 (Asia/Saigon)

Windows 0.8.5 passed 71 backend tests and native GLB/export/restart smoke. Startup now holds queued standalone GPU work (effects/maps/manual engine jobs) unless the project explicitly opted into auto-resume, while explicit Pause remains effective. CPU-only validation remains eligible. Settings exposes the project recovery policy and explains that paused work still needs Resume. Select explanations cover interface preferences, and effect previews open on a real visible captured frame.

Actual forced termination of an isolated packaged Windows process left the active Unity attempt interrupted and pending sibling work paused after reopening. Previously completed packages remained unchanged. One Unity Package Manager attempt failed with "Failed to resolve packages: operation cancelled"; this was not counted as success. A manual Retry into a new immutable attempt subsequently generated a real package, passed empty-project import validation, retained Maximum config and preserved all completed outputs. Evidence includes the interruption, runtime failure and successful continuation: evidence/fx_recovery_interrupted.json and evidence/fx_recovery_native.json. This is forced-process recovery, not a Windows OS reboot or mid-inference checkpoint claim. Automatic transient standalone repair is not established by this manual Retry test.

---

# Effect alternatives and playback - 2026-10-22 (Asia/Saigon)

Windows 0.8.4 passed 69 backend tests, native GLB/export/restart smoke and real effect acceptance. Effects now request 1-5 Maximum-quality seed alternatives within one stable asset and the shared one-heavy-GPU scheduler. Admission is durable/idempotent across partial failures. Native acceptance actually generated two different Ice alternatives, imported each Unity package into an empty project, compared real frame hashes, selected an alternative and generated an inherited Fire revision. Previous packages remained byte-identical. Play/pause, frame stepping, speed, non-loop end, grouped completion inbox and Windows close/reopen passed. Evidence: evidence/fx_candidates_native.json. This is procedural Unity output, not arbitrary AI VFX or target-device artistic/performance acceptance.

The UI also has a recoverable error boundary instead of an unhandled blank rendering screen. Captured effect camera/background remain baked; the interface says so explicitly.

---

# Workspace utilities acceptance - 2026-10-22 (Asia/Saigon)

0.8.3 delivered on main adds project-scoped Ctrl+K search, Home continuation, grouped opt-in production notifications, saved Library filters/scroll, reload-safe archive Undo, stable keyboard review order with a separate review-later tag, and Focused/Detailed/reduced-motion preferences. Select explanations are now portalled and bounded by the viewport. Bulk actions explicitly say loaded assets when the backend result is capped; no misleading all-assets claim beyond the loaded set. Metadata updates reread under a SQLite write lock and preserve worker-owned masters and revision history.

Browser acceptance used the actual 349-prompt Runavelle file plus licensed real skinned GLBs in an isolated Library: navigation, cross-project search isolation, review tag persistence, archive/Undo after reload, scroll restoration, settings persistence, actual model rendering and unchanged source hashes passed with zero inference jobs. The packaged Windows test also passed the full utility workflow and close/reopen persistence, with 66 backend tests and native GLB/export smoke passing; no new AI-generation or artistic-quality claim follows from these UI checks.

---

# Preview update - 2026-10-22 (Asia/Saigon)

Windows 0.8.2 passed the 65-test backend suite, packaged native GLB/export/restart smoke, and real licensed GLB animation/rig viewer acceptance. Actual clip playback, scrub, non-loop stop, speed selection, skeleton canvas pixels, joint pose changes and unchanged source hashes were checked; the model reloads after closing and reopening Windows. Static models retain their existing viewer and do not show nonfunctional motion controls. Technical fixture: Khronos/Cesium Rigged Simple, CC BY 4.0; it is not an AI-generated character, automatic rigging or retarget quality proof. Source and license: evidence/motion_fixture_license.json; native result: evidence/motion_native.json.

The next approved UX slices remain command search, resume/continue work, saved filters/scroll, reversible archive, continuous review and grouped notifications. General text-to-map/VFX, multi-result routes for these types, research integration and actual auto-rig/retarget still require independent implementation and real-output acceptance.

---

# Current implementation - 2026-10-22 (Asia/Saigon)

Windows 0.8.1 passed 65 backend tests, the packaged native smoke, and affected-feature acceptance on main. Create supports 1-5 result seeds; Preview/Refine/History, compact Batch, explanatory searchable selects and the graphite/amber spacing pass are implemented. The native legacy-seed/deep-link test confirms a saved model opens the correct workflow and Refine does not start generation. The latest user priorities are a genuinely empty personal Library, one stable asset item with nested stages/versions, and a shorter stepped Create flow with consistent spacing. Test runs live under .local with independent desktop configurations; no sample project is seeded into production.

The previous mixed workspace data contained 1,048 assets from three 349-item imports plus one older asset. It was moved to a recovery archive at the user's explicit reset request. Desktop now points to %LOCALAPPDATA%/AssetForgeStudio/Library. Original tools, weights, environments and external game directories were preserved. Same project/source ID reuses the asset; identical source/configuration reuses the import. Re-import appends provenance without overwriting a current master, original prompt or concurrent worker changes.

Create has workflow selection, prompt/reference input, then generation settings. Prompt and step restore across refresh; clicking the sidebar Create begins a fresh draft. Advanced controls remain available. Production nests standalone stages under one stable asset and persists asset Pause across stage handoff. Single-item groups do not create an extra duplicate heading row.

Editable procedural Unity sword-slash recipes now have actual native output for fire, ice, lightning, wind, earth and poison. Each uses the shared heavy-GPU scheduler, real 24-frame captures, cold reopen and package import into an empty project. Recipe revisions preserve prior parameters and immutable outputs. This is a procedural weapon demonstration, not validated character animation, retargeting, unrestricted prompt-to-VFX, artistic acceptance or target-player performance. See the release evidence for final native UI validation.

Still unfinished: Meshy-quality artistic acceptance; comprehensive engine/commercial benchmark clearance; local visual prompt-fidelity inference; rig/deformation/retarget and character combat animation; richer map biomes/rivers/material/performance. Unreal remains deferred. Historical entries below are superseded by this section.

---

# Current verified baseline - 2026-10-22 (Asia/Saigon)

Stable 0.6.0 is unified on main at a98a4e0. 55 backend tests and native Windows build/smoke passed. Real 349-source import/admission (312 primary, 37 FUTURE), shared Single/Batch queue, incremental GLB delivery, stage checkpoint recovery, Production/Library UI, separate technical/artistic statuses, short-prompt enrichment, CPU scale revisions, staged publication/rollback and Create reset are recorded in evidence/stable_0_6_release.json. No full 349-GPU development run was launched.

Existing Unity import and procedural World Plan slices were previously validated with native scenes, prefab instances, terrain and navigation; they remain experimental. They do not implement unrestricted prompt-to-map generation.

Still unfinished: Meshy-quality artistic acceptance; comprehensive multi-engine benchmarks / commercial clearance; local visual prompt-fidelity inference; editable runtime VFX; rig/deformation/retarget and combat animation; map biomes/rivers/material/performance expansion. Unreal remains deferred by the user. Optional local semantic inference has an adapter but no verified installed model.

The user now authorizes the next quality roadmap, starting with hash-bound prompt requirements and real measured checks, then a Unity combat/effect slice. Prior no-merge and no-new-module directions below are historical and superseded.

---

## Historical checkpoints

# Current verified state ? 2026-10-21

The entries below this section are historical checkpoints, superseded where noted here.

- Windows desktop is now primary (user's migration request supersedes Web-first). Version 0.2.1 Tauri EXE, bundled Python backend and NSIS installer build successfully. Actual WebView2 smoke passed: native UI, API authentication, single instance, real Archer GLB viewer, clean shutdown, Library persistence and token rotation. Artifacts: `dist/windows/latest/`; reports: `evidence/desktop_build.json`, `evidence/desktop_smoke.json`.
- Batch Studio has a 14-item explicit manifest acceptance and two genuinely generated local models with Blender GLB/FBX reopen checks. The shared scheduler ran one GPU inference at a time and overlapped Castle CPU Blender with Archer GPU inference. `evidence/batch_real_flow.json` records outputs, resource measurements, overlap and actual ZIP contents. No production artwork approval is implied.
- SDXL local text-to-concept works with the existing isolated environment and cached weights. Concepts require explicit approval; bad turnaround/house results were retained and rejected during QA. Prompt fidelity remains a quality limitation. `evidence/sdxl_local_concept.json` records real inference.
- Backend currently passes 22 tests including Single/Batch immutable config equality, execution/hash guards, explicit quality override, per-item failure isolation, manifest revision safety and desktop authentication. Actual native Maximum Single-versus-Batch inference passed with identical locked config and identical raw geometry/attributes in this paired trial. GLB byte hashes differ; future exact equality is not guaranteed. See `evidence/maximum_quality_comparison.json`, `desktop_inference.json` and `desktop_output.json`. Version 0.2.1 fixes a native CSP texture-loading failure; both real models now reopen with textures and export successfully. Missing external workspace startup was also tested (`desktop_startup.json`).
- Unity CPU import of actual FBX/LODs passed (see `evidence/unity_import.json`); GPU screenshots/gameplay performance remain unverified. Research TRELLIS v1 and Hi3DGen both ran real geometry and Blender export, but are not promoted to production engines merely for running.
- Git SSH push is working; tested Windows/Batch milestone committed and pushed as `ae11062`. Future changes require test/build/native-smoke before commit/push.
- Meshy reference is an image only. No Meshy geometry/PBR equivalence or user artistic approval has been established. SF3D remains gated; missing-engine workflows never fake success. Character/Animation/Map/VFX remain outside scope.

---

# Tiến độ thực tế

- Đã hợp nhất v1/v2; Local Web App trước, Tauri sau.
- Archer Tower đã chạy bằng TRELLIS.2 community CPU offload (512/1024, nhiều seed) và TripoSG trên RTX 5070 Ti 16 GB. Kết quả thử nghiệm chưa được duyệt chất lượng hoặc quyền thương mại toàn chuỗi.
- Đã có GLB thật, Blender headless, native geometry master 6.702.958 tam giác, LOD0–3, FBX có texture, kiểm tra mở lại và render sáu góc ở hai độ phân giải. Normal/AO bake mới thử riêng trên một LOD.
- Web local: import, viewer Three.js, review, multi-seed queue tuần tự, cancel/retry, tự nối AI → Blender, launcher Windows. Kiểm thử: 11 pytest, 1 Playwright; thêm luồng browser thực với TripoSG.
- Bằng chứng: [all_runs.json](evidence/all_runs.json), [ảnh so sánh](evidence/archer_tournament.png), [web thật](evidence/real_workbench.png), [luồng browser thật](evidence/web_real_flow.json). QA box có nhãn rõ và database riêng.
- Người dùng xác nhận chỉ có ảnh Meshy, không có GLB đối chứng. Đối chiếu ảnh không chứng minh geometry/mặt sau/PBR tương đương Meshy. Chưa có duyệt chất lượng của người dùng; gate chất lượng còn mở.
- Giới hạn: chi tiết mềm, vật liệu/crystal chưa đúng, mặt sau suy đoán, geometry vẫn còn lỗi sau phân tích weld. Unity import chưa thử. Chiều cao 10 m là cấu hình thử chưa duyệt game.
- SF3D chưa chạy do weights gated/access. Đang audit TRELLIS v1 và Hi3DGen trước; SPAR3D, Hunyuan3D-2mv, PartPacker riêng, không cài chung environment.
- Chưa triển khai Character Studio, Animation Studio, Map hoặc VFX. Engine chưa chứng minh lợi thế không tự động trở thành tích hợp chính thức.
- Commit từng chức năng vào main local. Push GitHub chưa được vì thiếu thông tin xác thực HTTPS.
- UI/UX studio mới đã triển khai sáu trang, project CRUD và cô lập dữ liệu, draft, Library, phiên bản/Master, gallery candidate thật, diagnostic viewer, export presets và keyboard shortcuts. 15 pytest + Playwright PASS; luồng Archer Tower chạy inference thật và mở lại sau restart backend PASS. Bằng chứng riêng tại `docs/evidence/studio_real_flow.json` và `studio_exports.json`.
- Text-only → concept chưa tích hợp; chưa tuyên bố chỉ nhập prompt là tạo được model. Unity presets đã xuất/mở lại file thật nhưng chưa duyệt chất lượng decimation hay import Unity.
- TRELLIS v1 và Hi3DGen cấu hình StableNormal/YOSO ban đầu đều đã tạo geometry GLB thật trên máy, environment riêng; có Blender render sáu góc và GLB/FBX reopen PASS. Chưa đủ benchmark multi-seed/turntable đầy đủ và duyệt lợi thế để tích hợp chính thức.
