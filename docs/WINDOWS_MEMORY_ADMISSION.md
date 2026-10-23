# Separate Windows physical RAM and system commit

The real native castle completed, but its next same-profile job was held:
38.28 GiB physical RAM available versus a learned 37.67 GiB allowance plus
2 GiB reserve. The allowance came from the maximum of resident RSS and private
committed bytes, so private commit was incorrectly used as physical demand.
Measured worker peaks were 24.77 GiB RSS and 31.89 GiB private commit.

Windows charges commit when pages are committed, while resident physical demand
changes when pages are accessed. These are separate resource budgets, documented
by [Microsoft's PERFORMANCE_INFORMATION contract](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-performance_information).
The fix uses that documented `GetPerformanceInfo` system API through ctypes,
without a new Python dependency, external service or administrative install.

The existing shared scheduler and host-resource ledger now reserve both:

- Physical allowance: measured worker-tree RSS plus 15% and 1 GiB, with existing
  stage floors unchanged (32 GiB for full TRELLIS.2).
- Commit allowance: measured private committed bytes with the existing margin
  and floor; available system commit is checked independently.
- Both retain the existing 2 GiB headroom. Pending claims subtract their
  unrealized physical and commit portions separately from actual system values.
- Missing Windows commit measurements block admission. Other platforms keep
  the earlier conservative mixed-budget behavior. Unknown claims remain blocked;
  owned orphan GPU workers still prevent new GPU admission. No concurrency,
  engine, quality, steps, resolution, texture or source changes are made.

New observations store both counters monotonically. A legacy mixed observation
is split only if its existing same-profile job and retained `resources.json`
samples prove both peaks and agree with the stored mixed peak/header. The update
is serialized in SQLite and retains the original observation. Missing,
inconsistent or unrelated legacy data stays conservative. No asset, prompt,
version, job, approval or export migration is performed.

New ledger claims keep the old combined `allowance_bytes` as a conservative
compatibility value for an older AFS process sharing the same machine lock.
New readers use explicit physical/commit fields. Dead claims are removed only
after the existing owner/child identity checks; no user processes are killed.

The actual same castle profile now needs **34 GiB physical RAM including reserve**
and **39.67 GiB commit including reserve**. At measurement time, 37.98 GiB
physical and 60.03 GiB commit were available, so the real check allowed it.
All queue/configuration IDs remained unchanged and no GPU job was launched by
that diagnostic. This is a planning guard, not protection against arbitrary
later external allocations or every possible Windows resource failure.

Fourteen targeted tests pass: separate shortages, independent pending claims,
release, monotonic estimates, same-profile legacy recovery, four unproven legacy
origins, unknown/orphan claims, unavailable counters and the real Windows API.
Controlled counter tests are admission arithmetic, not simulated successful AI.
The full 219-test backend suite passed in 204.38 s during the 0.9.18 build.

Evidence: [actual before/after check](evidence/host_commit_actual_v0918.json),
`desktop/verify-host-commit-native.mjs` and the final native report after the
new Windows acceptance run. The native harness deliberately restores only the
real isolated QA Library's old mixed observation, then requires recovery from
the actual castle samples and runs a new local Archer asset through real
inference, Blender, QA and automatic GLB delivery. Previous castle files must
remain unchanged through restart. It does not edit installed models or fabricate
measurements/artistic approval.

Final packaged Windows 0.9.18 acceptance passed. The new Archer asset took
729.02 s end-to-end (TRELLIS.2 worker 210.61 s), preserved the chosen source
image, ran real Blender/PBR preservation and technical QA, delivered one
66,589,200 B GLB plus manifest, then closed/reopened without duplicate jobs.
Both previous castle delivery files stayed byte-identical. Actual admission
receipt proves schema-2 counters and recovery of the declared legacy fixture
from the original same-job samples, with the 32 GiB floor / 2 GiB reserve intact.
Evidence: [native result](evidence/host_commit_native_v0918.json) and
[native screenshot](evidence/host_commit_native_v0918.png).

The optional Qwen concept-planning step did not complete on this explicit Source
request. The persisted report correctly says `not_evaluated` and uses the
unchanged original text/source fallback. That is not a successful LLM analysis
claim, and the screenshot exposes it. It did not prevent the direct source-image
geometry route. Artistic status remains `not_reviewed`; no tower/Meshy quality
equivalence follows merely from technical delivery.
