import { PerspectiveCamera, Vector3 } from 'three'
import { FlyAgent } from '../fly/FlyAgent'

export class FirstPersonCamera {
  readonly camera = new PerspectiveCamera(82, 1, 0.0005, 100)
  private readonly forward = new Vector3()
  private readonly up = new Vector3()

  update(agent: FlyAgent) {
    const forward = this.forward.set(0, 0, -1).applyQuaternion(agent.body.quaternion).normalize()
    const up = this.up.set(0, 1, 0).applyQuaternion(agent.body.quaternion).normalize()
    this.camera.position.copy(agent.body.position).addScaledVector(forward, 0.0025).addScaledVector(up, 0.001)
    this.camera.quaternion.copy(agent.body.quaternion)
  }
}
