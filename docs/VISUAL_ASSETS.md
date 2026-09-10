# Open visual assets

## Canonical fly

- **Asset:** TuragaLab/Flybody `fruitfly.xml` plus referenced OBJ meshes
- **License:** Apache-2.0, as distributed by the upstream repository
- **Use:** canonical Drosophila body and wing/leg/abdomen assembly
- **Loader:** `frontend/src/rendering/FlybodyAsset.ts`

## World geometry

The floor and invisible arena bounds are procedural Three.js geometry. The
floor uses a small deterministic procedural texture; live market habitats are
procedural geometry with compact food/rot/trash/market details, and their
colored tops identify the encoded sensory parameters assigned to each habitat.
The world can render up to 128 market identities without downloading one
large prop pack per token.

The scene no longer uses unrelated bundled context props; only the coin/market
habitats are rendered as semantic objects.

Habitat particles are pooled instances and fly trails share one dynamic line
buffer. The scene has no unrelated decorative fly population. The four
additional render-only bodies attached to each primary CNS agent are explicitly
labelled followers and do not add brains, sensors, or consensus votes.

## Canva background

- **Asset:** `frontend/public/design/fruit-fly-capital-canva-background.png`
- **Format:** 16:9 PNG, text-free, suitable for Canva upload or a pitch-deck
  background
- **Intent:** dark graphite market-ecology atmosphere with restrained emerald,
  cyan, and warm-gold light; the center and upper-left remain usable for
  overlaid brand copy
- **Provenance:** generated for this project; it is a presentation asset, not
  a biological or market-data input
