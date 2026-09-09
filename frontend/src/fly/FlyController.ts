import type { ActuatorCommand, FlyMode, SensorFrame } from '../networking/protocol'
import { BrainSocket } from '../networking/BrainSocket'
import { neutralActuators } from './FlyActuators'

export interface ControllerInput {
  frame: SensorFrame
  dt: number
}

export interface FlyController {
  readonly mode: FlyMode
  update(input: ControllerInput): ActuatorCommand
}

export class KeyboardState {
  private readonly pressed = new Set<string>()

  constructor(target: Window = window) {
    target.addEventListener('keydown', (event) => {
      this.pressed.add(event.code)
      if (['ShiftLeft', 'ShiftRight', 'ControlLeft', 'ControlRight', 'Space'].includes(event.code)) event.preventDefault()
    })
    target.addEventListener('keyup', (event) => this.pressed.delete(event.code))
    target.addEventListener('blur', () => this.pressed.clear())
  }

  isDown(...codes: string[]) {
    return codes.some((code) => this.pressed.has(code))
  }
}

export class ManualController implements FlyController {
  readonly mode = 'manual' as const

  constructor(
    private readonly keyboard: KeyboardState,
    private readonly enabled: () => boolean = () => true,
  ) {}

  update(): ActuatorCommand {
    if (!this.enabled()) return neutralActuators()
    const pitchTorque = (this.keyboard.isDown('KeyS') ? 1 : 0) - (this.keyboard.isDown('KeyW') ? 1 : 0)
    const yawTorque = (this.keyboard.isDown('KeyD') ? 1 : 0) - (this.keyboard.isDown('KeyA') ? 1 : 0)
    const rollTorque = (this.keyboard.isDown('KeyE') ? 1 : 0) - (this.keyboard.isDown('KeyQ') ? 1 : 0)
    const shift = this.keyboard.isDown('ShiftLeft', 'ShiftRight')
    const control = this.keyboard.isDown('ControlLeft', 'ControlRight')
    return {
      forwardThrust: clamp01((shift ? 0.7 : 0) - (control ? 0.22 : 0)),
      verticalThrust: clamp01(0.5 + (shift ? 0.12 : 0) - (control ? 0.48 : 0)),
      yawTorque,
      pitchTorque,
      rollTorque,
    }
  }
}

export class MaleCNSController implements FlyController {
  readonly mode = 'malecns' as const
  private elapsed = 0
  private readonly initialDelaySeconds: number

  constructor(
    private readonly socket: BrainSocket,
    private readonly flyId: string,
    private readonly brainUpdateHz = 20,
    initialDelaySeconds = 0,
  ) {
    this.initialDelaySeconds = Math.max(0, initialDelaySeconds)
  }

  update(input: ControllerInput): ActuatorCommand {
    this.elapsed += input.dt
    if (this.elapsed < this.initialDelaySeconds) return this.socket.commandsFor(this.flyId)
    if (this.elapsed >= 1 / this.brainUpdateHz) {
      this.elapsed = 0
      // The MaleCNS encoder consumes the eye summaries and odor values. Do
      // not send the 20 ray samples for every pilot agent on every update;
      // the full frame remains available to the selected debug view.
      this.socket.send({ type: 'brain_input', flyId: this.flyId, mode: this.mode, sensors: compactSensorFrame(input.frame) })
    }
    return this.socket.commandsFor(this.flyId)
  }
}

/**
 * A deliberately separate, non-neural flight benchmark.
 *
 * The current bounded MaleCNS path produces real sensory spikes but no
 * sustained wing-amplitude/forward drive. This controller keeps the browser
 * demonstrable without relabelling a hand-authored flight policy as emergent
 * MaleCNS behaviour. It uses only local embodied observations (eye
 * asymmetry, antenna asymmetry, optic flow and contact), and it writes through
 * the exact same FlyActuators -> FlyBody boundary as the neural controller.
 *
 * Brain frames are still sent for telemetry, so the causal panel can show the
 * real CNS activity alongside the explicitly labelled preview drive.
 */
export class SensoryFlightPreviewController implements FlyController {
  readonly mode = 'preview' as const
  private elapsed = 0
  private timeSeconds = 0
  private smoothedYaw = 0
  private wallTurnSign: -1 | 1 = 1
  private wallTurnRemaining = 0
  private readonly phase: number

