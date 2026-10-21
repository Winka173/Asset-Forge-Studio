# Universal Expansion V2 Reviewed — implementation ledger

Work branch: `feature/universal-expansion-v2-reviewed`, based on `d1b1e49`. User explicitly forbids merging into main for now. The complete source specification is [V2 Reviewed](../doc/Asset_Forge_Studio_Universal_Expansion_Master_Prompt_V2_Reviewed.md); it supersedes the prior Universal prompt and earlier prohibitions on future modules. No production game repository is modified.

The PC 0.3.1 distribution is pinned at `dist/windows/stable/` and source branch `release/pc-0.3.1` (`9b80ef9`). Universal work ships separately as **Asset Forge Studio Expansion** at `dist/windows/expansion/latest/`, using its own Windows identifier and default settings/library. Expansion 0.3.2 passed 28 backend tests, frontend build, packaged native smoke/relaunch and an actual coexistence check while the user's PC edition stayed open; original PC checksums match. See `evidence/desktop_distributions.json` and `evidence/desktop_stable_release.json`. No new AI inference or artistic approval is implied by this release separation.

Stable UI/default/export updates have also shipped separately as PC **0.3.4**, branch `release/pc-stable`, commit `d34bc8d`. The verified portable app is `dist/windows/stable/0.3.4/Asset Forge Studio.exe`: the user's older app remains running from `stable/latest`, so that directory was left unchanged. Both editions have neutral graphite surfaces, custom keyboard-accessible selects, empty fresh libraries and project-scoped delivery ZIPs. See `evidence/pc_stable_delivery.json`, `pc_stable_build.json` and `pc_stable_smoke.json`.

## Audit and prioritized gaps

| Area | Verified starting point | Gap / decision |
|---|---|---|
| Desktop | Windows 0.2.1 EXE + packaged API, native textured viewer, Library restart, 22 baseline tests | Preserve shell, storage, token auth and continuous native build/smoke |
| Single / Batch | Actual Archer Maximum pair, pinned config, real Blender GLB/FBX and six-view renders; shared GPU lock and CPU overlap | Keep inference implementation and immutable masters; extend admission with explicit dependencies |
| Models | Isolated TripoSG, TRELLIS v1, Hi3DGen, TRELLIS.2 community, SDXL environments found; runtime versions audited | v1/Hi3D remain research; SF3D gated. Community TRELLIS/PBR chain not commercially cleared |
| Unity | Editors 6000.4.8f1 / 6000.6.3f1 installed; existing real FBX/LOD/material/prefab CPU validation | Pin 6000.4.8f1 + Built-in first. Integrate isolated Editor jobs, save/reopen, source package and GPU screenshots |
| Unreal | No Editor found in standard Epic or registered install locations | No tested version can be pinned. Native Unreal outputs remain unavailable until an Editor is configured/tested |
| MCP | Blender server configured, live connection test failed; Unity/Unreal not configured | Optional developer integration only; no MCP installs or mandatory runtime dependency |
| Planning / concepts | Actual SDXL local direct adapter, approved-image bypass; structured manifest parser | Ollama/ComfyUI localhost services unreachable. No ComfyUI adapter needed to fill the existing concept route; no LLM weights downloaded |
| New asset modules | No validated complete map/character/VFX/audio/etc. slice | Planned, with no functioning-looking Generate buttons |
| Reference | Supplied Archer image and actual local candidates present | User has no Meshy GLB; no geometry/PBR equality or production artistic approval established |

Local audit: [universal_audit.json](evidence/universal_audit.json). Reopened real Maximum inputs/outputs before changing app code: [universal_baseline.json](evidence/universal_baseline.json). This revalidated existing real artifacts and exports, not a new inference run or an artist approval.

