import { Group, Mesh, MeshStandardMaterial, PlaneGeometry, Vector3 } from 'three'
import type { WorldBounds } from '../fly/FlyBody'

export const ARENA_BOUNDS: WorldBounds = {
  min: new Vector3(-1, 0, -1),
  max: new Vector3(1, 1, 1),
}

// The visual arena is intentionally minimal: an untextured floor and the
// three differentiated TokenHabitat coin piles. Physical bounds remain
// invisible so the experiment cannot be cluttered by placeholder props.
export class Arena {
  readonly group = new Group()
  readonly bounds = ARENA_BOUNDS

  constructor() {
    this.group.name = 'Arena'
    const floor = new Mesh(
      new PlaneGeometry(2, 2),
      new MeshStandardMaterial({ color: 0x111c28, roughness: 0.92, metalness: 0.05 }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.name = 'Floor'
    this.group.add(floor)
  }
}