  constructor(
    private readonly socket: BrainSocket,
    private readonly flyId: string,
    private readonly brainUpdateHz = 2,
    phaseSeed = 0,
  ) {
    this.phase = hashFlyId(flyId) * 0.00017 + phaseSeed
  }

  update(input: ControllerInput): ActuatorCommand {
    this.elapsed += input.dt
    this.timeSeconds += input.dt
    if (this.elapsed >= 1 / this.brainUpdateHz) {
      this.elapsed %= 1 / this.brainUpdateHz
      this.socket.send({ type: 'brain_input', flyId: this.flyId, mode: this.mode, sensors: compactSensorFrame(input.frame) })
    }

    const frame = input.frame
    const leftObstacle = obstaclePressure(frame.leftEye.samples)
    const rightObstacle = obstaclePressure(frame.rightEye.samples)
    const visualTurn = frame.rightEye.meanContrast - frame.leftEye.meanContrast
    const odorTurn = frame.odor.rightAntenna - frame.odor.leftAntenna
    // A stronger obstruction on the left should turn the body right, hence
    // left-minus-right here. The other two terms use the same positive-right
    // convention: stronger right-eye/antenna input turns right.
    const localTurn = visualTurn * 0.75 + odorTurn * 3.0 + (leftObstacle - rightObstacle) * 1.4

    this.wallTurnRemaining = Math.max(0, this.wallTurnRemaining - input.dt)
    if (frame.contact.wall && this.wallTurnRemaining <= 0) {
      const obstacleSide = Math.sign(leftObstacle - rightObstacle)
      const visualSide = Math.sign(visualTurn || odorTurn || Math.sin(this.phase) || 1)
      // If the wall is visible more strongly on the left, turn right. When a
      // wall is directly ahead and there is no lateral cue, use a stable
      // deterministic turn direction for this agent.
      this.wallTurnSign = obstacleSide > 0 ? 1 : obstacleSide < 0 ? -1 : visualSide >= 0 ? 1 : -1
      this.wallTurnRemaining = 1.8
    }
    const explorationTurn = Math.sin(this.phase + this.timeSeconds * 0.25) * 0.08
    const desiredYaw = this.wallTurnRemaining > 0
      ? this.wallTurnSign * 0.48
      : clamp(localTurn + explorationTurn, -0.34, 0.34)
    this.smoothedYaw += (desiredYaw - this.smoothedYaw) * (1 - Math.exp(-4.5 * input.dt))

    // Forward drive is a preview benchmark, not a decoded MaleCNS output.
    // Optic-flow braking keeps the path from accelerating indefinitely while
    // contact causes a short throttle reduction before the turn completes.
    const flowBrake = Math.min(0.22, frame.leftEye.meanOpticFlow * 0.34 + frame.rightEye.meanOpticFlow * 0.34)
    const forwardThrust = clamp01(0.78 - flowBrake - (frame.contact.wall ? 0.24 : 0))
    const verticalThrust = frame.contact.ground ? 0.62 : 0.55
    return {
      forwardThrust,
      verticalThrust,
      yawTorque: this.smoothedYaw,
      pitchTorque: 0,
      rollTorque: 0,
    }
  }
}

export class SwitchableController implements FlyController {
  private active: FlyController

  constructor(
    private readonly manual: ManualController,
    private readonly malecns: MaleCNSController,
    private readonly preview: SensoryFlightPreviewController,
  ) {
    this.active = preview
  }

  get mode() {
    return this.active.mode
  }

  toggleMode() {
    this.active = this.active.mode === 'preview'
      ? this.malecns
      : this.active.mode === 'malecns'
        ? this.manual
        : this.preview
  }

  setMode(mode: 'manual' | 'malecns' | 'preview') {
    this.active = mode === 'manual' ? this.manual : mode === 'malecns' ? this.malecns : this.preview
  }

  update(input: ControllerInput) {
    return this.active.update(input)
  }
}

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value))
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function compactSensorFrame(frame: ControllerInput['frame']): ControllerInput['frame'] {
  return {
    ...frame,
    leftEye: { ...frame.leftEye, samples: [] },
    rightEye: { ...frame.rightEye, samples: [] },
  }
}

function obstaclePressure(samples: ControllerInput['frame']['leftEye']['samples']) {
  return samples.reduce((pressure, sample) => {
    const weight = Math.min(1, sample.objectAngularSizeRad * 5) * (0.25 + sample.contrast)
    return pressure + (sample.azimuthRad < 0 ? weight : -weight)
  }, 0)
}

function hashFlyId(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return Math.abs(hash >>> 0)
}
