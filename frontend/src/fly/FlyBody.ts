import { Euler, Quaternion, Vector3 } from 'three'
import type { ActuatorCommand } from '../networking/protocol'

export interface WorldBounds {
  min: Vector3
  max: Vector3
}

export interface BodyContact {
  ground: boolean
  obstacle: boolean
  wall: boolean
}

export class FlyBody {
  readonly position = new Vector3(0, 0.48, 0)
  readonly velocity = new Vector3()
  readonly quaternion = new Quaternion()
  readonly angularVelocity = new Vector3()
  readonly contact: BodyContact = { ground: false, obstacle: false, wall: false }

  readonly massKg = 0.001
  readonly inertia = new Vector3(0.0000012, 0.0000015, 0.0000011)
  readonly maxForwardForceN = 0.00055
  readonly maxVerticalForceN = 0.000018
  readonly gravityN = 0.00000981
  readonly maxTorqueNm = 0.000001
  readonly linearDrag = 0.0032
  readonly angularDrag = 3.8
  // Approximate adult-fly collision radius in metres; the rendered mesh uses
  // the same physical scale rather than an arbitrary room-sized avatar.
  readonly collisionRadius = 0.0025
  private readonly forward = new Vector3()
  private readonly up = new Vector3()
  private readonly force = new Vector3()
  private readonly localTorque = new Vector3()
  private readonly angularAcceleration = new Vector3()
  private readonly rotationAxis = new Vector3()
  private readonly rotationDelta = new Quaternion()

  step(dt: number, command: ActuatorCommand, bounds: WorldBounds) {
    const forward = this.forward.set(0, 0, -1).applyQuaternion(this.quaternion).normalize()
    const up = this.up.set(0, 1, 0).applyQuaternion(this.quaternion).normalize()
    const force = this.force.copy(forward).multiplyScalar(command.forwardThrust * this.maxForwardForceN)
    force.addScaledVector(up, command.verticalThrust * this.maxVerticalForceN)
    force.y -= this.gravityN
    this.removeOutwardBoundaryForce(force, bounds)
    force.addScaledVector(this.velocity, -this.linearDrag)
    this.velocity.addScaledVector(force, dt / this.massKg)
    this.velocity.multiplyScalar(Math.exp(-this.linearDrag * 2 * dt))
    this.position.addScaledVector(this.velocity, dt)

    const localTorque = this.localTorque.set(command.pitchTorque, command.yawTorque, command.rollTorque)
    const angularAcceleration = this.angularAcceleration.set(
      (localTorque.x * this.maxTorqueNm) / this.inertia.x,
      (localTorque.y * this.maxTorqueNm) / this.inertia.y,
      (localTorque.z * this.maxTorqueNm) / this.inertia.z,
    )
    this.angularVelocity.addScaledVector(angularAcceleration, dt)
    this.angularVelocity.multiplyScalar(Math.exp(-this.angularDrag * dt))
    const angle = this.angularVelocity.length() * dt
    if (angle > 0.0000001) {
      const delta = this.rotationDelta.setFromAxisAngle(this.rotationAxis.copy(this.angularVelocity).normalize(), angle)
      this.quaternion.multiply(delta).normalize()
    }
    this.resolveBounds(bounds)
  }

  private resolveBounds(bounds: WorldBounds) {
    this.contact.ground = false
    this.contact.obstacle = false
    this.contact.wall = false
    const minY = bounds.min.y + this.collisionRadius
    const maxY = bounds.max.y - this.collisionRadius
    if (this.position.x < bounds.min.x + this.collisionRadius) {
      this.contact.wall = true
      this.position.x = bounds.min.x + this.collisionRadius
      // Remove only the outward component. Reflecting it caused a repeated
      // bounce/thrust loop when the controller continued to command forward.
      if (this.velocity.x < 0) this.velocity.x = 0
    } else if (this.position.x > bounds.max.x - this.collisionRadius) {
      this.contact.wall = true
      this.position.x = bounds.max.x - this.collisionRadius
      if (this.velocity.x > 0) this.velocity.x = 0
    }
    if (this.position.z < bounds.min.z + this.collisionRadius) {
      this.contact.wall = true
      this.position.z = bounds.min.z + this.collisionRadius
      if (this.velocity.z < 0) this.velocity.z = 0
    } else if (this.position.z > bounds.max.z - this.collisionRadius) {
      this.contact.wall = true
      this.position.z = bounds.max.z - this.collisionRadius
      if (this.velocity.z > 0) this.velocity.z = 0
    }
    if (this.position.y < minY) {
      this.contact.ground = true
      this.position.y = minY
      this.velocity.y = Math.max(0, this.velocity.y) * 0.1
    } else if (this.position.y > maxY) {
      this.position.y = maxY
      this.velocity.y = -Math.abs(this.velocity.y) * 0.25
    }
  }

  private removeOutwardBoundaryForce(force: Vector3, bounds: WorldBounds) {
    const margin = this.collisionRadius + 0.001
    if (this.position.x <= bounds.min.x + margin && force.x < 0) force.x = 0
    if (this.position.x >= bounds.max.x - margin && force.x > 0) force.x = 0
    if (this.position.z <= bounds.min.z + margin && force.z < 0) force.z = 0
    if (this.position.z >= bounds.max.z - margin && force.z > 0) force.z = 0
  }

  getEuler() {
    return new Euler().setFromQuaternion(this.quaternion, 'YXZ')
  }
}
