# Local model and tool updates

Settings → Models & tool updates checks public metadata without sending prompts,
source models or game files. First network check is explicit; once enabled,
daily checks run on startup. Preferences, check results, errors, active/previous
media pointers and maintenance jobs persist in the existing SQLite Library.

Tracked sources: installed-series Blender portable catalog; Unity release API;
TRELLIS v1/v2, TripoSG, Hi3DGen/normal and SDXL Hugging Face revisions; official
TRELLIS v1, Hi3DGen and TripoSG GitHub commits. Model revision equality is not a
full weight integrity audit or proof of quality. Unrecorded Hi3DGen local
revisions remain explicitly unverified. Unreal remains deferred, account-gated.

The first supported unattended installer is portable FFmpeg + FFprobe. FFmpeg's
official download page links the BtbN Windows build provider. Only stable Win64
GPL archives carrying GitHub SHA-256 metadata are accepted, not master/nightlies.
The installer checks archive size/hash/path safety/disk capacity, retains license
files, stages into Library/tools, and runs actual H.264 encoding, FFprobe stream
checks and full decoding. The codec diagnostic is never a Library asset.

Installation uses the shared durable CPU queue at low priority. Pause prevents
new maintenance admission; cancellation is checked during download/extraction.
Interrupted downloads restart rather than claiming byte-range resume. Existing
environments and external executables are never modified. A validated version
activates only when no production job is queued/running. Pending activation is
recovered after restart; rollback restores the previous pointer and disables automatic
installation so a daily check cannot undo that choice. Queued cinematic
jobs retain pinned paths. Active managed executable hashes are checked before use.

Auto installation is limited to this validated media adapter. AI weights and
editor upgrades require isolated dependency/license review and real pipeline
regression/quality benchmarking before promotion. Unity profiles stay pinned;
no silent major Blender upgrade, pip upgrade, git pull, paid service or license
acceptance is performed. Engine code comparisons do not assess local patches.

Backend acceptance actually downloaded the 193,977,587-byte stable archive,
verified SHA-256, installed n9.0.2-31-gc89d6ee1ca-20261021 and passed codec QA.
See evidence/updates_backend.json. Windows 0.8.14 passed 92 backend tests and native affected-feature acceptance:
visible upstream inventory at 1280/1536 widths, persisted opt-out, zero inference
assets, real portable download/hash/codec validation, activation, close/reopen and
rollback with automatic installation disabled. See evidence/updates_native.json.
