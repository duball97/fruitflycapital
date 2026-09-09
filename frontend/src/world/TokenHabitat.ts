import { CanvasTexture, Color, CylinderGeometry, Group, Mesh, MeshStandardMaterial, Sprite, SpriteMaterial, TorusGeometry, Vector3, Quaternion } from 'three'
import { FlybodyAssetLoader } from '../rendering/FlybodyAsset'
import { WingBeatPatternGenerator } from '../fly/WingBeatPattern'

export interface TokenState {
  id: string
  label: string
  activity: number
  liquidityDepth: number
  flowImbalance: number
  volatility: number
  socialActivity: number
  risk: number
  stableStructure: number
}

export interface HabitatProperties {
  physicalRadiusM: number
  resourcePileRadiusM: number
  visualMotionIntensity: number
  brightness: number
  particleActivity: number
  chaos: number
  attractiveOdor: number
  aversiveDanger: number
}

export type HabitatScenario = 'off' | 'different' | 'swapped' | 'live'

const NEUTRAL_PROPERTIES: HabitatProperties = {
  physicalRadiusM: 0.1,
  resourcePileRadiusM: 0.06,
  visualMotionIntensity: 0,
  brightness: 0.16,
  particleActivity: 0,
  chaos: 0,
  attractiveOdor: 0,
  aversiveDanger: 0,
}

// Shared distant launch area for the visual swarm. It is a world-space
// initial condition; the swarm still responds to each habitat's synthetic
// sensory parameters after launch.
const SWARM_START_WORLD = new Vector3(0, 0.64, 0.94)

export class TokenHabitat {
  readonly group = new Group()
  readonly state: TokenState
  readonly basePosition = new Vector3()
  properties: HabitatProperties = { ...NEUTRAL_PROPERTIES }
  private readonly ring: Mesh
  private readonly pile: Mesh
  private readonly light: Mesh
  private readonly swarm: SwarmFlyVisual[] = []
  readonly swarmReady: Promise<void>
  private readonly label: Sprite
  private enabled = true
  private readonly wingAxisX = new Vector3(1, 0, 0)
  private readonly wingAxisY = new Vector3(0, 1, 0)
  private readonly wingAxisZ = new Vector3(0, 0, 1)
  private readonly wingRotation = new Quaternion()

