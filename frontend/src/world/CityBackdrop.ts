import { Box3, Group, Mesh, MeshStandardMaterial, Vector3 } from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'

/** Loads the supplied street-city scene and fits it around the market floor. */
export class CityBackdrop {
  readonly group = new Group()
  readonly ready: Promise<void>

  constructor() {
    this.group.name = 'StreetCityBackdrop'
    this.ready = new Promise((resolve, reject) => {
      new GLTFLoader().load('/models/city/street_city.glb', (gltf) => {
        const city = gltf.scene
        const sourceBounds = new Box3().setFromObject(city)
        const sourceSize = sourceBounds.getSize(new Vector3())
        const scale = Math.min(
          sourceSize.x > 0 ? 5.4 / sourceSize.x : 1,
          sourceSize.z > 0 ? 5.4 / sourceSize.z : 1,
          sourceSize.y > 0 ? 3.4 / sourceSize.y : 1,
        )
        city.scale.setScalar(scale)
        const fittedBounds = new Box3().setFromObject(city)
        const center = fittedBounds.getCenter(new Vector3())
        city.position.x -= center.x
        city.position.z -= center.z
        city.position.y -= fittedBounds.min.y
        city.traverse((object) => {
          const mesh = object as Mesh
          if (!mesh.isMesh) return
          mesh.castShadow = false
          mesh.receiveShadow = true
          mesh.frustumCulled = true
          // The supplied asset is daytime-lit. Preserve its textures, but
          // grade the geometry into the same cool night palette as the sky so
          // habitats remain the visual focus on the street floor.
          const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
          materials.forEach((material) => {
            const standard = material as MeshStandardMaterial
            standard.color?.multiplyScalar(0.56)
            if (standard.emissive) {
              standard.emissive.multiplyScalar(0.32)
              standard.emissiveIntensity = Math.min(0.5, standard.emissiveIntensity || 0.08)
            }
          })
        })
        this.group.add(city)
        resolve()
      }, undefined, (error) => {
        console.warn('Street city asset unavailable; using procedural arena details', error)
        resolve()
      })
    })
  }
}
