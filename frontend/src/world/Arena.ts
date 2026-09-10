import { CanvasTexture, Group, Mesh, MeshStandardMaterial, PlaneGeometry, RepeatWrapping, SRGBColorSpace, Vector3 } from 'three'
import type { WorldBounds } from '../fly/FlyBody'

const FLOOR_Y = -0.012

export const ARENA_BOUNDS: WorldBounds = {
  min: new Vector3(-1, 0, -1),
  max: new Vector3(1, 1, 1),
}

// The fallback exists only while the city asset is unavailable. The normal
// scene contains the authored city, its floor, the habitats, and the flies.
export class Arena {
  readonly group = new Group()
  readonly bounds = ARENA_BOUNDS

  constructor() {
    this.group.name = 'Arena'
    const floorTexture = createFloorTexture()
    const floor = new Mesh(
      // The flight volume remains exactly 2 m x 2 m. This larger presentation
      // floor prevents the free camera from looking past the room boundary at
      // the default orbit distance; it does not extend the physical bounds.
      new PlaneGeometry(6, 6),
      new MeshStandardMaterial({ color: 0x727a74, map: floorTexture, roughness: 0.94, metalness: 0.02 }),
    )
    floor.rotation.x = -Math.PI / 2
    // The GLB road is intentionally a few millimetres above this fallback.
    // It remains visible in holes in the source city without z-fighting with
    // the authored road surface.
    floor.position.y = FLOOR_Y
    floor.name = 'StreetFloor'
    this.group.add(floor)
  }

  /** Hide only the synthetic safety floor once the supplied city floor loads. */
  setFallbackFloorVisible(visible: boolean) {
    const floor = this.group.getObjectByName('StreetFloor')
    if (floor) floor.visible = visible
  }

}

function createFloorTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const context = canvas.getContext('2d')
  if (!context) return undefined
  const image = context.createImageData(canvas.width, canvas.height)
  let seed = 0x5eed
  for (let index = 0; index < image.data.length; index += 4) {
    seed = (seed * 1664525 + 1013904223) >>> 0
    const noise = 112 + Math.floor(((seed >>> 8) & 0xffff) / 65536 * 28)
    image.data[index] = noise
    image.data[index + 1] = noise + 5
    image.data[index + 2] = noise + 4
    image.data[index + 3] = 255
  }
  context.putImageData(image, 0, 0)
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  texture.wrapS = RepeatWrapping
  texture.wrapT = RepeatWrapping
  texture.repeat.set(9, 9)
  return texture
}
