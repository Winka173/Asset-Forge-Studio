# Local prompt and image understanding

The existing Single/Batch queue can admit a `prompt_analysis` CPU stage before concept/3D generation. The installed local model is Qwen3-VL-4B Instruct Q4_K_M through portable Ollama 0.40.8. The official model manifest observed on this machine is `84f7ed8042fa7cdbd902f7dcb7d0370e032095047cc3244179f263b77b5bc318`. The official runtime ZIP was SHA-256 verified as `04d1d43ac62c2deb0393307bb49fed7caf6b192de41bdd497aaa9488089d5552`.

Sources: https://ollama.com/library/qwen3-vl:4b-instruct-q4_K_M and https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct (Apache-2.0 weights); https://github.com/ollama/ollama and https://docs.ollama.com/windows (portable runtime; preserve bundled third-party notices).

## Data and execution

Original prompt text and source images remain immutable. Validated derived English instructions, source spans/hashes, image hashes, model digest and reference role are stored separately. Explicit image-purpose choices override model suggestions. Auto infers whether to reconstruct the image or make a new subject using observed reference style. The metadata-only Ollama batch-import adapter remains separate; this is not a claim that the previous importer already used a VLM.

Inference uses loopback HTTP only, fixed installed local model (no cloud variant), `num_gpu=0`, 8192 context, eight CPU threads and `keep_alive=0`. Actual Ollama process samples verified zero `size_vram` while interpreting the real Vietnamese castle prompt and tower concept. Text is processed in 3000-character chunks; at most five images are downsampled to 768px for analysis. Source inputs are retained at original quality. Chunk receipts are hash checked on retry; no mid-inference resume is claimed. Schema and numeric checks reject incomplete/malformed interpretation. Equivalent English count words are recognized; values cannot simply disappear.

Missing managed weights/runtime keep interpretation unavailable and do not download weights or call paid services. Supported deterministic parsing and explicit image-purpose generation continue. Auto without an interpreter uses measured reference colors when a new-subject prompt is present; it must not silently reconstruct the reference object. A per-project Advanced option can disable optional interpretation. Runtime/weights remain external to the desktop installer. AFS only terminates a runtime it owns.

## Concept layout guard

For newly generated concepts in interpreted workflows, a `concept_layout` CPU stage inspects actual image composition before heavy 3D inference. It reports single-asset suitability and specific observed issues (separate views/panels, cropping, absent/wrong subject). A connected castle with several towers is allowed. This is inferred composition screening, NOT artistic approval, geometric QA, PBR validation or Meshy parity.

An unsuitable concept stays immutable. Bounded concept repair changes the seed and adds single-view instructions while preserving the quality preset, steps, resolution and sources. Only candidates with a hash-bound suitable layout report can be selected. Repeated failure blocks that asset with an actionable reason; unrelated assets continue. Human concept checkpoints, when configured, remain separate.

## Real evidence and limits

`evidence/prompt_intent_real.json` records the actual Qwen CPU response and SDXL inference. It correctly distinguishes a castle request from the supplied tower image. The subsequent SDXL output contained inset views, demonstrating that correct language understanding does not guarantee a suitable concept. `evidence/concept_layout_real.json` records actual negative and positive model checks: the multi-panel SDXL output is rejected; an actual full castle GLB render is accepted. No synthetic model inference or artistic score is substituted.

Earlier `evidence/castle_reference_3d.json/png` separately prove real Maximum concept-to-TRELLIS-to-Blender-to-GLB delivery. That model has topology warnings; artistic quality, full reference-style fidelity and Meshy equivalence remain unapproved. Complex translations, architectural inference, reference interpretation and VLM visual screening can be wrong; the inferred specification and original source are reviewable in Production.

Actual repair execution retained Maximum / 50 steps / 1024px and changed seed 42 to 43. The resulting image was accepted by the VLM layout check, but human inspection by the developer observed an illustrated background, border/text and weak reference-style fidelity. This demonstrates a false-negative/coverage limitation: layout screening is not proof of isolated-background, style or artistic suitability. Those quality checks remain open. No artistic approval was assigned.
