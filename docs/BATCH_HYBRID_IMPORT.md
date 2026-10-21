# Batch Hybrid Import — audit and acceptance

> Historical import acceptance below predates Automation V3. Current Auto workflow selects all 349 entries, including 37 FUTURE, as explicitly requested for Generate All; source FUTURE labels remain intact. Analyze still schedules zero GPU work. Expert retains explicit specification controls. See [Automation production](AUTOMATION_PRODUCTION.md).

## Root cause

The original Analyze action called `/api/batches/analyze`, a deterministic local parser, not a local LLM. The actual Downloads file is 2,640,840 bytes / 2,630,112 decoded characters. The request schema capped input at 1,000,000 characters, so FastAPI returned 422 before entering the parser. The frontend stringified the entire validation error, including `input`, escaped newlines and `ctx`. No valid manifest reached frontend state; the empty review panel was the result of that rejected request. CSS did not hide a successfully parsed manifest in this failure.

There were two further parser blockers: Markdown supported only tables/bullets and had a 200-row ceiling. It did not recognize the document's `# ASSET_ID — Title` blocks or distinguish nested `# RUNAVELLE` Bible headings. Large input could also exhaust localStorage's UTF-16 quota; autosave errors were unhandled. None of these failures established that an AI analysis had occurred.

## Implemented behavior

- Content-based JSON/CSV/Markdown/TXT detection; structured lists and long-form ID-heading documents. No prose-to-assets invention. Maximum 10 million decoded characters / 1,000 expanded assets; explicit errors rather than truncation. Multipart uploads spool and have a 16 MB read cap.
- The supplied file deterministically yields **349 original IDs**, **312 primary** and **37 FUTURE** entries. These are measured from source headings and status blocks, not fabricated result rows. The source's declared expected count is checked against parsed count. Internal shared Bible headings remain inside their asset prompt.
- Original uploaded bytes, decoded UTF-8 text, file SHA-256, complete individual prompt blocks, line/character spans and per-prompt hashes are retained. Original download checks the saved hash. Editing generation prompts preserves read-only source provenance. Internal UUIDs remain separate from original IDs.
- Invalid/duplicate IDs, empty long-form bodies, mismatched declared counts and schema violations fail explicitly. Legacy structured entries missing a prompt can remain reviewable drafts with a warning and cannot generate. Proposed dimensions are extracted only from explicit dimension fields and are never auto-confirmed.
- Analyze saves a paused draft and creates **zero jobs**. FUTURE rows start deselected. Bulk selection excludes FUTURE unless the user explicitly selects them. A single atomic selection endpoint replaces hundreds of parallel update requests. Generation requires explicit selection, valid dimensions and specification confirmation.
- The UI shows loading/success/readable errors, diagnostics and provenance, 50-row pagination, search, row editing, selection totals and Generate Selected. File-backed input defaults to a summary and bounded preview rather than a multi-megabyte textarea. Autosave quota failures show a warning and preserve current-session input. Saved batches restore from SQLite across desktop relaunch.

## Optional local semantics

`engines/local_semantics.py` implements the real loopback Ollama HTTP adapter using [structured JSON schemas](https://docs.ollama.com/capabilities/structured-outputs) and [installed model discovery](https://docs.ollama.com/api/tags). It never installs or pulls models and rejects non-loopback endpoints, redirects and cloud-tagged models. User-triggered metadata analysis enters the shared scheduler as a CPU job (`num_gpu=0`), processes each prompt in 4,000-character chunks, validates each result with Pydantic, binds suggestions to source hashes/model digest and saves checkpoints. Unknown dependency IDs or malformed output fail validation. Original prompts and generation settings are never replaced by suggestions.

The machine's actual Ollama/llama.cpp probes found no reachable service or installed executable. Consequently real LLM inference is **unverified and unavailable**, visibly disabled in this release. Parsing, source preservation and review do not depend on it. No synthetic AI result is used as evidence. Ollama CPU execution must be benchmarked with a compatible installed model before claiming verified semantic extraction quality.

## Acceptance evidence

`tests/test_runavelle_import.py` reads the actual Downloads file (or `AFS_RUNAVELLE_SOURCE`), checks every original span/hash, original-file round trip, all counts and selection. It verifies three real persisted concept jobs with full `user_prompt` after explicit confirmation; existing project art-direction suffixes are stored separately in the effective `prompt`. Tests do not run inference or claim model output quality.

`desktop/verify-batch-import.mjs` drives the actual packaged EXE/WebView2: multipart import, all seven table pages, FUTURE defaults, row editing, three selected/confirmed assets, visible enabled Generate, three independent real queued jobs and desktop relaunch. A briefly held shared GPU lock prevents these QA jobs from entering inference; they are explicitly cancelled before releasing it. This verifies queue admission, not generated images or Meshy parity. Reports and actual screenshots are retained under `.local/batch-import-native/` and copied into `docs/evidence/` after passing.

Verified release results: **Expansion 0.4.1: 36 backend tests + build/native smoke + actual 349-asset native acceptance PASS**; **Stable 0.3.5: 34 backend tests + build/native smoke + actual 349-asset native acceptance PASS**. Expansion exercised content autodetection, Stable explicitly selected Markdown manifest. Browser regression also verified actual 422 messages, source download checksums and a handled browser-storage quota error. The generic native smoke now records expected connection-refused messages only during intentional owned-backend shutdown; running-app network failures and JavaScript errors still fail.

Evidence: `evidence/batch_import_expansion_native.json`, `batch_import_expansion_manifest.png`, `batch_import_expansion_reopened.png`, `batch_import_stable_native.json`, `batch_import_stable_manifest.png`, the two edition build/smoke reports, `batch_import_stable_delivery.json` and `batch_import_browser.json`. These records preserve the actual source SHA-256 `8234e96aed3529fd40e822631d6f9ceaafa2c50e7f56e9e1de9884bb5f52976c`. The source file itself remains local and is not committed to Git.
