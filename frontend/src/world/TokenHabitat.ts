import { CylinderGeometry, Group, Mesh, MeshBasicMaterial, MeshStandardMaterial, RingGeometry, Vector3 } from 'three'
import type { TokenState } from './TokenState'

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

export class TokenHabitat {
  readonly group = new Group()
  readonly state: TokenState
  readonly basePosition = new Vector3()
  properties: HabitatProperties = { ...NEUTRAL_PROPERTIES }
  private readonly pile: Mesh
  private readonly coin: Mesh
  private readonly pressureRing: Mesh
  private readonly signalColumn: Mesh
  private readonly signalCap: Mesh
  private enabled = true

  constructor(state: TokenState, position: Vector3, color: number) {
    this.state = state
    this.basePosition.copy(position)
    this.group.name = `TokenHabitat:${state.id}`
    this.group.position.copy(position)

    this.pile = new Mesh(new CylinderGeometry(0.065, 0.09, 0.035, 18), new MeshStandardMaterial({ color: 0xb99345, metalness: 0.52, roughness: 0.38 }))
    this.pile.position.y = 0.028
    this.pile.castShadow = true
    this.group.add(this.pile)

    // The colored coin is the only identity marker in the 3D world. Floating
    // labels and orbit rings obscured the actual fly/coin interaction and
    // were not sensory inputs.
    this.coin = new Mesh(new CylinderGeometry(0.07, 0.07, 0.007, 18), new MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.4, roughness: 0.34 }))
    this.coin.position.y = 0.05
    this.coin.castShadow = true
    this.group.add(this.coin)

    this.pressureRing = new Mesh(
      new RingGeometry(0.078, 0.083, 32),
      new MeshBasicMaterial({ color, transparent: true, opacity: 0.26, side: 2, depthWrite: false }),
    )
    this.pressureRing.rotation.x = -Math.PI / 2
    this.pressureRing.position.y = 0.056
    this.group.add(this.pressureRing)

    this.signalColumn = new Mesh(
      new CylinderGeometry(0.009, 0.015, 0.12, 6),
      new MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.35, transparent: true, opacity: 0.55, roughness: 0.28 }),
    )
    this.signalColumn.position.y = 0.115
    this.signalColumn.visible = false
    this.group.add(this.signalColumn)
    this.signalCap = new Mesh(
      new CylinderGeometry(0.017, 0.017, 0.004, 8),
      new MeshBasicMaterial({ color, transparent: true, opacity: 0.42, depthWrite: false }),
    )
    this.signalCap.position.y = 0.178
    this.signalCap.visible = false
    this.group.add(this.signalCap)
    this.setScenario('different')
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
    ;(this.coin.material as MeshStandardMaterial).emissiveIntensity = intensity
    ;(this.coin.material as MeshStandardMaterial).opacity = this.enabled ? 1 : 0.42
    ;(this.pressureRing.material as MeshBasicMaterial).opacity = this.enabled ? 0.18 + visual.chaos * 0.35 : 0.07
    this.signalColumn.visible = this.enabled && visual.visualMotionIntensity > 0.04
    this.signalCap.visible = this.signalColumn.visible
    const columnMaterial = this.signalColumn.material as MeshStandardMaterial
    columnMaterial.emissiveIntensity = 0.25 + visual.brightness * 1.2
  }

  get isEnabled() {
    return this.enabled
  }

  update(timeSeconds: number) {
    const visual = this.enabled ? this.properties : NEUTRAL_PROPERTIES
    const pulse = 0.82 + Math.sin(timeSeconds * (1.1 + visual.visualMotionIntensity * 4.5) + this.basePosition.x * 2.7) * 0.18
    this.coin.scale.setScalar(0.98 + visual.visualMotionIntensity * 0.04 * pulse)
    this.pressureRing.scale.setScalar(0.94 + visual.chaos * 0.22 + visual.visualMotionIntensity * 0.08 * pulse)
    this.pressureRing.rotation.z = timeSeconds * (0.03 + visual.chaos * 0.24)
    if (this.signalColumn.visible) {
      const columnScale = 0.5 + visual.particleActivity * 1.4 + visual.chaos * 0.4
      this.signalColumn.scale.set(1, columnScale * pulse, 1)
      this.signalCap.scale.setScalar(0.8 + visual.particleActivity * 0.45)
      this.signalCap.position.y = 0.115 + 0.06 * columnScale * pulse
    }
  }

  setPosition(position: Vector3) {
    this.group.position.copy(position)
  }

  resetPosition() {
    this.setPosition(this.basePosition)
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

export function propertiesFromState(state: TokenState): HabitatProperties {
  const activity = signal(state, 'market.volume5mUsd', 0)
  const txVelocity = signal(state, 'flow.txVelocity5m', 0)
  const liquidity = signal(state, 'liquidity.usd', 0)
  const flow = signalValence(state, 'flow.imbalance', state.flow.flowImbalance)
  const risk = Math.min(1, Math.max(0, 0.55 * (1 - liquidity) + 0.45 * Math.abs(flow)))
  const activityLevel = Math.min(1, Math.max(0, 0.65 * activity + 0.35 * txVelocity))
  return {
    physicalRadiusM: 0.09 + liquidity * 0.13,
    resourcePileRadiusM: 0.045 + activityLevel * 0.045,
    visualMotionIntensity: Math.min(1, activityLevel * 0.8 + Math.abs(flow) * 0.2),
    brightness: Math.min(1, 0.16 + activityLevel * 0.5),
    particleActivity: Math.min(1, activityLevel * 0.72 + txVelocity * 0.28),
    chaos: risk,
    attractiveOdor: Math.min(1, activityLevel * 0.65 + liquidity * 0.2 + Math.max(0, flow) * 0.15),
    aversiveDanger: risk,
  }
}

function signal(state: TokenState, name: string, fallback: number) {
  return state.signals.find((candidate) => candidate.name === name)?.normalized ?? fallback
}

function signalValence(state: TokenState, name: string, fallback: number) {
  return state.signals.find((candidate) => candidate.name === name)?.valence ?? fallback
}
