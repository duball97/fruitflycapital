import { FlyActuators } from './FlyActuators'
import { FlyBody } from './FlyBody'
import type { FlyController } from './FlyController'
import { FlySensors, type OdorSampler } from './FlySensors'
import type { Vector3 } from 'three'

export class FlyAgent {
  readonly body = new FlyBody()
  readonly sensors = new FlySensors()
  readonly actuators = new FlyActuators()
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

  updateFixed(dt: number, bounds: Parameters<FlyBody['step']>[2], visualRoot: Parameters<FlySensors['update']>[1], odorSampler: OdorSampler, timeSeconds: number) {
    this.sensorAccumulator += dt
    if (this.sensorAccumulator >= this.sensorInterval) {
      this.sensorAccumulator %= this.sensorInterval
      this.sensors.update(this.body, visualRoot, odorSampler, timeSeconds)
    }
    const command = this.controller.update({ frame: this.sensors.toFrame(this.body), dt })
    this.actuators.set(command)
    this.body.step(dt, this.actuators.get(), bounds)
  }
}
