# Fruit Fly Capital visual rendering

The visual layer is presentation only. It does not alter MaleCNS topology,
neural state, sensor encoding, physics units, or actuator semantics.

## Minimal dependency plan

- `three` remains the scene, camera, GLTF/OBJ loaders, instancing, and buffer
  management layer.
- `postprocessing` is the only added runtime dependency. It provides SMAA,
  ACES filmic tone mapping, selective bloom, vignette, and an optional low-cost
  normal/AO pass.
- No runtime asset URL is required. The optional world props are bundled under
  `frontend/public/models/polyhaven/` and retain their local CC0 license files.

## Quality presets

`performance` is the default. It uses a capped device pixel ratio, SMAA, and
tone mapping while keeping bloom and AO disabled. Press `P` in the browser to
toggle the `demo` preset. The demo preset enables subtle bloom, vignette, and
half-resolution SSAO; it is intended for a presentation machine, not for
benchmarking a larger swarm.

The fixed body update remains 120 Hz and the browser render loop remains
`requestAnimationFrame`. Post-processing is not inserted into the neural or
physics loop.

## Canonical fly LOD

Every visible agent still uses the same canonical Flybody XML/OBJ geometry.
LOD only changes which already-loaded XML geoms are drawn:

- `full`: every canonical geom for the selected or nearby agent;
- `medium`: head, thorax, abdomen, and both wings;
- `low`: a smaller canonical silhouette for distant agents.

No billboard or replacement fly is introduced by the LOD system. Independent
agent bodies, sensors, brains, and trajectories remain unchanged.

## Habitats and particles

The three token habitats remain coin-pile identities. Their column, ring, and
particle intensity are derived from the existing provider-neutral
`HabitatProperties` (`brightness`, `particleActivity`, `chaos`, and motion),
not from a hidden target or scripted path. All particles are instances of one
pooled `InstancedMesh`; fly trails are one dynamic `LineSegments` buffer.

Two restrained local CC0 props (one metal trash can and one cardboard box) are
loaded asynchronously for scene context. A failed optional prop load cannot
block the biological world.

## Presentation and debug modes

The initial view is `DEMO`: product title, agent count, CNS-active count, and a
compact pressure status. The camera starts in the swarm overview phase of the
auto director so the biological agents are visible immediately. Press `` ` `` or click the top-right toggle to enter
`DEBUG`, which exposes socket state, causal telemetry, population state,
camera targeting, scenarios, and render metrics.

Camera keys are `1` free orbit, `2` selected-agent follow, `3` first-person,
`4` side/debug, `5` token cinematic, and `6` auto director. None of these
cameras gives the brain privileged coordinates; they only change the human
observer's view.
