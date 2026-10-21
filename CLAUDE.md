# Asset Forge Studio development contract

User requirements take priority. Preserve the current local AI pipeline, immutable artifacts, existing game data, per-engine Python environments and Quality Lock. No paid AI APIs/cloud inference. No Character/Animation/Map/VFX expansion.

## Mandatory Windows completion loop (user instruction, 2026-10-21)

Every completed feature, fix, UI improvement, backend change or significant refactor must pass:

1. Relevant automated tests.
2. Frontend TypeScript checks and production build.
3. Backend tests where applicable.
4. Production Windows desktop build (Tauri 2 preferred).
5. Launch the newly built desktop executable and smoke-test the affected feature.
6. Report application version, build/smoke results, Git commit and artifact location.
7. Commit and push the verified feature to main.

A Vite/browser preview alone is not desktop acceptance. If desktop build fails, fix and rebuild before calling the feature complete. Record real GPU inference separately from shell smoke tests. Never claim a launch, output, quality level or approval without evidence.

Keep the last known-good desktop build in `dist/windows/latest/`; failed staging builds must not replace it. Do not bundle multi-GB weights on each build. Persistent data belongs in user-configured storage or `%LOCALAPPDATA%/AssetForgeStudio`, never a build/temp/install directory. Back up databases before schema migration. Do not silently move or delete existing data.

Single and Batch share one EffectiveGenerationConfig resolver and one GPU Resource Scheduler. Default one heavy GPU job; bounded CPU/I/O overlap is allowed. Scheduler/retry must not change engine/checkpoint, precision, resolution, steps, candidate count, texture or Blender stages. OOM/resource shortage blocks rather than downgrades quality. Human approval remains separate from technical QA and Meshy parity.

Read `docs/IMPLEMENTATION_PLAN.md`, `docs/UX_REDESIGN.md`, current progress and Windows development docs before modifying related workflows. Git origin uses the already authenticated SSH transport for Winka173/Asset-Forge-Studio. Never log private keys/tokens.
