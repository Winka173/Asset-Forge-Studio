# ASSET FORGE STUDIO — ADAPTIVE 3D PRODUCTION + AI QUALITY CONTROL
## COMPLETE IMPLEMENTATION MASTER PROMPT FOR CLAUDE CODE

**Objective:** Transform the EXISTING Asset Forge Studio (AFS) model-generation pipeline into a reliable, quality-aware, recoverable, local-first 3D production system that produces genuinely useful game assets, instead of frequently failing halfway through. **This is an implementation assignment, not a request for a proposal, architecture-only answer, UI mockup, or untested code.**

**Target environment (verify, do not assume):** Windows 11, NVIDIA RTX 5070 Ti (~16 GB VRAM), 64 GB RAM, Tauri 2 + React/TypeScript UI, Python/FastAPI backend, SQLite, Blender 4.5 headless, optional local Ollama/Qwen3-VL, SDXL/Diffusers, TripoSG, Stable Fast 3D, Hunyuan3D, TRELLIS.2 community adapter, existing Production Workspace, Library and persistent GPU queue. Confirm actual repo, versions and working implementations first.

**Existing game projects:** Runavelle (premium stylized kingdom defense, ivory masonry, navy slate, wood/bronze/gold and restrained cyan magic); Aetherward (dark mythic arcane fantasy, 2D/2.5D game potentially using GLB for prerendered sprites); Forgebound (premium arcane blacksmith fantasy). Treat game style details as defaults to verify against project Art Bibles, not as permission to invent content or break existing IDs.

**Language:** Vietnamese user-facing progress and final summary; English code, types, schemas, internal docs and names where appropriate.

---

## 0 — NON-NEGOTIABLE CONTRACT

1. Work **inside the existing repository**. Audit, preserve, extend and test. No big rewrite, no new competing app, no replacement database, no second Production Queue/GPU scheduler/Library.
2. **Reliability first, then quality.** Diagnose actual failures before changing inference engines or promising better output.
3. Distinguish `Installed`, `Load Verified`, `Inference Verified`, `Export Verified`, `Degraded`, `Unavailable`, `Untested`; installing a checkpoint does not mean it works.
4. Keep the **original prompt immutable**. Store parsed/enriched specs separately with provenance (`explicit`, `inherited`, `inferred`, `defaulted`). Never override explicit constraints silently.
5. Auto mode is primary. Missing noncritical details should be inferred from the project, Art Bible, approved assets, presets and safe defaults. Do not block a 349-asset batch for routine subjective artistic approval.
6. **No silent quality downgrade** in Single or Batch. Both use the same per-asset `EffectiveGenerationConfig` and quality policy. If the selected route cannot meet requirements, use a verified equivalent or surface `Needs Attention` with evidence.
7. Maintain **one heavy GPU inference/render stage at a time by default** on 16 GB VRAM; CPU and disk tasks can overlap safely. No deadlocks from local VLM checking GPU while 3D engine holds VRAM.
8. Never declare technical success without running checks on actual outputs; never declare artistic superiority from a vision-model self-score alone.
9. Retain working raw geometry, approved candidates, masters, revisions and outputs. Failure in texturing/export must not destroy earlier successful stages.
10. Partial stages, revisions and delivery must be **durable, recoverable and idempotent** across app crash, power loss and reopen days later. Do not promise mid-inference checkpoints unless an engine really supports them.
11. `QA Passed` and `Art Approved` are distinct. `Not Reviewed` should not stall Auto mode if **mandatory technical and structural gates** pass; uncertain aesthetics should be flagged with evidence rather than falsely approved.
12. Only switch engines, lower resolution, alter candidate budgets or change shape strategy in ways allowed by explicit quality constraints, a documented equivalence policy and actual benchmarks; expose substantive tradeoffs.
13. Default export remains **GLB Only + manifest**, with atomic incremental delivery to the configured project output folder and version-safe promotion. Optional formats only when supported.
14. Do not auto-publish or overwrite the currently active game version on experimentation. Source masters and delivered assets are recoverable.
15. Never fabricate reference images, benchmarks, GPU performance, Unity validation, screenshots, CLI execution or license compliance. Clearly label `VERIFIED`, `IMPLEMENTED_UNVERIFIED`, `BLOCKED`, `NOT_IMPLEMENTED`.
16. Use local/offline-capable technologies; no compulsory paid APIs, no unauthorized copying, no unlicensed models/assets, no remote transmission of users' source images without opt-in.
17. Keep dependencies versioned, isolated and reproducible on Windows; inspect existing virtual environments before replacing anything.
18. Do not ask repeated preference questions; make safe decisions, record them and continue executing as far as environment permits.

