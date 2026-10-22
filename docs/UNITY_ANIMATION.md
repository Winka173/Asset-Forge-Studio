# Existing animation Unity profile

The Unity animation bridge extends the existing `unity_import` job, CPU resource
slots, cancellation, timeout, persistent queue and artifact history. It does not
create a second queue. No engine weights, paid service or extra installer is used.

## Supported workflow

In Library or Production, preview an existing animated model and expand **Unity
animation package**. Validate animation in Unity queues a CPU job. The app shows
the actual stage and offers the package and reports only after validation passes.
The default GLB Only profile is unchanged and never requires Unity validation.

The initial verified profile is Unity 6000.4.8f1 / Built-in, a single existing
Generic skinned clip, starting at zero, using LINEAR or STEP key interpolation.
Textured models, morph targets, extra influence sets, multiple clips and GPU
animation captures remain unavailable in this profile. Unsupported inputs get an
explanation before any native job is queued. Static PBR/LOD import uses the
existing separate profile.

The authoritative GLB is retained byte for byte, also included inside the package
as provenance. The FBX bridge is an additional derivative sampled at 120 fps,
without curve simplification. Blender reopens it and compares six source/FBX
deformation point clouds. This is sampled evidence, not lossless FBX conversion.

The independent `com.assetforge.animation` Editor package performs:

1. Generic FBX import with compression off, four-influence weights, zero weight
   pruning threshold, preserved bone references, animator/controller, prefab and
   serialized scene.
2. Real normalized-weight, bind-pose, bone count, clip duration, finite vertex,
   metric dimensions and motion-amplitude checks. It samples both the clip and
   Unity's PlayableGraph and CPU-skinned vertices; an idle/nonmoving result fails.
3. Cold reopen in a separate Editor process and validation of serialized outputs.
4. Package import into another empty AFS-owned project, waiting for the actual
   import-completed event before checking references and motion again.

The source tool/clip hash is locked at enqueue. Retry uses a new immutable
validation directory. Shutdown/cancel stops only the stage's child processes.
No user's Unity game project or Unity license is modified.

## Export/version safety

A validated `.unitypackage` is offered only for its exact source artifact. A
package for v1 is not available for v2 merely because both share an asset ID.
Re-export uses actual stored outputs and hashes without new AI inference. Export
preferences cannot reduce the internal master or erase source data. Technical
validation never assigns artistic approval or clears commercial provenance.

## Evidence and limitations

`tests/test_unity_animation.py` runs real Blender and installed Unity when
available; it checks queue idempotency, CPU classification, all three Editor
reports, real package export and rejection of a mismatched-version package.
`desktop/verify-unity-animation.mjs` tests the packaged Windows controls, paused
queue/restart/manual resume, retimed 1.666667-second clip, actual native outputs,
export hashes and version-specific UI. It delays an actual backend response while switching versions to ensure old request state does not appear on the new selection. Final evidence is
`evidence/unity_animation_native.json`.

The licensed technical fixture is Rigged Figure, Cesium 2017, CC BY 4.0. See
`evidence/animation_retime_fixture_license.json`. It has 19 joints and is not an
AFS-generated character. The initial successful probe measured 312 weighted
vertices, normalized sums approximately 0.9999999 to 1, and source/sample motion
approximately 0.416865 m, including after clean import. Failed exploratory runs
remain under `.local/unity-animation-probe`; a failed clean import is not counted
as success.

No automatic rigging, humanoid retargeting, new motion generation, repaired loop
seam, foot-contact quality, root-motion quality, player performance, textured
animation PBR parity or artistic acceptance is established. Metric checks avoid
claiming a moving but incorrectly scaled rig is valid. The source's non-looping
motion is not silently converted into a seamless action.

API references: Unity's [CPU BakeMesh semantics](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/SkinnedMeshRenderer.BakeMesh.html)
and [Generic animation import](https://docs.unity.com/en-us/engine/6000.7/script-reference/unityeditor/modelimporteranimationtype).
