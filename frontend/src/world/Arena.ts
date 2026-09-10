import { CanvasTexture, Group, Mesh, MeshStandardMaterial, PlaneGeometry, RepeatWrapping, SRGBColorSpace, Vector3 } from 'three'
import type { WorldBounds } from '../fly/FlyBody'

const FLOOR_Y = 0
export const PRESENTATION_SCENE_HALF_EXTENT = 3

export const ARENA_BOUNDS: WorldBounds = {
  // The authored city and the manual game-scene editor both use the full
  // presentation floor. Keep the simulation and visible map in the same
  // coordinate system so a drawn region is actually reachable by flies.
  min: new Vector3(-PRESENTATION_SCENE_HALF_EXTENT, 0, -PRESENTATION_SCENE_HALF_EXTENT),
  max: new Vector3(PRESENTATION_SCENE_HALF_EXTENT, 1, PRESENTATION_SCENE_HALF_EXTENT),
}

// This is the complete play surface: the star field is the background and the
// floor, habitats, and flies are the only world geometry.
export class Arena {
  readonly group = new Group()
  readonly bounds = ARENA_BOUNDS

  constructor() {
    this.group.name = 'Arena'
    const floorTexture = createFloorTexture()
    const floor = new Mesh(
      // The floor covers the same 6m x 6m presentation volume as the default
      // physics bounds, so the manual game-scene editor has no hidden area.
      new PlaneGeometry(6.2, 6.2),
      new MeshStandardMaterial({ color: 0x354943, map: floorTexture, roughness: 0.72, metalness: 0.18 }),
    )
    floor.rotation.x = -Math.PI / 2
    // Keep the visual floor exactly on the same Y plane used by habitats and
    // body ground contact.
    floor.position.y = FLOOR_Y
    floor.name = 'StreetFloor'
    this.group.add(floor)
  }

  /** Kept for compatibility with older callers; the floor is always visible. */
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
    const noise = 34 + Math.floor(((seed >>> 8) & 0xffff) / 65536 * 30)
    image.data[index] = noise
    image.data[index + 1] = noise + 13
    image.data[index + 2] = noise + 11
    image.data[index + 3] = 255
  }
  context.putImageData(image, 0, 0)
  // Subtle wet-road seams and oil patches give the plain floor depth without
  // reintroducing buildings, props, or another competing play surface.
  context.lineWidth = 1
  context.strokeStyle = 'rgba(133, 218, 202, 0.12)'
  for (let position = 16; position < 128; position += 32) {
    context.beginPath()
    context.moveTo(position, 0)
    context.lineTo(position + 7, 128)
    context.stroke()
  }
  for (let index = 0; index < 14; index += 1) {
    seed = (seed * 1664525 + 1013904223) >>> 0
    const x = ((seed >>> 8) & 0xffff) / 65536 * 128
    seed = (seed * 1664525 + 1013904223) >>> 0
    const y = ((seed >>> 8) & 0xffff) / 65536 * 128
    const radius = 4 + ((seed >>> 16) & 0xff) / 255 * 13
    const patch = context.createRadialGradient(x, y, 0, x, y, radius)
    patch.addColorStop(0, 'rgba(8, 20, 23, 0.28)')
    patch.addColorStop(0.72, 'rgba(8, 20, 23, 0.08)')
    patch.addColorStop(1, 'rgba(8, 20, 23, 0)')
    context.fillStyle = patch
    context.beginPath()
    context.ellipse(x, y, radius * 1.4, radius * 0.62, 0.2, 0, Math.PI * 2)
    context.fill()
  }
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  texture.wrapS = RepeatWrapping
  texture.wrapT = RepeatWrapping
  texture.repeat.set(9, 9)
  return texture
}
