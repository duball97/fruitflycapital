import { CanvasTexture, Group, Mesh, MeshStandardMaterial, PlaneGeometry, RepeatWrapping, SRGBColorSpace, Vector3 } from 'three'
import type { WorldBounds } from '../fly/FlyBody'

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
      new PlaneGeometry(2, 2),
      new MeshStandardMaterial({ color: 0x727a74, map: floorTexture, roughness: 0.94, metalness: 0.02 }),
    )
    floor.rotation.x = -Math.PI / 2
    floor.name = 'Floor'
    this.group.add(floor)
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
  texture.repeat.set(3, 3)
  return texture
}
