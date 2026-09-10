import { Euler, Quaternion, Vector3 } from 'three'
import type { ActuatorCommand } from '../networking/protocol'
import { FlyAgent } from './FlyAgent'
import { FlyRenderer } from '../rendering/FlyRenderer'

/**
 * A render-only body attached to one real CNS agent.
 *
 * The primary FlyAgent remains the only body that senses, runs a controller,
 * owns a brain runtime, and contributes to swarm statistics. Followers share
 * that agent's actuator intent for presentation, with deterministic formation
 * spacing, lag, orientation, speed, and wingbeat differences so the enlarged
 * presentation bodies remain visibly distinct without changing the
 * underlying agent or trading behavior.
 */
export class VisualFlyFollower {
  readonly renderer: FlyRenderer
  private readonly position = new Vector3()
  private readonly quaternion = new Quaternion()
  private readonly targetPosition = new Vector3()
  private readonly targetQuaternion = new Quaternion()
  private readonly localOffset: Vector3
  private readonly drift = new Vector3()
  private readonly rotatedOffset = new Vector3()
  private readonly orientationOffset: Quaternion
  private readonly visualCommand: ActuatorCommand = {
    forwardThrust: 0,
    verticalThrust: 0.5,
    yawTorque: 0,
    pitchTorque: 0,
    rollTorque: 0,
  }
  private readonly phase: number
  private readonly speedScale: number
  private initialized = false

  constructor(
    readonly primary: FlyAgent,
    slot: number,
    cohortIndex: number,
  ) {
    this.phase = cohortIndex * 1.73 + slot * 2.41
    this.speedScale = 0.95 + ((cohortIndex * 7 + slot * 11) % 11) / 100
    this.renderer = new FlyRenderer((this.phase / (Math.PI * 2)) % 1)

    // The renderer magnifies the millimetre-scale fly mesh by 12x. The old
    // centimetre-scale offsets therefore put several silhouettes through one
    // another. Fan the render-only bodies into a broad diamond around their
    // primary instead of letting them occupy nearly the same screen-space
    // footprint. The spacing is visual only; it does not change the primary's
    // physics, sensing, or trading decisions.
    const layouts = [
      [-0.11, 0.024, 0.075],
      [0.11, 0.030, 0.065],
      [-0.12, -0.018, -0.085],
      [0.12, -0.012, -0.095],
    ] as const
    const layout = layouts[slot % layouts.length]!
    this.localOffset = new Vector3(layout[0], layout[1], layout[2])
    this.orientationOffset = new Quaternion().setFromEuler(new Euler(
      Math.sin(this.phase) * 0.035,
      Math.cos(this.phase * 0.7) * 0.075,
      Math.sin(this.phase * 0.43) * 0.05,
      'YXZ',
    ))
  }

  update(dtSeconds: number, elapsedSeconds: number) {
    const body = this.primary.body
    const driftScale = 0.0025
    this.drift.set(
      Math.sin(elapsedSeconds * 1.7 + this.phase) * driftScale,
      Math.sin(elapsedSeconds * 1.25 + this.phase * 0.7) * driftScale * 0.7,
      Math.cos(elapsedSeconds * 1.45 + this.phase * 0.9) * driftScale,
    )
    this.rotatedOffset.copy(this.localOffset).add(this.drift).applyQuaternion(body.quaternion)
    this.targetPosition.copy(body.position).add(this.rotatedOffset)
    this.targetQuaternion.copy(body.quaternion).multiply(this.orientationOffset)

    if (!this.initialized) {
      this.position.copy(this.targetPosition)
      this.quaternion.copy(this.targetQuaternion)
      this.initialized = true
    } else {
      const followAlpha = 1 - Math.exp(-9 * Math.min(0.1, Math.max(0, dtSeconds)))
      this.position.lerp(this.targetPosition, followAlpha)
      this.quaternion.slerp(this.targetQuaternion, followAlpha)
    }

    const command = this.primary.actuators.get()
    this.visualCommand.forwardThrust = Math.min(1, command.forwardThrust * this.speedScale)
    this.visualCommand.verticalThrust = clamp01(0.5 + (command.verticalThrust - 0.5) * this.speedScale)
    this.visualCommand.yawTorque = command.yawTorque * 0.92
    this.visualCommand.pitchTorque = command.pitchTorque * 0.92
    this.visualCommand.rollTorque = command.rollTorque * 0.92
    this.renderer.updatePose(this.position, this.quaternion, this.visualCommand, elapsedSeconds)
  }
}

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}
