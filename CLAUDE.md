# Asset Forge Studio development contract

User requirements take priority. Preserve the current local AI pipeline, immutable artifacts, existing game data, per-engine Python environments and Quality Lock. No paid AI APIs/cloud inference. Universal Expansion V2 Reviewed now authorizes additional modules in evidence-based vertical slices; do not present planned modules as working.

## Mandatory Windows completion loop (user instruction, 2026-10-21)

Every completed feature, fix, UI improvement, backend change or significant refactor must pass:

1. Relevant automated tests.
2. Frontend TypeScript checks and production build.
3. Backend tests where applicable.
4. Production Windows desktop build (Tauri 2 preferred).
5. Launch the newly built desktop executable and smoke-test the affected feature.
6. Report application version, build/smoke results, Git commit and artifact location.
7. Commit and push the verified feature to its authorized working branch. Universal work MUST stay on `feature/universal-expansion-v2-reviewed`; user-authorized stable UI/default/export ports use `release/pc-stable`. Do not merge or push changes to main without a new explicit user instruction.

A Vite/browser preview alone is not desktop acceptance. If desktop build fails, fix and rebuild before calling the feature complete. Record real GPU inference separately from shell smoke tests. Never claim a launch, output, quality level or approval without evidence.

The user requires two separate desktop distributions. Preserve PC 0.3.1 files at `dist/windows/stable/` and `dist/windows/latest/` as rollback copies. New stable releases use `dist/windows/stable/latest/` and branch `release/pc-stable`; the user explicitly authorized the UI refinement, empty fresh workspace and project-scoped export changes for Stable too. Universal module development stays on `feature/universal-expansion-v2-reviewed`, product `Asset Forge Studio Expansion`, identifier `com.assetforgestudio.expansion`, output `dist/windows/expansion/latest/`; do not merge to main. Stable fixes can be ported independently without bringing unfinished generators across. Failed staging builds must not replace known-good builds. Expansion settings/library default to `%LOCALAPPDATA%/AssetForgeStudioExpansion`, Stable to `%LOCALAPPDATA%/AssetForgeStudio` or its configured library. Fresh libraries have zero sample projects; preserve existing projects and legacy-data migration. Both distributions retain the same global GPU resource lock. Do not bundle multi-GB weights on each build. Back up databases before schema migration. Do not silently move or delete existing data.

Single and Batch share one EffectiveGenerationConfig resolver and one GPU Resource Scheduler. Default one heavy GPU job; bounded CPU/I/O overlap is allowed. Scheduler/retry must not change engine/checkpoint, precision, resolution, steps, candidate count, texture or Blender stages. OOM/resource shortage blocks rather than downgrades quality. Human approval remains separate from technical QA and Meshy parity.

Read `docs/IMPLEMENTATION_PLAN.md`, `docs/UX_REDESIGN.md`, current progress and Windows development docs before modifying related workflows. Git origin uses the already authenticated SSH transport for Winka173/Asset-Forge-Studio. Never log private keys/tokens.

## Universal Expansion V2 Reviewed

`doc/Asset_Forge_Studio_Universal_Expansion_Master_Prompt_V2_Reviewed.md` supersedes the earlier Universal specification. Audit and validate the existing Single/Batch baseline first. Implement shared typed manifests/capability routing and the first genuine Unity validation slice before opening other generators. Keep unsupported types Planned/Experimental/Unavailable, local-only inference, one shared heavy GPU slot, scoped optional MCP, explicit license/commercial gates, opt-in heavyweight installs and no production game writes. Maintain `docs/UNIVERSAL_EXPANSION.md` with tested/untested phase checklists. Each completed feature still requires a fresh Windows build, real native smoke and commit/push on this feature branch.
