# Automation-first production and asset management

This release unifies the reviewed expansion into the Stable application identity, as explicitly requested. Previous Stable and Expansion distributions remain rollback copies. The code on main is the canonical product after final validated changes are merged; external AI environments/weights and Blender remain local dependencies.

## Status and review

The authoritative graph remains SQLite jobs, batch items, attempts, artifacts and export transactions. `statuses.py` projects that graph into persisted asset fields: production_status, stage_status, qa_status, export_status, art_review_status, attention_required. These fields do not enqueue work or implement another scheduler. Changed projections record transitions, and legacy records are backed up with SQLite backup before additive payload migration. Original legacy status and prompt hashes are retained. An old Under Review label alone establishes neither a QA pass nor artistic approval.

Auto and Review Flagged export real technically validated outputs without human approval. Artistic evaluation is unavailable, so valid unreviewed results remain not_reviewed. Manual Approval gates only the corresponding asset's delivery; explicit project defaults apply to future job snapshots and per-asset overrides can hold/release existing work. Artistic decisions are append-only, scoped to artifact hashes and reviewer identity. No human decision is inferred from job completion. Approval of a master is independent of game publication.

An existing file export validates the real GLB container, finite geometry and embedded-resource contract. Automated production additionally requires the successful Blender stage and its technical checks before delivery. Manifests list measured bounds/materials and tests still not performed. Technical QA does not claim watertight topology, gameplay readability, artistic compliance or Meshy parity beyond actual recorded checks.

## Missing inputs and recovery

Short prompts are accepted unchanged. Dimensions explicitly stated in a prompt are resolved before defaults; explicit source fields remain explicit. Missing dimensions use Art Bible / family settings, related approved measured references, validated optional semantic suggestions or provisional category defaults. Resolved generation specification and provenance are separate from immutable original prompt/source spans. A meaningful asset name can supply a missing description with inferred provenance. Empty/unknown identities remain Needs Input, without stopping independent assets.

Production groups shared attention reasons. Fix Input / Change Engine applies explicit corrections to selected assets with the same cause through the existing manifest edit and automatic admission logic. Original source and quality remain recorded, and completed deliveries require Refine rather than destructive edits. Retry uses completed checkpoints and reruns only unsupported interrupted stages; it never claims diffusion-tensor resume. OOM does not silently reduce steps, resolution, textures or candidates.

## Revisions and publication

A revision retains the stable asset identity, immutable parent hash, original prompt hash, versioned delta, inherited style snapshot, dimensions, references, quality, candidate count/seeds, export settings and attempts. Its execution is an ordinary persistent batch group using the shared worker; child execution groups are grouped under the original explorer identity. Revision creation is idempotent. Existing active work is not interrupted unless Cancel Current & Replace is explicitly chosen.

The verified direct operation is uniform Blender scaling using an explicit instruction such as `Uniformly scale to height 18 m`. Other mesh/material/style changes regenerate from concept using installed capabilities. Direct language-based mesh and material editing are not implemented. Original reference images remain provenance; the installed text-to-concept route does not pretend to provide image-to-image preservation. General refinement requests default to silhouette/construction/material clarity while keeping explicit constraints; optional goal buttons do not require another question.

When an asset already has a delivery, a revision exports to the separate internal revision-previews root by default. The game-facing manifest and original version stay unchanged. Use This Version atomically publishes to the configured game root and records publication history; an older processed version can restore the prior pointer. Re-export cannot silently promote an unpublished revision. Auto Replace is an explicit per-revision option, not the default. Export directories remain immutable and externally edited files/manifests are not overwritten.

## Library and UX

Production tracks operational state; Library manages asset identity, versions and delivery. Both reuse the same Three.js viewer, revision panel, QA and export records. Create always starts a new draft. Successful submission navigates to Production; imported drafts never start GPU work. An admitted batch uses Open Production instead of inviting duplicate Generate All submissions. Batch submission summary shows asset/FUTURE count, quality and review policy; source/configuration details collapse after import.

Each screen emphasizes its primary action. Production keeps the preview central and secondary batch actions collapsed for asset inspection. The queue is windowed, and Library grids/lists are windowed with bounded metadata; only selected models load into WebGL. Search, category/production/QA/art/publication filters, sorting, favorites, bulk selection, artistic decisions, tagging, technical inspection, refinement and archive are available. Archived assets retain every file and can be restored. Active work cannot be silently archived.

External GLB imports are streamed, independently validated and deduplicated by project/hash. Real source files are retained and Blender/QA runs in the shared CPU queue. Model thumbnails derive from actual Blender renders; reference images are labeled Reference, and unavailable renders are represented as empty states. Resized WebP thumbnails are reproducible cache files. Storage reports measured registered project files and excludes engine weights / unregistered job intermediates; cleanup removes only those resized caches.

Explicit QA profiles now set WebView2 data_directory as well as single-instance identity. Earlier native tests exposed shared browser preferences despite distinct backend profiles; tests must not share WebView state or overwrite a running packaged backend. Build publishing preserves running editions and writes new version directories.

## Verification scope

Unit/API tests cover real Runavelle 349-source parsing, incomplete manifests, name fallback, corrected explicit dimensions, migration backup, independent status persistence, revision idempotency, shared CPU queue admission, true capability limits, staged export, manual policy, publish/rollback, real external GLB deduplication and bounded gallery responses. Geometry fixtures in unit tests are labeled as fixtures and never reported as AI outputs.

Native reports distinguish actual local GPU generation, CPU Blender revision, real viewer/thumbnail rendering, atomic delivery, manual policy, rollback and restart. No full 349-GPU development run, zero-defect guarantee, human artistic acceptance, clean-machine installer certification or Meshy equivalence is implied. Final measured results and executable hashes are recorded in docs/evidence.

## Native Stable 0.6.0 evidence (2026-10-22 local)

- `evidence/production_349_native.json`: actual Runavelle 349 admission, 37 FUTURE, windowed visible list, Single appended to the same global queue, zero GPU execution under global Pause, native restart.
- `evidence/production_relaunch_native.json`: real textured Archer viewer, non-overlapping panels, re-export without inference, native close/reopen, and Library-to-Create resets to an empty new draft.
- `evidence/asset_management_native.json`: existing real SDXL/TRELLIS.2 checkpoints and CPU Blender revision. The original has 969,026 triangles and a measured 17.0 m height. Revision preserves those triangles and measures 18.00000095 m; CPU processing took 489.7 seconds. Staged delivery leaves the original game pointer and source hash unchanged. Actual native A/B preview, Manual Approval rejection of unapproved publication, explicit publication, rollback and restart all pass. No new GPU job was created during revision recovery.
- `evidence/screenshots/` contains actual native screenshots, not mockups. The generated full-prompt building is a technical workflow sample; its silhouette does not establish Archer Tower / ballista compliance or Meshy parity.

Native testing exposed and fixed two production defects: the internal revision output root was not created before export validation, and an active SSE connection could keep graceful backend shutdown waiting. Regression coverage includes the missing staging directory and stream termination. A native file-input smoke uses Chromium's real DOM.setFileInputFiles command because WebView2's high-level Playwright operation timed out when the input cleared its value; the test still uploads the actual local GLB through the UI handler and verifies the backend response and source checksum.
