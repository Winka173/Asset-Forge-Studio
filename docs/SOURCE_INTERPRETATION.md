# Keep Source reconstruction independent from unused concept planning

The real 0.9.18 Archer run completed geometry/Blender/QA/export, but its optional
prompt report was `not_evaluated`: Qwen's second, image-independent **new-concept**
planning call did not finish. The first image-aware interpretation had completed.
Because reconstruction uses the supplied Source image, that second call was
unnecessary and could discard a valid translation/role analysis.

The adapter now finishes each Source chunk after the existing image-aware local
interpretation, schema validation, explicit-numeric preservation and reference
role handling. It retains the translated original request as generation text,
adds no inferred geometry, records `concept_planning.status=skipped` with the
actual reason, and leaves planning duration null because no call was made.
No new concept is implied. Original text, references, hashes and checkpoints
remain unchanged and version-compatible.

Style/new-subject and text-only routes still perform the separate text-only
planning call. A castle with a tower style reference must keep that separation;
this change does not pass reference pixels into castle concept planning. The
optional-interpreter fallback remains explicit when the first analysis itself
fails. Source image geometry, engine, seed, steps, PBR and Quality Lock do not
change. Previously queued generation configurations are not rewritten.

Three added regression tests use declared schema fixtures, not real LLM evidence:
one Source call / checkpoint reuse, Style's separate text-only call, and rejection
of lost numeric constraints. Six relevant tests pass; the full 222-test backend
suite passed in 186.44 s during the new Windows build, plus TypeScript/Vite.

Actual affected-feature native acceptance uses local CPU Qwen, the real Archer
reference and the packaged queue. A declared helper holds only the shared GPU
mutex while CPU interpretation runs; this is a scheduler fixture, not a GPU job
or fabricated mesh. The real reconstruction is admitted but must remain queued
with its full Maximum config and no inference subprocess. The harness requires
`interpreted`, actual model/digest, skipped concept-planning metadata, unchanged
translation/source, persisted checkpoint and no duplicate stage after restart.
It explicitly pauses the QA batch before releasing the mutex. The full genuine
Archer inference/Blender/PBR/export route was separately verified in 0.9.18;
this narrow test does not claim another 3D generation.

Harness: `desktop/verify-source-intent-native.mjs`. Final native/build reports
record completion. Personal data and installed model weights are untouched.

Final native 0.9.19 acceptance: `PASS_NATIVE_REAL_SOURCE_INTERPRETATION_NO_UNUSED_PLAN`.
Actual local analysis and geometry admission completed in 39.63 s, with model
digest `84f7ed8042fa7cdbd902f7dcb7d0370e032095047cc3244179f263b77b5bc318`.
The UI displays Understood request / archer tower / Reconstruct image and marks
concept skipped. Both persistent job IDs, result hash, original prompt/image,
Maximum32/4K config and Not Reviewed status survive native restart; inference
never started in this scoped test. The initial harness used an incorrect
texture field name; it was corrected to the existing `texture.size` contract
and fully rerun, without changing product code or counting that failure as a pass.
Evidence: [native report](evidence/source_intent_native_v0919.json) and
[native screenshot](evidence/source_intent_native_v0919.png).