  constructor(state: TokenState, position: Vector3, color: number) {
    this.state = state
    this.basePosition.copy(position)
    this.group.name = `TokenHabitat:${state.id}`
    this.group.position.copy(position)

    const ringMaterial = new MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.18, transparent: true, opacity: 0.72, roughness: 0.48 })
    this.ring = new Mesh(new TorusGeometry(0.12, 0.008, 8, 36), ringMaterial)
    this.ring.rotation.x = Math.PI / 2
    this.ring.position.y = 0.006
    this.group.add(this.ring)

    this.pile = new Mesh(new CylinderGeometry(0.065, 0.09, 0.035, 18), new MeshStandardMaterial({ color: 0xb99345, metalness: 0.52, roughness: 0.38 }))
    this.pile.position.y = 0.028
    this.pile.castShadow = true
    this.group.add(this.pile)

    this.light = new Mesh(new CylinderGeometry(0.07, 0.07, 0.006, 18), new MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.4, transparent: true, opacity: 0.72 }))
    this.light.position.y = 0.05
    this.group.add(this.light)

    this.label = new Sprite(new SpriteMaterial({ map: labelTexture(`${state.id}  /  ${state.label}`, color), transparent: true, depthWrite: false }))
    this.label.position.y = 0.21
    this.label.scale.set(0.27, 0.068, 1)
    this.group.add(this.label)
    this.setScenario('different')
    this.swarmReady = this.loadCanonicalSwarm()
  }

  get swarmCount() {
    return this.swarm.length
  }

  setScenario(scenario: HabitatScenario) {
    this.enabled = scenario !== 'off'
    this.properties = this.enabled ? propertiesFromState(this.state) : { ...NEUTRAL_PROPERTIES }
    this.applyAppearance()
  }

  setPhysicalProperties(properties: HabitatProperties) {
    this.enabled = true
    this.properties = { ...properties }
    this.applyAppearance()
  }

  private applyAppearance() {
    const visual = this.enabled ? this.properties : NEUTRAL_PROPERTIES
    const intensity = visual.brightness * (0.7 + visual.visualMotionIntensity * 0.3)
    ;(this.ring.material as MeshStandardMaterial).emissiveIntensity = intensity
    ;(this.light.material as MeshStandardMaterial).emissiveIntensity = intensity
    ;(this.light.material as MeshStandardMaterial).opacity = this.enabled ? 0.72 : 0.3
    for (const fly of this.swarm) fly.carrier.visible = this.enabled && visual.particleActivity > 0.04
  }

  setPosition(position: Vector3) {
    this.group.position.copy(position)
    for (const fly of this.swarm) {
      fly.start.set(
        SWARM_START_WORLD.x - position.x + fly.launchOffset.x,
        SWARM_START_WORLD.y - position.y + fly.launchOffset.y,
        SWARM_START_WORLD.z - position.z + fly.launchOffset.z,
      )
    }
  }

  resetPosition() {
    this.group.position.copy(this.basePosition)
  }

  update(elapsedSeconds: number) {
    const activity = this.properties.particleActivity
    const chaos = this.properties.chaos
    const sensoryDrive = Math.min(1, Math.max(0, 0.1 + this.properties.attractiveOdor * 0.95 - this.properties.aversiveDanger * 0.8))
    for (const fly of this.swarm) {
      const phase = fly.phase
      // The visual swarm is not given a target coordinate. This is a small
      // documented synthetic sensor demo: attraction/activity accelerate
      // approach, while aversive danger keeps members nearer the launch zone.
      const progress = Math.min(1, Math.max(0, (elapsedSeconds - 0.5) * (0.008 + sensoryDrive * 0.045)))
      const eased = progress * progress * (3 - 2 * progress)
      fly.carrier.position.lerpVectors(fly.start, fly.base, eased)
      fly.direction.subVectors(fly.base, fly.start).normalize()
      fly.carrier.rotation.y = Math.atan2(fly.direction.x, -fly.direction.z) + Math.sin(elapsedSeconds * 0.8 + phase) * 0.65
      fly.carrier.rotation.z = Math.sin(elapsedSeconds * 1.7 + phase) * 0.18 * (1 - progress)
      const angles = fly.wingBeat.step(1 / 30, activity)
      if (fly.leftWing) {
        fly.leftWing.quaternion.copy(fly.leftBase)
        this.applyWingAngles(fly.leftWing, angles.leftYaw, angles.leftRoll, angles.leftPitch)
      }
      if (fly.rightWing) {
        fly.rightWing.quaternion.copy(fly.rightBase)
        this.applyWingAngles(fly.rightWing, angles.rightYaw, angles.rightRoll, angles.rightPitch)
      }
    }
    this.pile.rotation.y = Math.sin(elapsedSeconds * (0.15 + this.properties.visualMotionIntensity * 2.0)) * this.properties.chaos * 0.08
  }

  private async loadCanonicalSwarm() {
    try {
      const loader = new FlybodyAssetLoader()
      // Two visible members per habitat are enough to communicate a swarm
      // without multiplying the 85-geom canonical asset into a frame-rate
      // problem. They are visual swarm members, not extra CNS simulations.
      const positions = [new Vector3(-0.055, 0.11, 0.015), new Vector3(0.05, 0.14, -0.02)]
      const launchOffsets = [new Vector3(-0.025, 0, 0), new Vector3(0.025, 0.025, 0)]
      const startPositions = launchOffsets.map((offset) => SWARM_START_WORLD.clone().sub(this.group.position).add(offset))
      const results = await Promise.all(positions.map(() => loader.load()))
      results.forEach((result, index) => {
        const carrier = new Group()
        carrier.name = `CanonicalFlybodySwarmMember:${this.state.id}:${index + 1}`
        carrier.position.copy(startPositions[index]!)
        carrier.scale.setScalar(8)
        const phase = index * Math.PI + this.state.activity * 0.7
        carrier.rotation.y = Math.sin(phase) * 0.65
        carrier.add(result.root)
        this.group.add(carrier)
        const visual: SwarmFlyVisual = {
          carrier,
          start: startPositions[index]!.clone(),
          base: positions[index]!.clone(),
          launchOffset: launchOffsets[index]!.clone(),
          phase,
          wingBeat: new WingBeatPatternGenerator(),
          leftWing: result.leftWing,
          rightWing: result.rightWing,
          direction: new Vector3(),
          leftBase: result.leftWing?.quaternion.clone() ?? new Quaternion(),
          rightBase: result.rightWing?.quaternion.clone() ?? new Quaternion(),
        }
        this.swarm.push(visual)
      })
      this.applyAppearance()
    } catch (error) {
      // Do not replace a failed canonical swarm member with a fake fly. The
      // habitat remains usable, but the status can report the missing body.
      console.warn(`Canonical Flybody swarm unavailable for ${this.state.id}: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

  private applyWingAngles(wing: Group, yaw: number, roll: number, pitch: number) {
    wing.quaternion.multiply(this.wingRotation.setFromAxisAngle(this.wingAxisZ, yaw))
    wing.quaternion.multiply(this.wingRotation.setFromAxisAngle(this.wingAxisX, roll))
    wing.quaternion.multiply(this.wingRotation.setFromAxisAngle(this.wingAxisY, pitch))
  }

  odorAt(position: Vector3, timeSeconds: number) {
    const distance = position.distanceTo(this.group.position)
    const sigma = 0.24 + this.properties.physicalRadiusM * 0.45
    const gaussian = Math.exp(-(distance * distance) / (2 * sigma * sigma))
    const fluctuation = 1 + Math.sin(timeSeconds * (0.7 + this.properties.chaos * 2.0) + this.group.position.x * 4.0) * this.properties.chaos * 0.08
    return {
      attractive: Math.min(1, Math.max(0, gaussian * this.properties.attractiveOdor * fluctuation)),
      aversive: Math.min(1, Math.max(0, gaussian * this.properties.aversiveDanger * fluctuation)),
    }
  }
}

interface SwarmFlyVisual {
  carrier: Group
  start: Vector3
  base: Vector3
  launchOffset: Vector3
  phase: number
  wingBeat: WingBeatPatternGenerator
  leftWing: Group | null
  rightWing: Group | null
  leftBase: Quaternion
  rightBase: Quaternion
  direction: Vector3
}

export function propertiesFromState(state: TokenState): HabitatProperties {
  return {
    physicalRadiusM: 0.09 + state.liquidityDepth * 0.13,
    resourcePileRadiusM: 0.045 + state.activity * 0.045,
    visualMotionIntensity: Math.min(1, state.activity * 0.72 + Math.abs(state.flowImbalance) * 0.18 + state.socialActivity * 0.1),
    brightness: Math.min(1, 0.16 + state.activity * 0.42 + state.socialActivity * 0.18),
    particleActivity: Math.min(1, state.activity * 0.7 + state.socialActivity * 0.2 + state.volatility * 0.1),
    chaos: Math.min(1, state.volatility * 0.6 + state.risk * 0.3 + (1 - state.stableStructure) * 0.1),
    attractiveOdor: Math.min(1, state.activity * 0.55 + state.liquidityDepth * 0.25 + Math.max(0, state.flowImbalance) * 0.2),
    aversiveDanger: Math.min(1, state.risk * 0.75 + state.volatility * 0.15 + (1 - state.stableStructure) * 0.1),
  }
}

function labelTexture(text: string, color: number) {
  const canvas = document.createElement('canvas')
  canvas.width = 640
  canvas.height = 150
  const context = canvas.getContext('2d')
  if (!context) return new CanvasTexture(canvas)
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.fillStyle = '#08121dcc'
  context.roundRect(4, 18, canvas.width - 8, 94, 18)
  context.fill()
  context.strokeStyle = `#${new Color(color).getHexString()}`
  context.lineWidth = 5
  context.stroke()
  context.fillStyle = '#eef7ff'
  context.font = '700 34px ui-monospace, monospace'
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  context.fillText(text, canvas.width / 2, 65)
  return new CanvasTexture(canvas)
}
