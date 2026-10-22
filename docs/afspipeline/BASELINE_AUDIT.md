# Adaptive pipeline baseline — 2026-10-22

Status: VERIFIED code/log inventory; new adaptive implementation is not yet a release.

Existing application: main at 57e61c7, packaged Stable 0.8.20. Tauri 2.12.3 CLI, React/TypeScript/Vite/Three.js, FastAPI 0.156.4, Python 3.11.5, SQLite schema v3. Windows build 26200 (Python identifies the NT family as Windows-10), RTX 5070 Ti 16303 MiB, NVIDIA driver 610.88, 61.61 GiB physical RAM. Audit free disk 96.0 GiB. Blender evidence identifies 4.5.14 LTS; rediscovery must validate the executable. Unity's existing integration is pinned to 6000.4.8f1; Unreal installation was deferred by the user.

Code authorities: `apps/api/automation.py` (shared Single/Batch coordinator), `jobs.py` (one cross-process heavy GPU slot, bounded CPU slots), `store.py` (existing SQLite/artifacts), `statuses.py` (independent status axes), `export_profiles.py` (incremental atomic GLB delivery), `revisions.py` (versioned edits/publication), `engines/quality.py` (immutable quality resolver), `pipelines/blender/process_asset.py` (headless processing/reimport/renders). Desktop lifecycle: `src-tauri`, `scripts/desktop.ps1`; UI: `apps/web/src/studio.tsx`, `production.tsx`.

Pre-change Auto routing pinned installed textured TRELLIS.2 before TripoSG. It did not constitute a benchmark-based strategy planner. TripoSG requires an alpha input and has no AI PBR output. Existing mesh edits support uniform height changes and retiming existing skinned clips; arbitrary material editing was not implemented.

Local Qwen3-VL 4B Instruct Q4_K_M runs through managed Ollama, CPU only, context 8192, keep-alive zero; no source transmission to cloud. SDXL 1.0 uses a separate environment. TRELLIS.2, SDXL and research engines are isolated. TripoSG/TRELLIS v1/Hi3DGen: Torch 2.8.0+cu128, Diffusers 0.32.2, Transformers 4.46.3. TRELLIS.2: Torch 2.8.0+cu128, Transformers 4.57.3. SDXL: Torch 2.11.0+cu128, Diffusers 0.41.0, Transformers 5.20.2. These are installed package metadata, not fresh model-load verification.

Actual user Library was inspected read-only: castle batch 076ee4256aec44308b43fd3d8c7df7a4 stopped at concept layout. Both concept jobs and local CPU checks completed; no inference/Blender job existed. No evidence supports blaming that failure on TRELLIS/VRAM. Preserve this Library and the running user's desktop.

Recent isolated attempts: `.local/quality-flow-20261022-v21` blocked at layout; v21b reached 3D but was explicitly interrupted for review; v21c completed local interpretation/planning but concept was interrupted. These are failures/interrupted attempts, not accepted assets. Earlier real castle GLB remains in `.local/castle-reference-acceptance/Library`; evidence `docs/evidence/castle_reference_3d.json`. Historical engine results: `docs/evidence/all_runs.json`; original `data/generation` paths no longer resolve in this workspace, so those records are historical, not newly verified environments.

Existing technical QA validates real GLBs and preserves topology warnings. It does not prove absence of self-intersections, UV overlap, physically plausible PBR or Meshy parity. No Meshy GLB was supplied. No approved artistic ground-truth dataset exists for calibrating Qwen.

Recovery follow-up: historical `data/generation` artifacts were subsequently found under `.local/data-reset-backups/20261021T181054Z/workspace-data/generation`. The seed-43 original tower GLB, native geometry, source PNG and generation receipt have now been checked read-only against their hashes, see `../evidence/tower_quality_preservation.json`. Original historical paths remain stale; use the recovery receipt's actual paths. Recovery is not a fresh inference or artistic reapproval.
