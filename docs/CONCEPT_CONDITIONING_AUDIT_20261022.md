# Local SDXL conditioning audit — 2026-10-22

Read-only CPU/tokenizer audit of the real castle and original Runavelle V4 document. No inference, engine installation, model download, quality-setting change or source-prompt rewrite was performed. This is diagnostic evidence, not a claim of improved visual quality.

## Actual implementation

The executable worker is `engines/sdxl_worker.py`. It already implements explicit long-prompt encoding: each CLIP encoder receives windows containing up to 75 content tokens plus BOS/EOS; the per-window penultimate hidden states are concatenated. Positive and negative conditioning use the same window count. SDXL receives those embeddings directly, bypassing the pipeline's default single-window tokenizer. CLIP-2 projected pooled outputs are averaged across all windows. There is a hard error above 64 windows instead of silent truncation.

Installed pipeline source confirms SDXL accepts supplied `prompt_embeds`, `negative_prompt_embeds`, `pooled_prompt_embeds` and `negative_pooled_prompt_embeds`. No additional package is needed for controlled conditioning research. Its default string-prompt path does truncate at 77 total tokens, but that path is **not** used by this worker.

## Actual castle

Source request: `.local/castle-quality-route/20261022T132736Z/Library/jobs/a26c9ecf305344dabfd9c89d51a93253/request.json`.

Request SHA-256: `51332efcf2c69cc5bc53343f3ab5bd289997bbf06939a4ed7626983852130625`.

Both locally cached CLIP tokenizers measured the same counts:

| Item | Measured value |
| --- | --- |
| Positive content tokens | 410 |
| Negative content tokens | 61 |
| Encoded windows | 6 |
| Positive window content lengths | 75, 75, 75, 75, 75, 35 |
| Negative window content lengths | 61, 0, 0, 0, 0, 0 |
| First connected/whole-silhouette anchor | approximately token 213, window 3 |
| Inherited project material language | approximately token 269, window 4 |
| Maximum detail instruction | approximately token 349, window 5 |
| Final full-object framing instruction | approximately token 381, window 6 |

The saved generation report independently confirms `chunks: 6`, `tokens_not_truncated: true` and `pooled: mean across CLIP-2 chunks`. There is **no evidence of 77-token truncation in this actual run**. Keeping tokens is not proof that the model obeyed every constraint.

The negative pooled vector is the arithmetic mean of one nonempty-window vector and five empty-window vectors. This is a real implementation property. Its effect on visual fidelity has not been isolated; describing it as a demonstrated cause of failure would be unsupported.

### Color, material and view findings

- Positive conditioning asks for blue/brown/beige/gray; measured reference palette adds brown/charcoal/gray/ivory; project material language adds ivory limestone, chestnut oak, midnight blue slate, aged bronze, navy/gold cloth and cyan mana. These are multiple overlapping appearance descriptions. None declares an exclusive palette, so this audit found **no proven logical color/material contradiction** in the castle request.
- The established castle concept's orange/brown roofs do not establish correct compliance with midnight-blue slate. Token retention alone cannot certify palette fidelity; an image-region assessment or human review is still needed.
- Orthographic projection and a three-quarter viewing angle are compatible. The inherited `orthographic view` must not be flagged as a contradiction merely because the request also says three-quarter view.
- The negative `orthographic sheet` excludes a sheet composition, not every orthographic view. No exact positive/negative phrase conflict was found in the actual compiled castle prompt. Shared words such as `view` are not sufficient evidence of a conflict.
- A conversational fragment, `create for me 1 castle, style similar to this image ref`, remains in window 3. It came from the numeric-preservation fallback in `intent_adapter.py` because the generated description used an article rather than the explicit count `1`. This is retained user meaning, but it also reintroduces conversational/reference words the planner had been asked to exclude. It is not proven to have caused this image's defects.
- Hex palette codes are tokenized as individual letters/digits across windows 4–5. The pipeline does not guarantee precise colorimetry from those textual tokens. Original hex constraints should remain in metadata regardless of any later tested conditioning policy.

