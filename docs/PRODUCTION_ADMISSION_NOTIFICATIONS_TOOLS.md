# Production admission, progress, notifications and local tools

## Production queue

Previously the backend checked whether any item in a batch was started, then returned every imported item. Production therefore displayed 349 rows after starting one asset. The read model now includes only assets explicitly started or backed by actual admitted jobs. Counts use that same set. Import drafts stay in Batch, and one admitted asset opens directly instead of a batch overview. One stable asset identity contains nested attempts and stages.

Generate buttons now send an explicit new-attempt flag and a persisted request ID. A new intentional click re-runs selected terminal attempts; active attempts remain intact. Replaying the same HTTP request does not increment attempts or duplicate jobs. Pause/Resume and Retry Failed retain their separate checkpoint semantics. Previous generation context, outputs and masters remain available. Status projection excludes prior attempts' candidates and exports, so a new attempt cannot inherit old technical or artistic approval.

## Visible pipeline progress

The preview header shows actual job progress.stage, engine and seed when present. View pipeline opens the inspector history. A five-stage static-model timeline shows Concept, 3D, Blender, technical QA and Export from real jobs/reports/delivery records. Supplied image input can skip Concept; no generated concept is invented. Native World/FX jobs show their actual native stages instead.

The outside progress bar counts completed/skipped stages and explicitly says it is a stage count, not a time estimate. Asset rows have compact bars. A running stage's own reported percentage is separate and shown only when finite and within 0?100. No wall-clock estimate or synthetic inference percentage is introduced.

Buttons use filled action families and explain consequences: Edit settings does not generate, Review does not export, Retry retries a failed stage, Regenerate creates a new AI attempt, Pause waits at a safe stage boundary. Destructive actions remain explicit.

## Notifications

A single Notifications bell replaces the old project-only browser inbox. SQLite stores stable event IDs, read state and cleared tombstones. Actual persisted job success/failure and completed selective-export records supply notifications. Polling is idempotent; opening the inbox does not mark entries read. Users can filter all/current game, completed/failed/unread, page through history, mark read, clear history and open the relevant pipeline. Clearing notifications never deletes assets, jobs or files. Optional Windows notifications remain opt-in.

## Local tools

On app startup a background request probes known local installations, environment overrides, PATH and Unreal registered builds. Find again reruns bounded discovery. Choose executable uses a Windows native picker, verifies executable identity and validates before persisting. Invalid selections leave previous settings intact; running stages prevent path changes. Blender uses a real --version probe; Unity PE product metadata is read without opening an Editor or activating a license. Unreal Build.version is checked without launching the Editor. Detection is separate from native output validation: Unreal remains unsupported; Unity remains pinned to the tested 6000.4.8f1 Built-in profile.

Saved choices are local to the current AFS Library. Blender postprocessing and Unity adapters use the same selected paths. No tool installation, EULA acceptance, paid service or AI model load is triggered by discovery.

## Verification and limits

Automated regressions use the actual Runavelle file, verify one selected asset appears as one Production row, old request replay does not duplicate work, a new click creates a distinct attempt, and the original full prompt is retained. The development test plans all 349 but does not run all 349 GPU jobs. Unit fixtures for failures/old candidates are explicitly labelled as fixtures and do not establish successful generation.

Native evidence is recorded in evidence/production_admission_native.json and evidence/notifications_tools_native.json. The queue smoke holds GPU admission paused and materializes the same idempotent concept request through the production endpoint to inspect persisted pending-stage controls; it does not claim a new AI output. Notifications acceptance uses two actual Unity builds with cold-reopen/NavMesh validation and a real worker rejection after deliberately altering a copied test GLB. Tool probes use the installed Blender and Unity. All QA runs use isolated Libraries, not the user's production data.
