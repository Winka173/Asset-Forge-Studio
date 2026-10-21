# Asset Forge Studio development contract

## Current release authority (user instruction, 2026-10-21)

The user explicitly authorized merging the reviewed expansion into main and making the newest unified application Stable. This supersedes the earlier branch/distribution separation below. Main is canonical; preserve previous PC/Expansion distributions as rollback copies. Unified product: Asset Forge Studio, com.assetforgestudio.desktop, version 0.6.0. Commit and push completed verified features to main after the native completion loop. Automate noncritical enrichment and technical delivery; only ask for essential unresolved input, new authorization, or an otherwise unapproved replacement of a delivered game version.

## Automation-first production (V3, user instruction)

Automatic by default; manual only when requested. Single and Batch expose Auto, Assisted checkpoints and Expert controls. Auto import analyzes losslessly without starting GPU work; only explicit Generate starts production. Generate All includes descriptive FUTURE tags. Missing ordinary scale metadata receives editable values with explicit/inherited/inferred/defaulted provenance, never invented gameplay contracts.

Automatic technical concept/candidate selection is not artist approval. Keep every source and candidate, preserve approved masters and the Single/Batch quality resolver. Deliver each technically validated asset immediately with GLB Only + optional manifest by default. Export choices never lower generation quality or force FBX/native packages. Never claim untested engine import or mid-inference resume.

Persist stage checkpoints and bounded asset windows in SQLite. One heavy GPU stage at a time. Graceful Pause stops new admission and lets active stages checkpoint. Restart defaults to waiting for manual Resume; GPU auto-resume requires explicit opt-in. Reuse completed outputs and idempotent exports, retry only interrupted/transient stages within bounds, keep failures isolated. Atomic game delivery publishes validated files before updating the project manifest; retain version history and reject externally edited files/indexes. Never commit to game repositories or alter scenes automatically.

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


## Production workspace

Production is the shared operational route after any successful Single/Batch generation submission. Keep Create for fresh inputs, and keep legacy diagnostics under secondary navigation. Read model: `apps/api/production.py`; workspace: `apps/web/src/production.tsx`. Authoritative state remains the existing SQLite jobs/batches/exports. Never start GPU work from reading a workspace or importing a manifest. Keep scoped pause, cancelled-group exclusion from Resume All, immutable generation quality, SSE authentication and viewer resource disposal. Native acceptance uses `desktop/verify-production.mjs`; do not execute all 349 GPU assets during development. See `docs/PRODUCTION_WORKSPACE.md`.


## Unified Stable and automation status / revisions

User authorized expansion merge into main; latest product ships under Stable identity, preserving old distributions as rollback. Production, Library and Create share one SQLite job graph and scheduler. Persist independent status dimensions through `statuses.py`; never use Under Review as an Auto export gate. Review policies are Auto / Review Flagged / Manual Approval, with explicit artifact-scoped human decisions. Original prompt/source is immutable; resolved specs carry provenance. Revision defaults to staged output when a delivery exists; only explicit publication / Auto Replace may update game manifest. Do not invent direct mesh-editing capability. Reuse shared worker, existing Blender and atomic export validation. Safe cleanup is limited to resized thumbnail caches. See `docs/ASSET_MANAGEMENT_WORKFLOW.md`.