---

## 1 — FIRST ACTION: EVIDENCE-BASED AUDIT AND FAILURE DIAGNOSIS

Before modifications, inventory the real repo and current pipeline; reproduce errors using its actual commands.

Inspect:
- Tauri desktop lifecycle; React Create/Production/Library; FastAPI routes; backend process management and logging.
- SQLite schema, migrations, job checkpoints, artifact/version identities, cache and output folders.
- Existing GPU scheduler, pause/resume/cancel/retry, single vs batch parity, queue priority, process isolation and process exit codes.
- Prompt parser, Qwen3-VL 4B via Ollama (CPU configuration), SDXL concept generation, concept QC/retry and engine routing.
- Installed or partially installed TRELLIS.2 Windows community fork, TripoSG, SF3D, Hunyuan Shape/Paint and Blender wrappers.
- Python/CUDA/PyTorch/driver compatibility, CUDA extensions, subprocess import errors, device allocation and model loading.
- Real job records for recent failures: per-stage start/end, stderr/stdout, exception stack, subprocess exit code, model/version, config, retry, elapsed time, peak VRAM/RAM, disk remaining, input/output paths.
- Which stages already produce recoverable artifacts, and which falsely mark an entire asset failed after downstream errors.
- Existing approved gold samples, project Art Bibles, GLB importer and actual Windows desktop build.

Create/update `docs/afspipeline/`:
- `BASELINE_AUDIT.md`: actual implementation, versions, file references, evidence.
- `FAILURE_TAXONOMY.md`: classify observed failures with logs and root-cause confidence.
- `ENGINE_CAPABILITY_MATRIX.md`: factual support and verified status.
- `IMPLEMENTATION_PLAN.md`: incremental changes with migration and rollback.
- `QA_MATRIX.md`, `BENCHMARK_RESULTS.md`, `KNOWN_ISSUES.md`, `DECISIONS.md`, `CHANGELOG.md`.

**Important:** Never assume the failures are all caused by TRELLIS.2 or VRAM. Some may be path, exception handling, GLB validation, process timeouts, weights or CUDA ABI. Avoid making engine changes before identifying at least representative root causes. If production logs are insufficient, add non-sensitive instrumentation and run small real diagnostic jobs.

---

## 2 — USER WORKFLOW AND VISIBLE STAGE MODEL

Main flow:

`Create request → Preflight → Strategy → Reference/Concept → Geometry → QA & Repair → Texturing/Finishing → Final Validation → Incremental Delivery → Library/Refine`

Inside the backend these are independent checkpointed tasks. In UI show 6–8 compact high-level stages with expandable details, **not 13 noisy progress steps**. Stage timelines must show observed progress or truthful indeterminate state; do not invent 93% for arbitrary model inference.

Support `Auto` (default), `Assisted`, and `Manual/Expert`. Single and Batch converge into the exact same asset job planner and config. For 349 Runavelle / 462 planned Aetherward prompts, submit to a **persistent global queue**, allow FUTURE-tagged assets when requested, and continue other independent jobs if one needs attention.

A concise Create screen: Project, Prompt/manifest/reference, Quality, Export destination, Generate. Advanced controls are collapsed by default.

---

## 3 — ASSET INTENT AND STRUCTURED SPECIFICATION