## Actual 349-prompt source

File: `C:/Users/Winka/Downloads/Runavelle_V4_ALL_349_Model_Prompts.md`.

Bytes: 2,640,840. SHA-256: `8234e96aed3529fd40e822631d6f9ceaafa2c50e7f56e9e1de9884bb5f52976c`.

The real explicit-ID headings split into **349 prompts, 312 primary and 37 FUTURE**. Both cached tokenizers measured the original individual prompt bodies at **933–1,903 content tokens, median 1,730**; all exceed one CLIP window and none exceeds the worker's 4,800-content-token ceiling. These are **raw source** counts, not the size of later Qwen-derived image descriptions.

The source includes production/export and review instructions alongside visual requirements. For example, the first castle asks for separate orthographic front/back/left/right/top and perspective proof, and mentions Meshy/paid-batch authoring requirements. These are source deliverable instructions, not a request to draw a multi-view contact sheet in the concept image. The original text must remain immutable while derived visual conditioning separates deliverables from image composition. Passing it directly through the fallback does not provide that semantic separation.

## Narrow next changes

1. Add truthful diagnostics before changing image behavior: prompt/tokenizer hashes, encoding policy identity, content counts per encoder, total windows, empty positive/negative windows, window-to-source/provenance spans, and the actual interpretation model/digest/status. Explicitly show deterministic original-text fallback when Qwen was not used or failed.
2. Persist encoding policy in **new** effective configurations before experimenting. Current effective configuration locks prompt/negative/size/steps/seed, but does not identify the chunk/pooled-vector policy. Legacy queued/retry jobs must dispatch the existing algorithm rather than silently adopting a future policy.
3. If testing alternative negative pooling or anchor placement, make one explicit derived-policy delta at a time, with the same model revision, prompt, negative prompt, seed, resolution, sampler and steps. Keep baseline outputs and record actual VRAM/time plus full-image and cropped A/B evidence. Do not infer visual improvement merely from fewer windows or more constraints in the first window.
4. A future planner can separate inherited requirements, explicit user overrides and inferred ordinary details in a structured, validated contract. Do not silently remove user exclusions or translate workflow instructions into visible geometry. The current numeric-token comparison is useful but cannot prove semantic preservation of all materials/exclusions.

The complete decoded-window/per-asset-token measurements are retained in [the evidence JSON](evidence/concept_conditioning_token_audit_v0912.json), and the exact reproduction helper is retained as [a text snapshot](evidence/concept_conditioning_token_audit_runner.txt). The original working copies live under `.local/audit_concept_conditioning.py` and `.local/concept_conditioning_audit.json`. The helper loads only cached CLIP tokenizers in the isolated SDXL environment and does not load model weights.


## Actual controlled pooling experiment, 2026-10-23 local

Ran the retained accepted castle prompt/negative, seed 43, Maximum 50 steps/1024 and cached SDXL weights twice in isolated copied workers. Current mean pooling exactly reproduced the retained input concept byte-for-byte (SHA-256 a0600ce07ec93d26e7ba0dbfee89a7701b6756d99a355ac6a569f5007270c8b9). First-chunk pooling changed architecture and left more room above the flags at this seed; both still had warm roofs, so inherited midnight-blue slate fidelity is unresolved. All six token windows remain encoded. No quality improvement, general framing guarantee or 3D acceptance follows from one image pair, and neither product worker nor quality config changed.

Measured wall time mean 53.55 s / first 32.95 s, sampled whole GPU peak 9030 / 9138 MiB; both Torch allocated 5,602,789,888 B and reserved 7,845,445,632 B. Order/cache and concurrent host work confound a speed comparison; no throughput claim. One heavy GPU lock plus host-RAM admission used, no downloads or installed-source edits. Evidence: evidence/castle_sdxl_pooling_research.json, actual mean/first PNGs and reproducible runner.
