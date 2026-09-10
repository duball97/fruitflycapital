# Open visual assets

## Canonical fly

- **Asset:** TuragaLab/Flybody `fruitfly.xml` plus referenced OBJ meshes
- **License:** Apache-2.0, as distributed by the upstream repository
- **Use:** canonical Drosophila body and wing/leg/abdomen assembly
- **Loader:** `frontend/src/rendering/FlybodyAsset.ts`

## World geometry

The floor and invisible arena bounds are procedural Three.js geometry. The
floor uses a small deterministic procedural texture; the three token coin
piles are procedural geometry and their colored tops identify the synthetic
sensory parameters assigned to each habitat.

The scene also uses two locally bundled Poly Haven CC0 props for restrained
world context:

- `metal_trash_can/metal_trash_can.gltf`
- `cardboard_box_01/cardboard_box.gltf`

They are loaded by `frontend/src/world/PropLibrary.ts`. The props are not
market signals and are not used as privileged brain inputs; they are ordinary
world geometry that the existing ray-based visual sensor may encounter.

Habitat particles are pooled instances and fly trails share one dynamic line
buffer. The scene has no unrelated decorative fly population. The four
additional render-only bodies attached to each primary CNS agent are explicitly
labelled followers and do not add brains, sensors, or consensus votes.