Generate a schema-validated `AssetGenerationSpec`:
- `asset_id`, project, category, asset role, game target/platform, project style.
- Original prompt and immutable reference pointers/hashes.
- Primary object/subject; style-only vs shape/identity reference classification.
- Required structural components and spatial relations; explicit negative constraints.
- Target approximate real-world bounds, orientation, pivot, units, assembly connectors, collider needs.
- `organic | hard_surface | architecture | modular_environment | existing_mesh_edit | mixed`.
- Visual style, materials/palette, silhouette requirements, hierarchy and LOD constraints.
- Desired outputs: high-quality master and game-ready derivative if justified.
- Confidence/evidence for inferred fields and whether each rule is a **hard gate** or soft preference.

Use Qwen3-VL for prompt+image interpretation when available, **structured JSON with strict schema validation**, and deterministic fallbacks; avoid fabricating unseen image features. Examples:
- “Create a castle in the style of this tower”: tower image = **style reference**, new subject = castle; no direct tower Image-to-3D.
- “Rebuild the object shown in this image”: image = shape reference, route through verified image-to-3D.
- “Make this existing roof navy”: material edit starting from pinned GLB, not concept regeneration.

If a prompt requires unsupported geometry or exact reference fidelity, state capability limitation and choose the best allowed route; do not silently reinterpret it as a different asset.

---

## 4 — PREFLIGHT, ENGINE REGISTRY, HEALTH AND CIRCUIT BREAKER

Implement a capability-based `EngineAdapter` contract with:
- `id`, `version`, `source`, license metadata, supported operating systems.
- Native inputs (prompt/image/multiview/mask/mesh), outputs (mesh/UV/textures/PBR), supported edits and constraints.
- Resource requirements, optional offload, quantization, texture size/model path, expected failure modes.
- `probe_install`, `probe_load`, `run_known_smoke_inference`, `validate_output`, `cleanup`, health records.
- Real registered workflow/CLI contracts, timeout/kill semantics and subprocess log paths.

Track verified status per `(engine version, dependency environment, driver/CUDA fingerprint, GPU, workflow profile)`. Health check after install/update/driver change and after repeated errors, NOT full inference every startup.

Initial adapter policy (actual benchmarks override priorities):
- **TripoSG**: priority image-to-3D baseline candidate when installed and verified; do not assume every asset class is superior.
- **Hunyuan3D 2.1 Shape**: benchmark geometry alternative; check actual VRAM and compatibility. Hunyuan Paint must not be assumed feasible on 16 GB without a verified compatible setup.
- **Stable Fast 3D**: optional fast/simple image-to-3D route after verified install.
- **TRELLIS.2**: experimental on 16 GB Windows unless the exact community fork demonstrates reliable real inference, export and resource behavior; do not set it as Auto default merely because it can load.
- **Blender procedural**: first-class deterministic geometry route for buildings, modular architecture, exact hard surface assemblies, transforms and supported repairs.
- Other future engines may be added via adapters; do not install everything by default.

**Circuit breaker:** cluster failures by exact engine+version+profile+root-cause class. If repeated environmental/incompatibility failures occur, quarantine that route temporarily; mark queued jobs as waiting/replanning instead of mass-failing hundreds. Resume only after meaningful remediation and health validation. Distinguish transient execution failures from content/model-quality failures. Persist breaker state and reset criteria, expose diagnostics.

**Preflight**: disk headroom, write permissions, checkpoint integrity, model load path, CUDA/device resources, Blender export, subprocess health, job input validity and projected resource risks. Run actual smoke inference only when no valid verified record exists or change/failure warrants it.

---

## 5 — ADAPTIVE STRATEGY PLANNER: ORGANIC / PROCEDURAL / HYBRID

**Do not require all assets to pass through SDXL and image-to-3D.** Select by subject semantics, user reference type, game constraints and measured engine capability.

### A. Organic AI
For creatures, heroes, character sculptures and irregular props: use concept/reference + compatible image-to-3D engine; plan semantic part checklist and downstream rig feasibility. Do not claim the generated GLB is rigged or animatable without actual skinning/animation.

