# Production workspace

## Audit and navigation decisions

The prior Single and Batch already shared SQLite jobs, immutable EffectiveGenerationConfig and one process-safe heavy GPU lock. Create combined input, review, logs and progress; Jobs was a technical table. No AI inference rewrite was required. Production is now the shared operational screen: Projects ? Create ? Generate ? Production ? optional review / Library. Compare, Diagnostics (legacy Jobs) and Settings remain available as secondary tools. Sidebar Create always creates a fresh draft; Add Jobs uses the same action. Successful automatic, assisted and expert submissions navigate to their persisted group/job. Failed submissions remain on Create with the backend error.

## State and interaction

Production's queue explorer spans every project. A durable Single is a one-asset group; Batch retains all original manifest IDs. Imported drafts enter Production only when explicitly submitted. Group selection displays counts and actual stage distribution; asset selection stays in Production and loads only that asset's detail. The queue uses fixed-height windowing (28 mounted rows with overscan), search and filters. Selection, queue scroll, Auto-follow preference and last workspace persist locally; authoritative requests/jobs/attempts/checkpoints/exports remain in SQLite. Auto-follow never opens a different page and manual selection disables it. Model switching reuses the existing Three.js viewer and its resource disposal.

The center chooses actual exported GLB, processed candidate, raw candidate, then concept/reference. The selector exposes all available versions and concept images; a second candidate uses synchronized cameras in the existing comparison viewer. No generated placeholder is added. Inspector shows measured stage durations, recorded state transitions, a bounded 16 KB log tail, technical QA and real delivery links. Historical jobs without recorded transition events are not assigned invented event histories. Completed stage timing comes from resources.json; running elapsed uses the persisted RUNNING event timestamp.

## Scheduler and controls

All generation still uses the existing worker. Pause Asset, Batch and All prevent new eligible stages while active stages finish their non-interruptible work. Global and per-asset pause persist in SQLite using existing tables; no schema migration or source conversion is required. Resume All is an explicit global action and releases paused scopes, but never restarts cancelled groups. Restart recovery defaults to manual Resume unless existing project auto-resume was explicitly enabled. A queued paused stage no longer forces cancel-and-exit when closing the app.

Next = priority 100, Normal = 0, Batch Order = -10; existing inference/Blender stage bonuses remain. Unbounded one-point-per-minute queue aging allows old work to eventually outrank fresh high-priority arrivals. Priority never interrupts an active stage. Resource caps remain one heavy GPU stage and the existing bounded CPU/I/O workers, shared across Single, Batch and desktop processes. Original quality, project style snapshot, references and export snapshot remain unchanged.

Cancel and Regenerate require confirmation. Cancel stops unfinished work and retains outputs. Retry creates a new attempt only for an interrupted/failed stage. Regenerate starts a new asset attempt and preserves previous versions/masters. Review / approve is an explicit Studio action; technical completion does not set artistic approval. Re-export uses existing checked files and starts no AI. Download final GLB, Open Folder and Copy Path refer to real delivery records.

## Updates and limits

Authenticated local SSE publishes durable queue revision notifications; the UI refreshes its read model on changes, with a 15-second fallback poll. Selected-asset logs/detail refresh independently. The persistent global header reports all projects' running/queued stages, rather than just the current game's jobs. Neither SSE nor React state owns the scheduler.

CPU Blender validation and export remain existing stages. The UI exposes their actual states/events; it does not invent seven separately timed jobs when the backend performs QA inside Blender. Per-batch disk usage and ETA are explicitly unavailable rather than estimated without evidence. Windows tray/background mode, diffusion tensor checkpoint resume, Unreal verification and Meshy artistic parity are outside this slice.

Actual native acceptance and screenshots are recorded separately after testing. Full 349 admission is tested with global scheduling paused, so no 349-GPU development run is started. Only the small explicit acceptance subset may execute.
