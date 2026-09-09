import { PerspectiveCamera, Vector3 } from 'three'
import type { FlyAgent } from '../fly/FlyAgent'
import type { TokenHabitat } from '../world/TokenHabitat'

export type PresentationCameraMode = 'overview' | 'token' | 'director'

export class PresentationCamera {
  readonly camera = new PerspectiveCamera(52, 1, 0.001, 100)
  private mode: PresentationCameraMode = 'overview'
  private readonly desired = new Vector3()
  private readonly target = new Vector3()
  private readonly center = new Vector3()
  private readonly overviewDirection = new Vector3(0.58, 0.42, 0.7).normalize()

  constructor() {
    this.camera.position.set(1.45, 1.08, 1.5)
  }

  setMode(mode: PresentationCameraMode) {
    this.mode = mode
  }

  get currentMode() {
    return this.mode
  }

  update(timeSeconds: number, agents: FlyAgent[], habitats: TokenHabitat[], selectedIndex: number) {
    const selected = agents[selectedIndex]
    if (this.mode === 'token' && habitats.length > 0) {
      const habitat = habitats[Math.floor(timeSeconds / 8) % habitats.length]!
      this.target.copy(habitat.group.position).add(new Vector3(0, 0.045, 0))
      this.desired.copy(this.target).add(new Vector3(0.28, 0.18, 0.3))
    } else if (this.mode === 'director' && selected) {
      const phase = timeSeconds % 18
      if (phase < 7) {
        this.center.set(0, 0, 0)
        agents.forEach((agent) => this.center.add(agent.body.position))
        this.center.multiplyScalar(1 / Math.max(1, agents.length))
        this.target.copy(this.center)
        this.desired.copy(this.center).add(new Vector3(0.72, 0.42, 0.88))
      } else if (phase < 13 && habitats.length > 0) {
        const habitat = habitats[Math.floor((timeSeconds - 7) / 6) % habitats.length]!
        this.target.copy(habitat.group.position).add(new Vector3(0, 0.045, 0))
        this.desired.copy(this.target).add(new Vector3(0.24, 0.14, 0.22))
      } else {
        this.target.copy(selected.body.position)
        this.desired.copy(this.target).add(new Vector3(0.18, 0.08, 0.18))
      }
    } else {
      const swarmRadius = this.setSwarmCenter(agents)
      this.target.copy(this.center)
      // Keep the entire population in frame as agents spread through the
      // room. The overview is a camera fit, not a second simulation rule.
      const verticalFov = this.camera.fov * Math.PI / 180
      const fitDistance = swarmRadius / Math.tan(verticalFov / 2) * 1.35
      this.desired.copy(this.center).addScaledVector(this.overviewDirection, Math.max(0.95, Math.min(4, fitDistance)))
    }
    this.camera.position.lerp(this.desired, 0.06)
    this.camera.lookAt(this.target)
  }

  private setSwarmCenter(agents: FlyAgent[]) {
    this.center.set(0, 0, 0)
    agents.forEach((agent) => this.center.add(agent.body.position))
    this.center.multiplyScalar(1 / Math.max(1, agents.length))
    return Math.max(0.12, ...agents.map((agent) => agent.body.position.distanceTo(this.center)))
  }
}
