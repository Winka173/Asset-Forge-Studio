# Decisions

- The 2026-10-22 Adaptive 3D Production + AI Quality Control user specification supersedes the prior proposal of adding mandatory VLM gates everywhere.
- Technical/mandatory structural validation is authoritative; uncertain aesthetic observations are advisory in Auto. Never turn uncertainty into artistic approval.
- Reuse the existing coordinator, SQLite, scheduler, status dimensions, Library and revision/export transactions.
- Diagnose each failed stage from actual logs before changing engines. Repeating a missing dependency with a new seed is not recovery.
- Architecture may use verified parametric geometry when it satisfies declared requirements; do not force all architecture into Blender or downgrade a required photoreal/AI-textured/exact-image route.
- Image interpretation and geometry planning are separated so a style reference cannot silently become the target object. Their results remain inferred and reviewable.
- Keep user Library untouched during acceptance. No unrelated Video/Audio expansion work in this task.