### B. Procedural / parametric
For walls, paths, tiles, floor pieces, towers, castles, gates, bridges, geometric weapons and dimension-critical assemblies: plan geometry by named submeshes, parametric Blender scripts, modular kits, connectors, consistent scale and material zones. Validate dimensions, part count, joining and alignment.

### C. Hybrid assembly
For ornate castles, complex shrines, bosses with detachable props, multi-part structures: Blender establishes controlled base geometry and assembly; AI details may add ornamentation only when compatible. Keep parts as separate editable submeshes, with stable hierarchy, connectors and material slots.

### D. Existing mesh refinement
For existing GLBs, prefer direct material/geometry/scale edits when technically possible. Generate from scratch only if the requested change genuinely requires it.

**Case study — fantasy castle based on a tower reference:** resolve style from the tower but generate a *castle* consisting of keep, four corner towers, curtain walls, gatehouse, roofs and details. Use part-level hard gates; validate connectors, dimensions and silhouette. A single whole-castle Image-to-3D attempt can remain an experimental comparison, not the default production strategy.

Store route rationale and fallback plan. The route planner must not become a rigid hardcoded `if castle → always Blender`: respect available real assets, project approved results and benchmarks.

---

## 6 — REFERENCE PREPARATION AND CONCEPT INPUT SUITABILITY

Only create an SDXL concept if a concept actually improves the chosen route. When needed:
- Preserve user references unmodified and distinguish style vs shape references.
- Preserve project Art Bible and explicitly requested palette/shape; optionally local SDXL/Diffusers, with memory-safe verified settings. 1024×1024 and 50 steps are **not hardcoded universally**; tune presets from measured quality/resource results.
- Check single dominant object when appropriate, full subject silhouette/padding, non-cropped head/roof/feet, plain/consistent background, minimal occlusion, perspective, subject and prompt correspondence, segmentation/mask quality, semantic mandatory parts.
- For multiview, accept real consistent reference angles or generate proposed views with consistency verification; never assume AI-generated front/back views depict the same geometry merely because they share a prompt.
- For complex structures, prefer structural blueprints/part specifications over inventing photorealistic back views.

**QA routing:** deterministic image checks first (size, alpha, crop, mask, aspect, duplicates); Qwen3-VL semantic assessment second. JSON output with `checks`, `observed_evidence`, `missing`, `unknown`, `confidence`, `proposed_fix`. Do not use one arbitrary AI numerical score as a pass/fail authority.

Repair by cause: crop→reframe; multi-subject→segment/new concept; wrong subject→rebuild effective prompt; wrong style→adjust reference conditioning; inconsistent multiview→regenerate only inconsistent views; unresolvable → Needs Attention and continue batch. Bound attempts by time/compute/stage budget; different seeds without addressing cause are not a valid repair plan.

---

## 7 — STAGE-LEVEL QUALITY GATES (DETERMINISTIC + AI)

Create a reusable `QualityEvaluationEngine` with **4 independent QA layers** and a gate at meaningful checkpoints:

1. **Technical Integrity:** file decode/import, finite transforms, geometry non-empty, triangle count, degenerate faces thresholds, normals, UV, texture paths, material count, naming, export hash, valid units and bounds. Programmatic Python/Blender/glTF tooling is the authority.
2. **Geometry & Structure:** required parts present (by named submesh/assembly manifest where possible), part count, dimensions, symmetry where required, door/portal/roof connectivity, no floating/disconnected geometry where forbidden, collisions/gaps, usable orientation/pivot, manifold checks only for assets requiring solid watertight geometry. Never universally reject intentionally open planes, foliage, cloth or VFX geometry.
3. **Visual & Semantic:** render real front/back/left/right/three-quarter/top as appropriate using consistent camera/exposure; compare with **original user prompt and Art Bible** as well as the accepted concept; Qwen3-VL detects wrong object, silhouette defects, missing obvious parts, texture/material/palette mismatch. Render unseen regions for actual 3D evidence. The VLM may say `UNKNOWN` and may make errors: use evidence images and uncertainty flags, not absolute artistic claims.
4. **Game Integration:** use actual game view, import and scale tests where Unity/project access is available; check LOD, pivot, colliders, material pipeline, performance budgets and readability at target camera/target screen resolution. Aetherward may require **2D/2.5D orthographic sprite render** from GLB, preserving original Unity sprites/GUID references; do not pretend GLB import converts the game to runtime 3D.

