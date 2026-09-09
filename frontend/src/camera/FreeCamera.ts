import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { PerspectiveCamera, Vector3 } from 'three'

export class FreeCamera {
  readonly camera = new PerspectiveCamera(54, 1, 0.001, 100)
  readonly controls: OrbitControls
  private readonly focusOffset = new Vector3()

  constructor(domElement: HTMLElement) {
    // Frame the two flies closely enough to be identifiable while retaining
    // enough room context for orbit/pan/zoom exploration.
    this.camera.position.set(0.98, 0.82, 1.12)
    this.controls = new OrbitControls(this.camera, domElement)
    this.controls.target.set(0, 0.38, 0)
    this.controls.enableDamping = true
    this.controls.enablePan = true
    this.controls.screenSpacePanning = true
    this.controls.zoomToCursor = true
    this.controls.minDistance = 0.005
    this.controls.maxDistance = 4
  }

  focusOn(position: Vector3) {
    // Preserve the current orbit direction and distance while moving the
    // orbit pivot, then move into an inspection distance. A real fly is only
    // millimetres long, so keeping the room-scale distance would make a
    // successful focus appear not to work.
    this.focusOffset.copy(this.camera.position).sub(this.controls.target)
    if (this.focusOffset.lengthSq() < this.controls.minDistance ** 2) {
      this.focusOffset.set(0.12, 0.06, 0.12)
    }
    this.focusOffset.setLength(Math.max(this.controls.minDistance * 5, Math.min(this.focusOffset.length(), 0.14)))
    this.controls.target.copy(position)
    this.camera.position.copy(position).add(this.focusOffset)
    this.controls.update()
  }

  update() {
    this.controls.update()
  }
}
