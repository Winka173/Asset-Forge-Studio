# SDXL conditioning identity - Windows 0.9.16

New concept jobs persist the actual conditioning policy, worker/helper hashes,
tokenizer and model-configuration hashes, Python version and versions of eight
installed runtime packages. Admission reads metadata from the separate SDXL
environment without importing Torch or loading model weights. Before execution,
both the API and the real subprocess compare the saved identity with installed
files. The subprocess also binds its measured safetensor hashes to the admitted
checkpoint inventory before loading models.

A changed policy, runtime inventory, code, tokenizer/configuration, checkpoint or
prompt/negative/seed/steps/resolution/guidance blocks execution with an actionable
reason. Saved settings remain intact. No automatic quality reduction, engine
substitution or successful candidate registration follows a mismatch. This uses
the existing job states, scheduler and recovery model. Missing admission metadata
returns an HTTP 409 instead of a raw server error.

Legacy jobs explicitly report `legacy_default_unpinned` and retain the original
algorithm. They cannot retrospectively establish the environment identity that
existed when they were admitted.

## Unchanged generation behavior

The frozen policy is `sdxl_clip_windows_mean_v1`: 75 content tokens per CLIP
window, BOS/EOS/padding to 77 positions, penultimate hidden states concatenated
across windows, and arithmetic mean of **all** CLIP-2 pooled vectors. Positive
and negative use equal window counts; empty negative windows remain included.
More than 64 windows is an explicit error, never silent truncation. Maximum
still uses the existing 50 steps / 1024 resolution. This release does not adopt
the separately researched first-chunk pooling experiment.

The actual generation report now records content counts and ranges per encoder
and direction, empty windows and prompt hashes. Ranges are content-token offsets,
not character spans or provenance mappings. Retaining every token does not prove
that SDXL obeyed the requested architecture, materials or palette.

## Evidence and limits

The real castle was replayed sequentially in the actual isolated SDXL environment
with the legacy request and a new locked request. Both PNGs are byte-identical to
the retained concept:

`a0600ce07ec93d26e7ba0dbfee89a7701b6756d99a355ac6a569f5007270c8b9`

| Actual replay | Wall time | Sampled entire-GPU peak |
| --- | ---: | ---: |
| Legacy | 28.27 s | 10,272 MiB |
| Locked | 27.25 s | 10,428 MiB |

Both measured 410 positive / 61 negative content tokens, six windows and five
empty negative windows. Torch peak allocated was 5,602,789,888 B and reserved
7,845,445,632 B in both. Whole-device samples include the desktop and other
processes and may miss transients; ordering/cache precludes a speed comparison.
Original source/configuration/image hashes remained unchanged. Evidence:
[actual replay report](evidence/concept_conditioning_replay_v0916.json) and
[reproduction helper](evidence/concept_conditioning_replay_runner.txt).

Targeted tests cover ten real admission mismatches without launching inference,
legacy reporting, exact packing boundaries and oversize rejection. Deliberately
altered expectations are negative fixtures, not fabricated successful AI outputs.
The full 207-test backend suite and TypeScript/Vite passed during Windows build.

Native acceptance uses a fresh isolated SQLite Library, actually generates a
Maximum concept, checks measured encoding/configuration/idempotency, closes and
reopens Windows, requires explicit Resume, then tests two deliberately stale
queued contracts. A stale worker identity is rejected before subprocess launch;
a stale weight inventory is rejected after real weight hashing, before model
inference. No installed source, tokenizer or weights are edited. The original
PNG and Not Reviewed artistic state must survive. The harness opens the actual
asset and stage history before taking screenshots. See the final native report
alongside the build and generic native smoke reports. Earlier harness runs that
failed ambiguous UI selectors are retained under `.local/concept-conditioning-native`;
they are not counted as successful native acceptance.

Runtime version inventory does not hash all transitive dependency source,
CUDA kernels or GPU drivers. This is a concrete drift guard, not a general
cross-machine deterministic-generation guarantee. No new 3D inference or
artistic/Meshy parity is established. The castle's style/material fidelity and
geometry comparison remain separate quality work.
