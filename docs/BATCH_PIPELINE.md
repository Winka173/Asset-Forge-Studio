# Batch pipeline and Quality Lock

Create contains Single Asset and Batch Assets. Both call the same concept/generate endpoints and `engines/quality.py` resolver. Batch orchestration adds a durable manifest, per-item checkpoints and dependency/priority controls; it does not introduce another inference implementation.

Explicit JSON, CSV, Markdown tables and asset/tier lists are parsed locally. Without a configured local language model this is a structured parser, not semantic AI planning. Unknown dimensions remain missing and require confirmation. T1-T3 is expanded into three independently editable items; dimensions are never inferred as equal. New manifest items create draft metadata, never fabricated meshes.

The saved EffectiveGenerationConfig includes prompt/reference hashes, actual checkpoint hashes, engine, seed, precision, resolution, steps, texture availability, Blender/LOD/export and QA requirements. Retry preserves its bytes and hash. The worker rejects changed hashes, checkpoints or execution parameters. Unsupported requested stages fail explicitly. Shape-only engines are not described as textured. Technical export validation and human master approval remain separate.

The default scheduler admits one heavy GPU task and up to two CPU Blender tasks, bounded by available RAM. All data stores/processes share operating-system GPU/CPU lock files. Single, Batch and GPU Blender use the same resource admission. CPU Blender uses a bounded thread count and can overlap inference. A paused batch finishes its active stage and keeps queued work at checkpoints. An item submission error is persisted on that item; other items continue. Timeout/OOM never switches the engine or reduces quality. Interrupted jobs become blocked and need an explicit retry; stage-level recovery does not imply resuming a partially executed diffusion step.

Resource reports record job start/end, wall time, process-tree RAM, system RAM/CPU and sampled GPU memory, power and utilization. GPU Torch maxima are separate from whole-device samples. Cross-machine throughput improvements and increased GPU concurrency have not been proven; concurrency remains one.

Exports contain real immutable outputs and a manifest/report identifying missing models. A ZIP containing omitted items is not a successful complete batch. Quality, family consistency, dimensions and production acceptance require review of actual models. The Meshy reference currently consists of an image only; geometry/PBR parity cannot be established from it.

Windows desktop build and actual executable smoke are mandatory before completion or commit. See `CLAUDE.md` and the Windows development guide for the executable lifecycle and persistent storage contract.
