import { Box3, Group, Vector3 } from 'three'
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js'

const LOCAL_ASSETS = {
  trashCan: '/models/polyhaven/metal_trash_can/metal_trash_can.gltf',
  cardboardBox: '/models/polyhaven/cardboard_box_01/cardboard_box.gltf',
} as const

export class PropLibrary {
  private readonly loader = new GLTFLoader()
  private readonly cache = new Map<string, Promise<Group>>()

  load(name: keyof typeof LOCAL_ASSETS) {
    const existing = this.cache.get(name)
    if (existing) return existing
    const request = this.loader.loadAsync(LOCAL_ASSETS[name]).then((gltf) => gltf.scene)
    this.cache.set(name, request)
    return request
  }

  async place(name: keyof typeof LOCAL_ASSETS, position: Vector3, heightM: number) {
    const source = await this.load(name)
    const object = source.clone(true)
    const bounds = new Box3().setFromObject(object)
    const size = bounds.getSize(new Vector3())
    if (size.y > 0) object.scale.setScalar(heightM / size.y)
    object.updateMatrixWorld(true)
    const scaledBounds = new Box3().setFromObject(object)
    object.position.set(position.x, -scaledBounds.min.y, position.z)
    object.userData.assetSource = `Poly Haven CC0 · ${name}`
    return object
  }
}