Each gate yields: `PASS`, `REPAIRABLE`, `FLAGGED_UNCERTAIN`, `BLOCKED`, `NOT_EVALUATED` with evidence, severity, remediation suggestion, tool/version, timestamps and hashes. A technical hard gate can block; subjective artistic concerns should be flagged or routed to optional review in Auto mode unless they violate an explicit mandatory requirement.

**No average score overriding failures.** Required gate criteria are conjunctive, then rank surviving candidates by soft criteria. A model missing the mandated castle gate is invalid even if visually gorgeous. Semantic AI judgments must be calibrated against human-rated examples; never claim a fixed 85/100 threshold is scientifically valid without ground truth.

Use a versioned, validated QA JSON schema; cache by `artifact hash + prompt/spec hash + reference hash + evaluator version + QA config`. Reuse cached judgments only if inputs/evaluator have not changed. Preserve raw render evidence.

---

## 8 — GEOMETRY GENERATION, CANDIDATES AND CANDIDATE SELECTION

- Generate small candidate sets using **the same declared quality configuration** in Single and Batch. A batch may queue more slowly; it must not silently lower per-asset quality.
- Per candidate store: raw mesh/master source, engine/version/seed/input images/workflow profile, logs, wall time, peak VRAM, geometry checks, renders and semantic evaluation.
- Run lightweight validity checks **before** expensive texturing. Do not waste texturing cycles on clearly empty, invalid or wrong-object geometry.
- Candidate eligibility = mandatory gates pass; ranking among eligible candidates considers geometry integrity, silhouette, reference faithfulness, material quality, project consistency, game suitability and measured costs. Rank evidence, not unsupported claims such as “the AI thinks this is 9.5/10 premium”.
- When comparing one engine versus another, normalize evaluation rendering/camera/lighting and original reference to avoid spurious wins.
- Preserve non-selected viable candidates for revision/repair according to storage policy.
- If no candidate meets mandatory requirements, choose targeted recovery or `Needs Attention`, never silently promote the least-bad model as fully completed.

---

## 9 — TEXTURING, MATERIALS, MASTER AND GAME-READY DERIVATIVES

Separate:
`raw_geometry → validated_geometry → textured_master → game_ready_derivative → GLB_export`.

- Use available real PBR/texture workflows only after verifying model weights/licensing/resources; fallback to authored procedural/material-library colors **when allowed by required quality and game style**, explicitly recording fidelity limitations.
- Preserve UV/material inventory, material slot mapping, texture hashes, correct color space, roughness/metallic/normal, transparency as applicable.
- Maintain high-quality master untouched; create game-specific optimized derivative separately (LOD, decimation/retopo with measured silhouette loss, atlas if project pipeline permits, simple colliders, pivots/scale).
- Never run universal remesh/decimate/manifold cleanup over all categories; thin leaves, transparent magic planes and cloth need category-specific handling.
- Do not destroy unique mesh/texture details by uniform reduction merely to satisfy arbitrary polygon budget.
- For Runavelle, preserve approved color/material language and game-approved naming conventions; for Aetherward, validate actual prerender game-scale readability; for Forgebound, make weapon frame/core/rune silhouettes meaningful and preserve modular semantics.

---

## 10 — QUALITY REPAIR PLANNER AND RETRY POLICY

Implement `QualityRepairPlanner` mapping root cause → minimal affected stage → exact supported action → cost/resource prediction → validation plan. It must not suggest unsupported editing operations.

