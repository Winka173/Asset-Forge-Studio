# Observed failures and classification

| Evidence | Root cause | Confidence | Recovery boundary |
|---|---|---|---|
| User jobs b2a69240 / 5167feb9, concept_layout.json | SDXL produced multiple views/panels; bounded layout repair exhausted | Confirmed reports; visual inference is fallible | Concept, not 3D engine |
| Isolated v21 / fffcbd80 report | Qwen boolean says background is nonplain while its observation calls it a plain gray gradient | Confirmed inconsistent output | Evaluator/schema, not engine switch |
| Isolated v21 image 55685029 | Close-up doorway/house, cropped boundary rather than complete castle | Direct image inspection; no user art approval | Replan subject/composition |
| Isolated v21b / first concept | Repeating architectural panels | Actual Qwen report; inspect image evidence | Concept conditioning |
| Isolated v21b / second concept | Castle/house/tower ambiguity; single-object screening alone cannot establish required castle structure | Direct image inspection | Structural spec/assembly route |
| v21b inference / v21c concept | Explicit user-requested stop for workflow review | Confirmed process stop and persisted BLOCKED reason | Retry interrupted stage only |
| Historical Hi3DGen run 153507 | Missing VAE checkpoint filename | Actual recorded exception, historical | Environment/weights; not new seed |
| Historical TRELLIS v1 run 153324 | Failed initialization; inspect original log before asserting detailed cause | Recorded failed run; original path unavailable | Environment diagnostic |

Additional hypotheses, not proven causes: SDXL reads negated nouns in positive conditioning; long CLIP chunks weaken subject emphasis; image-aware planning can copy reference architecture despite a style-only instruction. New conditioning separates negatives, image appearance and text-only geometry planning; real comparisons are required before claiming improvement.

Execution taxonomy codes: MODEL_DEPENDENCY_MISSING, CUDA_ABI_CONFLICT, CUDA_OOM, PROCESS_TIMEOUT, INPUT_OR_CONFIG_INTEGRITY, EMPTY_GEOMETRY, EXPORT_VALIDATION, INTERRUPTED, UNCLASSIFIED_EXECUTION. Environmental breaker counts exact engine/environment/device/profile; content rejection must not quarantine unrelated assets.
