import { Box3, Group, Mesh, MeshStandardMaterial, Vector3 } from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'

/**
 * Scene-only placement controls, in world metres/radians. Keep rotation at
 * zero for the supplied street-city asset; adjust these values when tuning
 * the visual alignment without touching the simulation coordinates.
 */
export const CITY_SCENE_TUNING = {
  offsetX: 0,
  offsetY: -0.10,
  offsetZ: 0,
  rotationY: 0,
  scaleMultiplier: 1,
} as const

/** Loads the supplied street-city scene and fits it around the market floor. */
export class CityBackdrop {
  readonly group = new Group()
  readonly ready: Promise<void>
  loaded = false

  constructor() {
    this.group.name = 'StreetCityBackdrop'
    this.ready = new Promise((resolve, reject) => {
      new GLTFLoader().load('/models/city/street_city.glb', (gltf) => {
        const city = gltf.scene
        const sourceBounds = new Box3().setFromObject(city)
        const sourceSize = sourceBounds.getSize(new Vector3())
        // The asset's street/road footprint is the world floor. Fit that
        // footprint to the presentation floor without the old second 0.72x
        // shrink, which left most of the usable city outside the camera.
        const scale = Math.min(
          sourceSize.x > 0 ? 5.65 / sourceSize.x : 1,
          sourceSize.z > 0 ? 5.65 / sourceSize.z : 1,
          sourceSize.y > 0 ? 4.2 / sourceSize.y : 1,
        )
        city.scale.setScalar(scale * CITY_SCENE_TUNING.scaleMultiplier)
        city.rotation.y = CITY_SCENE_TUNING.rotationY
        const fittedBounds = new Box3().setFromObject(city)
        const center = fittedBounds.getCenter(new Vector3())
        city.position.x -= center.x - CITY_SCENE_TUNING.offsetX
        city.position.z -= center.z - CITY_SCENE_TUNING.offsetZ

        // The asset is already Y-up. Normalize its actual rendered lowest
        // point to the shared world ground; rotating this file makes the
        // buildings and streets appear on their sides.
        city.position.y -= fittedBounds.min.y - CITY_SCENE_TUNING.offsetY
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
            standard.color?.multiplyScalar(0.96)
            if (standard.emissive) {
              standard.emissive.multiplyScalar(0.72)
              standard.emissiveIntensity = Math.min(1.05, Math.max(0.16, standard.emissiveIntensity || 0.16))
            }
          })
        })
        this.group.add(city)
        this.loaded = true
        resolve()
      }, undefined, (error) => {
        console.warn('Street city asset unavailable; using procedural arena details', error)
        resolve()
      })
    })
  }
}