Examples:
- `CUDA_OOM`: unload, isolate GPU, evaluate measured offload strategy; bounded meaningful retry; optional equivalent engine if verified and permitted.
- `MODEL_DEPENDENCY_MISSING` or CUDA ABI conflict: mark environmental failure; no repeated inference until repaired.
- `CONCEPT_WRONG_SUBJECT` or cropping: revise reference preparation / prompt and retry concept only.
- `MULTIVIEW_INCONSISTENCY`: regenerate affected view, do not rerun entire pipeline unnecessarily.
- `EMPTY_OR_WRONG_MESH`: regenerate geometry or switch to modular strategy; do not texture.
- `MISSING_CASTLE_TOWER`: repair Blender component/assembly graph if that route supports it; otherwise regenerate suitable geometry.
- `NORMALS_UV_MINOR_ERROR`: Blender repair then reevaluate; do not run AI inference.
- `TEXTURE_MISMATCH`: material adjustment/retexture only; reuse geometry.
- `EXPORT_FAILURE`: re-export from validated master; verify GLB by reimport.
- `VISUAL_JUDGE_UNCERTAIN`: mark flagged, optional human review; do not discard usable master based solely on uncertain VLM opinion.

Enforce retry budgets per asset, stage, engine and root-cause class: attempt count, elapsed GPU/CPU time, disk cost and no-progress detection. Track whether a retry meaningfully changed the failure conditions. Prevent endless loops and thrashing between engines.

Preserve artifact checkpoints. Use a dependency DAG/hash so revisions invalidate only affected steps; cancel and retry distinct; original prompt and outputs immutable. A job can be `Needs Attention` while an intermediate asset remains browsable.

---

## 11 — PERSISTENCE, QUEUE, STATUS AND FAILURE ISOLATION

Reuse existing SQLite and queue. Extend via safe migrations; support resume after power loss/app close. Suggested independent state axes:
- `production_status`: Queued, Running, Paused, Recovering, NeedsAttention, Completed, Failed, Cancelled.
- `stage_status`: Pending, Running, Passed, Repairing, Failed, Skipped, NotEvaluated.
- `qa_status`: TechnicalPassed, TechnicalFailed, VisualFlagged, NotEvaluated (prefer separate technical/visual fields).
- `art_review_status`: NotReviewed, Approved, Rejected, NeedsReview.
- `export_status`: NotExported, Exported, Published, ExportFailed.
- `attention_required`: boolean + reason codes.

Persist stage input/output references, hashes, version fingerprints, last successful checkpoint, logs, retry records and estimated resources. On restart reconcile process state and actual files before resuming. One asset failure must not block independent jobs. Auto cannot wait for aesthetic approval unless explicitly configured `Manual Approval`.

Circuit breaker must handle 349+ jobs without mass failure. If common engine failure occurs, keep unattempted jobs pending and give user actionable diagnosis. Pause should be at stage boundary; never promise checkpoint restoration inside opaque diffusion operations.

---

## 12 — FINAL EXPORT, DELIVERY, LIBRARY AND ITERATIVE REFINE

- Deliver **GLB Only + manifest** by default as soon as each asset passes mandatory gates; atomic write/rename and stable content hash. The job should not wait for whole batch.
- Validate exported GLB by reopening it in Blender or glTF validator, inspecting dimensions/materials and rendering at least one angle. Never assume successful subprocess exit means valid geometry.
- Preserve master, source intermediate versions and export records. Stable asset identity; revisions v1, v2, v3 are not separate asset identities.
- Production page previews real candidates/render contacts, stage errors, recoveries and logs; Library holds actual model, versions, exports, QA evidence and ability to `Refine with Prompt`.
- Revision planner routes edit to the earliest truly affected stage; material changes do not rerun 3D, structural changes rerun required geometry or assembly.
- Side-by-side GLB comparison, choose/promote version, restore, rollback. Existing game-active asset **must not be silently overwritten** by experimental revision; initial Auto delivery and subsequent promotion follow separately documented policy.
- Cache cleanup may remove reproducible intermediates after safety checks, but never unique source, approved master or currently published version.

---

## 13 — ASSET BENCHMARK LAB: QUALITY AND RELIABILITY MEASUREMENTS

Create reproducible **Asset Benchmark Lab** using real representative project assets:

