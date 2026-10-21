# Current implementation - 2026-10-22 (Asia/Saigon)

The current Windows candidate is 0.7.1 on main. The latest user priorities are a genuinely empty personal Library, one stable asset item with nested stages/versions, and a shorter stepped Create flow with consistent spacing. Test runs live under .local with independent desktop configurations; no sample project is seeded into production.

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
