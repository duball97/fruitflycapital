import { PerspectiveCamera, Vector3 } from 'three'
import { FlyAgent } from '../fly/FlyAgent'

export class FollowCamera {
  readonly camera = new PerspectiveCamera(58, 1, 0.001, 100)
  private readonly desired = new Vector3()
  private readonly target = new Vector3()

  constructor() {
    this.camera.position.set(0, 0.52, 0.08)
  }

  update(agent: FlyAgent) {
    const forward = new Vector3(0, 0, -1).applyQuaternion(agent.body.quaternion).normalize()
    const up = new Vector3(0, 1, 0).applyQuaternion(agent.body.quaternion).normalize()
    this.desired.copy(agent.body.position).addScaledVector(forward, -0.055).addScaledVector(up, 0.022)
    this.target.copy(agent.body.position).addScaledVector(forward, 0.006)
    this.camera.position.lerp(this.desired, 0.12)
    this.camera.lookAt(this.target)
  }
}
