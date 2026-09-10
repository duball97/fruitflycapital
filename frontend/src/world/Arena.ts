import { BoxGeometry, CanvasTexture, CircleGeometry, CylinderGeometry, Group, Mesh, MeshStandardMaterial, PlaneGeometry, RepeatWrapping, SRGBColorSpace, SphereGeometry, Vector3 } from 'three'
import type { WorldBounds } from '../fly/FlyBody'

const FLOOR_Y = -0.012

export const ARENA_BOUNDS: WorldBounds = {
  min: new Vector3(-1, 0, -1),
  max: new Vector3(1, 1, 1),
}

// The visual arena stays sparse, but the floor has a small procedural concrete
// texture so the presentation does not read as an unlit debug plane.
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
    this.addStreetDetails()
  }

  /** Hide only the synthetic safety floor once the supplied city floor loads. */
  setFallbackFloorVisible(visible: boolean) {
    const floor = this.group.getObjectByName('StreetFloor')
    if (floor) floor.visible = visible
  }

  private addStreetDetails() {
    const details = new Group()
    details.name = 'StreetDetails'
    const lineMaterial = new MeshStandardMaterial({ color: 0xe0bd55, emissive: 0x3f2e0c, emissiveIntensity: 0.22, roughness: 0.62 })
    for (const z of [-1.9, 1.9]) {
      const line = new Mesh(new BoxGeometry(4.8, 0.006, 0.018), lineMaterial)
      line.position.set(0, FLOOR_Y + 0.006, z)
      details.add(line)
    }
    const oilMaterial = new MeshStandardMaterial({ color: 0x171b1d, transparent: true, opacity: 0.55, roughness: 0.98 })
    for (const [x, z, sx, sz] of [[-1.8, -0.9, 0.42, 0.16], [1.6, 0.7, 0.31, 0.12], [-0.7, 1.65, 0.25, 0.1]] as const) {
      const stain = new Mesh(new CircleGeometry(1, 24), oilMaterial)
      stain.rotation.x = -Math.PI / 2
      stain.position.set(x, FLOOR_Y + 0.007, z)
      stain.scale.set(sx, sz, 1)
      details.add(stain)
    }
    const platformMaterial = new MeshStandardMaterial({ color: 0x3f4b4a, roughness: 0.82, metalness: 0.12 })
    for (const [x, y, z, sx, sy, sz] of [[-2.05, 0.055, 1.25, 0.45, 0.11, 0.32], [1.95, 0.035, -1.45, 0.38, 0.07, 0.28]] as const) {
      const platform = new Mesh(new BoxGeometry(sx, sy, sz), platformMaterial)
      platform.position.set(x, y, z)
      platform.castShadow = true
      platform.receiveShadow = true
      details.add(platform)
    }
    const crateMaterial = new MeshStandardMaterial({ color: 0x76553d, roughness: 0.88 })
    for (const [x, z, rotation] of [[-2.25, -1.6, 0.12], [2.25, 1.35, -0.2], [1.6, 1.8, 0.08]] as const) {
      const crate = new Mesh(new BoxGeometry(0.28, 0.2, 0.24), crateMaterial)
      crate.position.set(x, 0.1, z)
      crate.rotation.y = rotation
      crate.castShadow = true
      details.add(crate)
    }
    const barrelMaterial = new MeshStandardMaterial({ color: 0x3e4647, metalness: 0.58, roughness: 0.58 })
    for (const [x, z] of [[-2.35, -1.2], [2.35, -0.7], [-1.85, 1.7]] as const) {
      const barrel = new Mesh(new CylinderGeometry(0.1, 0.1, 0.28, 12), barrelMaterial)
      barrel.position.set(x, 0.14, z)
      barrel.rotation.z = 0.04
      barrel.castShadow = true
      details.add(barrel)
    }
    const bagMaterial = new MeshStandardMaterial({ color: 0x15191b, roughness: 0.96 })
    for (const [x, z, sx] of [[-2.1, -1.35, 1.2], [2.15, -0.95, 0.9], [1.9, 1.55, 1.1]] as const) {
      const bag = new Mesh(new SphereGeometry(0.13, 10, 7), bagMaterial)
      bag.position.set(x, 0.1, z)
      bag.scale.set(sx, 0.8, 0.75)
      bag.castShadow = true
      details.add(bag)
    }
    this.group.add(details)
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
