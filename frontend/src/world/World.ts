import { Object3D, Scene } from 'three'
import { FlyAgent } from '../fly/FlyAgent'
import { Environment } from './Environment'

export class World {
  readonly fixedDt = 1 / 120
  readonly environment: Environment
  readonly scene: Scene
  readonly agents: FlyAgent[]
  readonly agent: FlyAgent
  elapsedSeconds = 0
  private accumulator = 0

  constructor(scene: Scene, agents: FlyAgent | FlyAgent[], environment: Environment) {
    this.scene = scene
    this.agents = Array.isArray(agents) ? agents : [agents]
    this.agent = this.agents[0]!
    this.environment = environment
    this.scene.add(this.environment.group)
  }

  add(object: Object3D) {
    this.scene.add(object)
  }

  update(realDeltaSeconds: number) {
    this.accumulator += Math.min(realDeltaSeconds, 0.1)
    let steps = 0
    // Keep the interactive loop real-time. If a tab wakes up or a heavy asset
    // frame stalls rendering, do not run an unbounded backlog of physics steps
    // that makes the next frame even slower.
    while (this.accumulator >= this.fixedDt && steps < 6) {
      this.environment.update(this.elapsedSeconds)
      for (const agent of this.agents) {
        agent.updateFixed(this.fixedDt, this.environment.bounds, this.environment.group, (position, timeSeconds) => this.environment.sampleOdorAt(position, timeSeconds), this.elapsedSeconds)
      }
      this.elapsedSeconds += this.fixedDt
      this.accumulator -= this.fixedDt
      steps += 1
    }
    if (steps === 6) this.accumulator = 0
    return steps
  }
}
