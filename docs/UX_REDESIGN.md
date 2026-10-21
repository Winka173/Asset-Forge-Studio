# Local creation studio — audit and implementation

## Audit

The previous single-page quality lab had useful real import, synchronized Three.js comparison, human rubric, durable sequential inference, cancellation/retry, Blender artifacts and immutable exports. Preserve those implementations. Problems: hard-coded game/asset, technical parameters visible before the preview, global job history, no project CRUD, no named library asset/version state, no server-side draft or idempotent creation request.

## Navigation and states

`Home → select/create game → Create → approved image → Generate → candidate review → human Master selection → Improve/Export → Library → reopen`.

Six routes share a project switcher: Home (real recent assets/jobs), Create (input/advanced + large preview), Library (named assets/versions/search), Jobs (durable queue/errors), Compare (synchronized golden/concept review), Settings (project Art Bible, engines, local tools). No per-engine page or future Studio module.

Creation states: draft → reference selected → queued → running actual stage → generated → Blender postprocess → validation → human review. Preserve failed, cancelled and interrupted attempts. Refresh fetches persisted jobs; it never submits Generate automatically. Explicit retry reuses an already active retry attempt. Generation/export request IDs are committed atomically with their jobs.

## Data and honesty

An additive SQLite migration assigns existing Archer Tower artifacts to the real Runavelle asset without changing their bytes, metadata or IDs. New projects have empty libraries. New assets have stable UUIDs and retain versions, prompt, references, settings, human approval history and actual export history. Inference and Blender outputs inherit their project/asset. Project deletion requires its exact name, rejects active jobs and archives the project while preserving immutable files.

Art Bible, palette and material language are isolated project configuration; they are recorded with generation. Existing image-to-3D engines do not accept a text style prompt: UI must explain that prompt is saved context, not claim those words alter inference. No text-to-concept engine is installed, so text-only creation must explain this and offer image import. The complete text-only acceptance path remains unavailable until a real local concept engine is implemented and verified.

Auto Best Quality currently prefers the installed engine with proven textured output, then shape-only if input alpha is available. This is an explicit policy, not a universal measured quality ranking or Meshy parity claim. Research engines remain outside the production selector until useful output is proven.

Master selection is a deliberate human action and preserves earlier approval records/source files. It does not imply Meshy/Unity acceptance. Master GLB exports original verified bytes; FBX/Unity presets execute the existing Blender pipeline and expose files only after reopen checks. Unity presets are provisional LOD targets, not a Unity-tested Game-ready certification. Normal/clay viewer modes are diagnostics, not generated PBR channels.

## Validation

API tests cover legacy migration, empty new games, cross-project reference rejection, draft persistence, confirmation/archive, immutable master history, actual GLB downloads and atomic generation/export deduplication. Existing real Blender tests remain in place. Browser acceptance uses real Archer Tower inference in a separate database, distinct from production human approval. Screenshot and E2E evidence is recorded after implementation.
