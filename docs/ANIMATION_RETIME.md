# Existing animation clip revisions

This slice edits an existing skinned GLB clip. It does not generate a character,
create motion, automatically rig a static mesh, or retarget a skeleton.

## Workflow

Open a real animated asset in Library or Production, select Refine, then choose
Slower / 0.75x or Faster / 1.25x. The equivalent precise prompt is
`Set clip 1 speed to 0.75x`. Clip numbers start at one. Auto selects the local
retime operation for that instruction. Verified speeds range from 0.25x to 4x.
Other prompt edits follow the existing capability planner; unsupported direct
editing is explained rather than reported as successful motion generation.

Check Plan does not enqueue work. Generate Revision persists the immutable delta
and inherits project constraints, references, quality and export preferences. A
paused queue retains the pending revision across restart and admits its job only
after Resume. The CPU operation uses the same scheduler and priority controls as
the rest of Production. It does not load AI weights or occupy a heavy GPU slot.

The GLB editor appends selected clip time accessors. Original binary data,
geometry, skin, materials and other animations remain intact. LINEAR and STEP
interpolation are supported; cubic-spline tangent retiming remains unavailable.
Times must be finite, strictly increasing, nonnegative and contained in their
declared buffer view. External-resource GLBs are unsupported for this operation.

Headless Blender imports the original and retimed clips and compares evaluated
deformed vertex positions at six matching normalized times. Dense models use
bounded deterministic vertex samples. Skeleton/vertex counts, measurable motion,
finite positions and scale-relative pose error are checked. The resulting GLB is
inspected again before artifact registration and export. Failure is a real failed
stage; no placeholder candidate is registered as validated.

For a previously delivered asset, the edited output is staged separately. Use
This Version publishes it through the existing atomic game manifest. Preview
original and Use / Restore This Version preserve rollback. Artistic status stays
not_reviewed. A concurrent status refresh cannot replace a newer explicit
publication pointer with a stale snapshot.

## Evidence and limits

`tests/test_animation.py` exercises real GLBs, actual Blender deformation QA,
unselected clip preservation, source hashes, staged delivery, publication and
rollback. It also interleaves an actual publication after a status snapshot to
check the persisted pointer is retained.

`desktop/verify-animation-revision.mjs` launches the packaged Windows app in an
isolated Library. It uses the actual Refine buttons, pauses/reopens/resumes,
checks one admitted CPU job, previews real motion/skeleton, publishes and rolls
back, compares versions, then reopens without duplicate jobs. Final native
results are in `evidence/animation_revision_native.json`. Earlier failed test
runs remain under `.local/animation-revision-native` for diagnosis; they are not
counted as passes.

Technical fixture: **Rigged Figure**, Cesium, copyright 2017, CC BY 4.0, from the
[official Khronos sample asset](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/RiggedFigure).
License metadata and the source hash are retained in
`evidence/animation_retime_fixture_license.json`. It is a licensed test fixture,
not an AFS-generated character or evidence of auto-rig quality. The source is
1.25 seconds with 19 bones; 0.75x produces approximately 1.666667 seconds.

The report records loop seam distance but does not repair a non-looping action.
Root motion quality, foot contact, semantic action quality, retarget quality and
Unity/Unreal native animation import have not been validated by this slice. A
Blender deformation comparison is sampled technical evidence, not exhaustive
proof or artistic approval. No Meshy quality equivalence is claimed.
