# Open visual assets

## Canonical fly

- **Asset:** TuragaLab/Flybody `fruitfly.xml` plus referenced OBJ meshes
- **License:** Apache-2.0, as distributed by the upstream repository
- **Use:** canonical Drosophila body and wing/leg/abdomen assembly
- **Loader:** `frontend/src/rendering/FlybodyAsset.ts`

## World geometry

The current experiment intentionally contains no room props or placeholder
landmarks. The floor and invisible arena bounds are procedural Three.js
geometry. Token coin piles are also procedural geometry; their colored coin
tops identify the synthetic sensory parameters assigned to each habitat. The
floating labels and orbit rings were removed from the experiment view because
they were presentation-only clutter, not sensory inputs.