Official MCP source checks are recorded with HEAD, license and last-push timestamps in [universal_mcp_audit.json](evidence/universal_mcp_audit.json). The requested Blender URL redirects to [ahujasid/mcp-for-blender](https://github.com/ahujasid/mcp-for-blender); the repository declares MIT. [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) also declares MIT and currently uses a beta default branch. [DeVoe09/UnrealMCP](https://github.com/DeVoe09/UnrealMCP) declares MIT but has limited history; none of those facts proves an installed or tested integration. Blender's exposed arbitrary-code/remote-asset capabilities are not made an end-user batch dependency. Native Unity automation follows the [official Editor CLI](https://docs.unity3d.com/6000.0/Documentation/Manual/EditorCommandLineArguments.html).

## Execution order and acceptance

1. Add shared manifests and output-aware routing without replacing working generators. Accept when legacy regression tests pass, a real GLB can be snapshotted with matching hashes in the native app, unsupported output contracts are blocked and no GPU work is submitted by dry-run.
2. Integrate a real Unity import/validation job against an isolated AFS-owned project. Accept only after Editor creates and reopens actual prefab/scene/material/LOD assets, exports a native package, records reports and produces real GPU screenshots under the shared scheduler. No production project path is accepted by this route.
3. Add deterministic, editable World Plan and a Runavelle Unity terrain/roads/zones/props slice, proving connectivity, scale and saved native scene. Unreal is a separate unavailable target until Editor access is verified.
4. Character/rig/animation, VFX/materials, then 2D/UI/audio/cinematics: one actual transform/export/import slice at a time. No heavyweight model, license acceptance, paid tool, game-repo write or source deletion without explicit permission.

## Checklist — evidence, not feature count

- [x] Read complete V2 Reviewed; create separate branch; preserve main.
- [x] Revalidate native baseline and audit runtimes/MCP/install locations.
- [x] Versioned typed manifest v2, immutable checksum-verified snapshots, schema export, existing data unchanged.
- [x] Trusted plugin hook SDK, typed stage DAG with cycle/unknown-dependency validation; scheduler waits/blocks on persisted job dependencies.
- [x] Capability Registry separates installed/experimental/planned, source vs weights vs input rights; commercial requests default blocked.
- [x] Output-aware dry-run: approved image skips concept; shape-only PBR requests fail; audio/map do not enter a fake Blender chain.
- [x] Existing deterministic structured planning preserved; unavailable LLM/ComfyUI never causes a paid fallback.
- [x] Project target-engine/profile metadata stored additively and preserved by project edits.
- [x] Foundation Windows 0.3.0 build/native smoke PASS, 27 backend tests; real native dry-run created no jobs and saved/downloaded a manifest with the imported GLB hash. See `evidence/universal_foundation_build.json` and `universal_foundation_smoke.json`.
- [ ] Executable stage-by-stage Manual policies, hash-bound approved-family Auto Batch, configurable fan-out/retry/storage limits. These modes are not represented as working end-user features yet.
- [ ] Local LLM planning adapter after a real installed model is available; structured fallback is already working.
- [x] Integrated Unity Editor import job, native package, saved/reopened prefab and scene, GPU proof and UI report. Real packaged native UI submission, shared GPU lock, idempotent request/refresh, cold Editor reopen and desktop relaunch passed; see `evidence/universal_unity_native.json`. Tested profile: Unity 6000.4.8f1 / Built-in, four FBX LODs, one material and up to 4K basecolor/MR. Unsupported/missing material inputs and commercial presets are explicitly blocked.
- [ ] Unreal native import test — deferred at the user's request; no fake .uasset/.umap outputs.
- [x] Experimental World Plan and native Unity map vertical slice: immutable reviewed plan, 16-bit terrain, roads/build zones, actual same-project prefab instances, native NavMesh paths, cold Editor reopen, real camera renders, project export ZIP and master selection. Packaged desktop refresh/idempotency, cross-project reset and relaunch evidence: `evidence/universal_world_native.json`. See [scope and limitations](WORLD_PLAN_SLICE.md). This is a procedural technical slice, not text-to-map AI or artistic approval.
- [ ] Map expansion: rivers/bridges, biome/scatter generation, production terrain materials, player performance budgets; Unreal when resumed.
- [ ] Rig/deformation/retarget slice and native clips.
- [ ] Editable realtime VFX/material slice.
- [ ] Separate validated sprite/UI/audio/cinematic slices.
- [ ] Mixed-type batch, performance budgets, commercial-provenance approval workflow and production hardening.

Every completed feature requires unit/API tests, frontend typecheck/production build, backend regression tests, a new Windows EXE and actual native smoke, then commit/push this feature branch. Build reports include branch, source state and executable SHA-256; previous known-good builds survive failures. Model weights and engine environments are external and cached. Technical QA does not imply human approval or game-ready status. Target pipelines/versions are supported only where actually tested.
