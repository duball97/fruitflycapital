import { FlyActuators } from './FlyActuators'
import { FlyBody } from './FlyBody'
import type { FlyController } from './FlyController'
import { FlySensors, type OdorSampler } from './FlySensors'
import type { ActuatorCommand, SensorFrame } from '../networking/protocol'
import type { Vector3 } from 'three'

export type LandingState = 'cruise' | 'descending' | 'landed' | 'departing'
export type HabitatContactSampler = (position: Vector3) => boolean

const LANDING_ODOR_ONSET = 0.055
const LANDING_ODOR_RELEASE = 0.025
const DWELL_SECONDS = 2.2

export class FlyAgent {
  readonly body = new FlyBody()
  readonly sensors = new FlySensors()
  readonly actuators = new FlyActuators()
  /** The command returned by the CNS before the local landing layer acts. */
  lastNeuralCommand: ActuatorCommand = neutralCommand()
  /** The command actually applied to the body after landing mechanics. */
  lastMotorCommand: ActuatorCommand = neutralCommand()
  landingState: LandingState = 'cruise'
  habitatContact = false
  // One hundred agents at 20 Hz would perform 40,000 eye raycasts per
  // second. Ten Hz is still faster than the default brain transport cadence
  // and keeps the fixed 120 Hz body integration independent of perception.
  private readonly sensorInterval = 1 / 10
  private sensorAccumulator = this.sensorInterval

  constructor(
    readonly id: string,
    private readonly controller: FlyController,
    spawnPosition?: Vector3,
  ) {
    if (spawnPosition) this.body.position.copy(spawnPosition)
  }

  get mode() {
    return this.controller.mode
  }

  updateFixed(
    dt: number,
    bounds: Parameters<FlyBody['step']>[2],
    visualRoot: Parameters<FlySensors['update']>[1],
    odorSampler: OdorSampler,
    timeSeconds: number,
    habitatContactSampler: HabitatContactSampler = () => false,
  ) {
    this.sensorAccumulator += dt
    if (this.sensorAccumulator >= this.sensorInterval) {
      this.sensorAccumulator %= this.sensorInterval
      this.sensors.update(this.body, visualRoot, odorSampler, timeSeconds)
    }
    const frame = this.sensors.toFrame(this.body)
    const neuralCommand = this.controller.update({ frame, dt })
    this.lastNeuralCommand = { ...neuralCommand }
    const command = this.applyLandingMechanics(neuralCommand, frame, dt)
    this.lastMotorCommand = { ...command }
    this.actuators.set(command)
    this.body.step(dt, this.actuators.get(), bounds)
    this.habitatContact = habitatContactSampler(this.body.position)
    this.updateLandingStateAfterStep(dt)
  }

  private applyLandingMechanics(command: ActuatorCommand, frame: SensorFrame, dt: number) {
    const odor = frame.odor.concentration
    const safeOdor = odor >= frame.odor.aversiveConcentration * 0.9
    if (this.landingState === 'cruise' && odor >= LANDING_ODOR_ONSET && safeOdor) {
      this.landingState = 'descending'
    } else if (this.landingState === 'descending' && odor < LANDING_ODOR_RELEASE && !this.body.contact.ground) {
      this.landingState = 'cruise'
    }

    if (this.landingState === 'descending') {
      // Odor is the only descent trigger. The CNS still owns left/right
      // steering; this layer only supplies a bounded vertical approach and
      // slightly reduces forward speed so the fly can reach the source.
      return {
        ...command,
        forwardThrust: Math.min(command.forwardThrust, 0.62),
        verticalThrust: Math.min(command.verticalThrust, 0.16 + odor * 0.2),
        pitchTorque: command.pitchTorque * 0.72,
        rollTorque: command.rollTorque * 0.82,
      }
    }

    if (this.landingState === 'landed') {
      return {
        ...command,
        forwardThrust: 0,
        verticalThrust: 0.52,
        yawTorque: command.yawTorque * 0.22,
        pitchTorque: 0,
        rollTorque: 0,
      }
    }

    if (this.landingState === 'departing') {
      return {
        ...command,
        forwardThrust: Math.max(0.22, command.forwardThrust),
        verticalThrust: Math.max(0.72, command.verticalThrust),
      }
    }

    // Keep the fixed-step loop responsive if the state changes on this tick.
    void dt
    return command
  }

  private dwellSeconds = 0

  private updateLandingStateAfterStep(dt: number) {
    if (this.landingState === 'descending' && this.body.contact.ground && this.habitatContact) {
      this.landingState = 'landed'
      this.dwellSeconds = 0
    }
    if (this.landingState === 'landed') {
      if (!this.habitatContact || !this.body.contact.ground) {
        this.landingState = 'cruise'
        this.dwellSeconds = 0
        return
      }
      this.dwellSeconds += dt
      if (this.dwellSeconds >= DWELL_SECONDS) {
        this.landingState = 'departing'
        this.dwellSeconds = 0
      }
    }
    if (this.landingState === 'departing' && !this.body.contact.ground && this.body.position.y > 0.06) {
      this.landingState = 'cruise'
    }
  }
}

function neutralCommand(): ActuatorCommand {
  return { forwardThrust: 0, verticalThrust: 0.5, yawTorque: 0, pitchTorque: 0, rollTorque: 0 }
}