1. Simple organic (skull/creature).
2. Hard surface (sword/chest/shield).
3. Aetherward hero (figure, detail, potential sprite-readability).
4. Runavelle Archer Tower T3 (architecture detail and scale).
5. Complex castle with four corner towers and a gate (single-mesh vs modular/hybrid).
6. Environment kit wall/gate/path/tiles (snap, repeat and connectors).
7. Aetherward boss or complex fantasy creature (silhouette/semantic detail).

Compare eligible verified engines and routing strategies with standardized prompts/references and same evaluation rendering. Record attempts (5–10 repeats when resources allow; label lower sample sizes transparently), GPU peak, RAM peak, elapsed time, cost in GPU minutes, output validity, first-pass and after-repair success, number of retries, true end-to-end acceptance rate and reasons rejected.

**Metrics:**
- Geometry generation success rate.
- Valid GLB rate.
- First-pass completion rate.
- End-to-end **accepted asset** rate.
- Time per **accepted asset** (more important than fastest raw inference).
- Median and tail latency, GPU minutes, peak VRAM, disk consumption.
- Structure/mandatory-part compliance and geometry integrity.
- Reference/Art Bible fidelity through human or calibrated vision-review evidence.
- Game-scale readability and target Unity compatibility (when verified).
- Recovery rate after actual failures.

Do not average away hard failures with attractive concept art. Store provenance of every benchmark, and make route decisions evidence-based. Benchmarks must not run on every app launch. New drivers, models or environments invalidate relevant measurements or mark them stale. Allow user to inspect benchmark evidence in Settings/Diagnostics.

### Calibrating local vision QA
Build a small manually assessed dataset of `Accepted`, `Rejected` and `Uncertain` assets with annotated reasons; test Qwen judge prompts/model revisions for false accept, false reject, confidence calibration and disagreement. Do not optimize AI judge to merely agree with its own prior decisions. Keep independent geometry/technical gates authoritative.

---

## 14 — RELIABILITY FIRST IMPLEMENTATION PHASES

### P0 — Triage and base reliability (must come first)
1. Instrument and reproduce frequent Failed cases from real logs.
2. Implement root-cause taxonomy, health states and truthful error messages.
3. Validate real TripoSG/Hunyuan/SF3D/TRELLIS setups; choose Auto default using evidence.
4. Persist per-stage artifacts and checkpoints; split failed stage from asset availability.
5. Add bounded retries and environment circuit breaker.
6. Verify one end-to-end GLB with correct technical gates and export reimport.
7. Verify Single/Batch quality config parity and safe queue behavior.

### P1 — Adaptive route and quality control
8. Structured prompt+reference intent, style-vs-shape distinction.
9. Organic/Procedural/Hybrid/Existing GLB routing.
10. Input suitability concept checks and cause-specific repair.
11. Geometry QA before texture, render contact sheets and Qwen semantic QA.
12. Blender procedural assembly for dimension-critical architecture and modular kits.
13. Independent masters/game-ready derivatives, meaningful LOD/material handling.

### P2 — Full production quality and benchmark
14. Multiview reference consistency as supported; semantic required-part detection.
15. Stronger candidate comparisons, versioned quality evidence, calibrated human benchmark.
16. Game integration check paths for Unity/project, readability/sprite rendering for Aetherward.
17. Benchmark Lab UI/report, A/B engine routing and resilience testing on sizable batches.
18. Progressive polish of Library, inspector, recovery actions and revision UI.

Do not work on Video Studio, Audio Director, social posting or unrelated expansion while fixing the core 3D generation reliability, unless absolutely required by shared infrastructure. Keep existing capabilities functional.

---

## 15 — REAL ACCEPTANCE SCENARIOS (REQUIRED)

**A. Baseline & failure reproducibility**: show at least representative failing job logs and root-cause classification; demonstrate diagnostic improvement.

**B. Real geometry engine smoke**: for installed engines claim `Inference Verified` only after actual inference and valid exported geometry, not import success.

**C. Style vs shape**: with a tower reference, prompt “create a castle in this tower's style”; spec must produce castle subject with tower used only for style, unless user explicitly asks otherwise.

