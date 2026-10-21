# AFS Unity Editor import slice

Verified target: **Unity 6000.4.8f1, Built-in rendering, Windows 11**. Other installed Editors and URP/HDRP are not advertised as compatible. This package is editor-only and is not required in a deployed game.

In Create, select a **Blender processed LOD0** candidate, expand **Unity native package & validation**, then **Validate in Unity**. The AFS backend starts the pinned Editor in a fresh project under the job directory. GPU previews use the same heavy-GPU lock as Single/Batch inference and GPU Blender. CPU-only import is supported through the preview checkbox. Requests are idempotent; retries create immutable attempts, and changed source/toolchain hashes block instead of modifying quality.

The tested input profile is four real FBX LODs and one material with actual basecolor and metallic/roughness textures, up to 4K. The importer preserves source bytes; metallic B becomes Unity Standard metallic R, and inverse roughness G becomes smoothness A. No absent normal/AO/emission maps are fabricated. Multi-material, shape-only or larger-texture translations remain blocked for this profile until tested.

Actual Editor output:

- `editor_project/Assets/AFS/Output/AFS_Validated.prefab`: imported LODGroup with four mesh levels and a bounds-based BoxCollider.
- `editor_project/Assets/AFS/Output/AFS_Validation.unity`: editable native scene, metric scale, fixed validation lighting/cameras when GPU render is requested.
- `AFS_Standard.mat`, original FBX/textures and converted metallic/smoothness data.
- `output/AFS_Asset.unitypackage`: exported by `AssetDatabase.ExportPackage`, including native assets, source files and GUID metadata. Import into a game only as an explicit user action, preferably in a test project first.
- `output/AFS_Editor_Importer.zip`: editable UPM package source. Extract and add the package from disk if using the importer independently.
- Import and cold-reopen JSON reports; three actual Editor renders at 1280×720 / 2560×1440; source/config/toolchain hashes, resource measurements and logs.

AFS starts a **second Editor process** to reopen the serialized scene/prefab and check scale, LODs, collider and material references. Success is not reported until both Editor runs and file validation pass. No production game path is accepted or modified by the API.

API: `POST /api/platform/assets/{asset_id}/unity-import` with `artifact_id`, stable `request_id`, `render_gpu` and the pinned profile. `commercial: true` is blocked until the complete source/model/reference provenance chain is cleared. The existing Unity Editor license is used; AFS does not activate, copy or change licenses.

Reproduce the actual native UI acceptance after building Windows:

```powershell
node desktop/verify-unity.mjs
```

This test uses the existing real Archer Maximum QA library, submits the actual import from the Tauri UI, observes the shared GPU lock, checks a native package HTTP range, verifies unchanged source bytes, closes/reopens the application and checks the saved job/previews. Evidence: `docs/evidence/universal_unity_native.json` and the actual Unity screenshots. The test is not a clean-machine installer test, mobile player FPS measurement, artistic approval or Meshy comparison.
