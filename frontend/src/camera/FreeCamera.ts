import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { PerspectiveCamera, Vector3 } from 'three'

export class FreeCamera {
  readonly camera = new PerspectiveCamera(54, 1, 0.001, 100)
  readonly controls: OrbitControls

  constructor(domElement: HTMLElement) {
    // Frame the two flies closely enough to be identifiable while retaining
    // enough room context for orbit/pan/zoom exploration.
    this.camera.position.set(0.42, 0.66, 1.1)
    this.controls = new OrbitControls(this.camera, domElement)
    this.controls.target.set(0, 0.5, 0.65)
    this.controls.enableDamping = true
    this.controls.enablePan = true
    this.controls.screenSpacePanning = true
    this.controls.zoomToCursor = true
    this.controls.minDistance = 0.005
    this.controls.maxDistance = 5
  }

  update() {
    this.controls.update()
  }
}