**D. Complex castle strategy**: produce an assembly plan with named keep, four towers, main gate and wall modules; validate count, scale/connectors and render results. If final art cannot meet requirements, mark limitations truthfully.

**E. Real model path**: single sword/asset → concept if required → valid mesh → Blender postprocess → multi-view QA → GLB re-import → incremental Library delivery.

**F. Organic character**: Aetherward hero asset through selected verified route; validate object identity, multiple-angle geometry and game-view readability; do not claim rigging if none.

**G. Texture-only repair**: change roof material color on an existing master without rerunning image-to-3D; version history and game-active copy remain untouched.

**H. Empty geometry**: engine returns empty mesh, detect at earliest stage, prevent texture/export, recover or Needs Attention with actionable reason.

**I. CUDA OOM**: inject/reproduce OOM, unload resources, bounded adaptive retry or quarantine route, no endless fail loop; no dozens of queued mass failures.

**J. Missing model/dependency**: detect and prevent meaningless repeated GPU attempts; show repair instructions.

**K. Crash recovery**: close app between concept and 3D, then between master and export; restart and reuse verified intermediate outputs.

**L. Batch isolation**: queue representative batch, one bad asset gets Needs Attention but others complete; 349+ manifests are handled without exhausting scheduler/database resources. Do not claim 349 actual generations if only dry-run.

**M. Gate correctness**: missing mandatory gate/tower cannot pass despite good visual score; intentionally open foliage should not be rejected by universal watertight requirement.

**N. AI judge uncertainty**: Qwen unavailable or unable to observe hidden surface → mark Not Evaluated/Unknown, do not invent pass; run deterministic technical QA regardless.

**O. Import validation**: exported GLB can be reimported to Blender with actual mesh/material/scale; if Unity is available, import target sample and capture evidence. Clearly label unverified Unity if unavailable.

**P. Quality lock**: Single and Batch effective settings match; GPU serial scheduling avoids unsafe simultaneous workloads; Maximum Quality never silently becomes cheap/draft.

**Q. Windows release**: build packaged Tauri app and run realistic Create → Production → Library → Refine → Export smoke. If Windows build cannot be run here, mark blocked and provide exact commands/evidence required; don't claim successful packaging.

Keep `QA_MATRIX.md` with individual status, commands, logs, evidence paths, failures and fixes. Automated tests should cover schema, migrations, stage DAG, circuit breaker, retry semantics, export atomicity, version rollback and route selection. Tests must not merely mock all success paths.

---

## 16 — REPORTING AND DONE CRITERIA

At the end, produce a concise Vietnamese report including:
1. Exact changes and file paths.
2. Root causes actually observed and corrected (separate hypotheses).
3. Engine matrix with real install/load/inference/export verification.
4. Representative generation examples and actual GLB paths/previews.
5. Benchmark results, sample count and limitations.
6. QA gate reports and repair outcomes.
7. Production resume/batch verification and memory observations.
8. Windows application build/test evidence, or honest blockers.
9. Remaining bugs/risks, optional P2 enhancements and reproduction steps.
10. How the user runs a single job, large batch and model refinement in the updated AFS.

**Definition of Done:** At least one **real** local path yields a usable validated GLB end-to-end; errors are classified, stage recoverability is real, the correct adaptive route is selected for representative asset types, quality gates and Auto mode have truthful behavior, and Production/Library are integrated. Do not call all phases complete merely because files, UI labels or tests with synthetic outputs exist.

---

# START EXECUTING NOW

Audit the actual AFS repository and the real Failed jobs first. Then implement P0, validate a working vertical slice, and continue P1/P2 as resources permit. Make conservative, compatible changes; create usable software, not only a roadmap. Preserve existing applications, user assets, version history, and the high-quality pipeline wherever genuinely functional.

**Target user experience:** `Describe / attach style reference → AFS understands what to build → picks a proven strategy → generates and verifies candidates → repairs the correct stage → finishes materials and geometry → validates real GLB → exports automatically → user can review/refine without losing previous results.`
