import { Object3D, PerspectiveCamera, Vector3 } from 'three'
import type { FlyAgent } from '../fly/FlyAgent'
import type { TokenHabitat } from '../world/TokenHabitat'

export type PresentationCameraMode = 'overview' | 'token' | 'director'

export class PresentationCamera {
  readonly camera = new PerspectiveCamera(52, 1, 0.001, 100)
  private mode: PresentationCameraMode = 'overview'
  private readonly desired = new Vector3()
  private readonly target = new Vector3()
  private readonly center = new Vector3()
  private readonly orientation = new Object3D()
  private readonly forward = new Vector3()
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
      // Hold each shot long enough to read the behavior log. The director
      // still cuts between three shot types, but transitions are deliberately
      // slow and eased instead of snapping every few seconds.
      const phase = timeSeconds % 36
      if (phase < 14) {
        this.center.set(0, 0, 0)
        agents.forEach((agent) => this.center.add(agent.body.position))
        this.center.multiplyScalar(1 / Math.max(1, agents.length))
        this.target.copy(this.center)
        const wideDistance = 1.45 + (Math.floor(timeSeconds / 36) % 2) * 0.42
        this.desired.copy(this.center).add(new Vector3(0.58, 0.38, 0.72).normalize().multiplyScalar(wideDistance))
      } else if (phase < 24 && habitats.length > 0) {
        const habitat = habitats[Math.floor((timeSeconds - 14) / 10) % habitats.length]!
        this.target.copy(habitat.group.position).add(new Vector3(0, 0.045, 0))
        const mediumDistance = 0.46 + (Math.floor(timeSeconds / 36) % 3) * 0.12
        this.desired.copy(this.target).add(new Vector3(0.72, 0.42, 0.72).normalize().multiplyScalar(mediumDistance))
      } else {
        // The final shot is an occasional fly-eye view: close to the agent,
        // but still slightly above the floor so the subject remains visible.
        this.forward.set(0, 0, -1).applyQuaternion(selected.body.quaternion).normalize()
        this.target.copy(selected.body.position).addScaledVector(this.forward, 0.14).add(new Vector3(0, 0.012, 0))
        this.desired.copy(selected.body.position).addScaledVector(this.forward, -0.025).add(new Vector3(0, 0.025, 0))
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
    this.camera.position.lerp(this.desired, 0.025)
    this.orientation.position.copy(this.camera.position)
    this.orientation.lookAt(this.target)
    this.camera.quaternion.slerp(this.orientation.quaternion, 0.035)
  }

  private setSwarmCenter(agents: FlyAgent[]) {
    this.center.set(0, 0, 0)
    agents.forEach((agent) => this.center.add(agent.body.position))
    this.center.multiplyScalar(1 / Math.max(1, agents.length))
    return Math.max(0.12, ...agents.map((agent) => agent.body.position.distanceTo(this.center)))
  }
}
