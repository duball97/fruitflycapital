import { BoxGeometry, CanvasTexture, CircleGeometry, CylinderGeometry, Group, Mesh, MeshBasicMaterial, MeshPhysicalMaterial, MeshStandardMaterial, PointLight, RingGeometry, Sprite, SpriteMaterial, SphereGeometry, TorusGeometry, Vector3 } from 'three'
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
  semanticType: 'food' | 'rot' | 'trash' | 'market'
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
  semanticType: 'market',
}

export class TokenHabitat {
  readonly group = new Group()
  state: TokenState
  private readonly initialState: TokenState
  readonly basePosition = new Vector3()
  properties: HabitatProperties = { ...NEUTRAL_PROPERTIES }
  private readonly pile: Mesh
  private readonly coin: Mesh
  private readonly pressureRing: Mesh
  private readonly innerRing: Mesh
  private readonly outerRing: Mesh
  private readonly signalColumn: Mesh
  private readonly signalCap: Mesh
  private readonly signalLight: PointLight
  private readonly floorGlow: Mesh
  private readonly label: Sprite
  private readonly semanticGroup = new Group()
  private enabled = true

  constructor(state: TokenState, position: Vector3, color: number) {
    this.state = state
    this.initialState = state
    this.basePosition.copy(position)
    this.group.name = `TokenHabitat:${state.id}`
    this.group.position.copy(position)
    this.semanticGroup.name = 'SemanticSmellSource'
    this.group.add(this.semanticGroup)

    this.floorGlow = new Mesh(
      new CircleGeometry(0.18, 32),
      new MeshBasicMaterial({ color, transparent: true, opacity: 0.08, depthWrite: false }),
    )
    this.floorGlow.rotation.x = -Math.PI / 2
    this.floorGlow.position.y = 0.006
    this.group.add(this.floorGlow)

    this.label = new Sprite(new SpriteMaterial({ map: labelTexture(state.label), transparent: true, depthWrite: false }))
    this.label.name = 'TokenLabel'
    this.label.position.y = 0.23
    this.label.scale.set(0.31, 0.058, 1)
    this.group.add(this.label)

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

    this.innerRing = new Mesh(
      new TorusGeometry(0.078, 0.004, 8, 36),
      new MeshPhysicalMaterial({ color, emissive: color, emissiveIntensity: 0.35, metalness: 0.62, roughness: 0.24, clearcoat: 0.65, clearcoatRoughness: 0.2 }),
    )
    this.innerRing.rotation.x = Math.PI / 2
    this.innerRing.position.y = 0.056
    this.group.add(this.innerRing)

    this.outerRing = new Mesh(
      new TorusGeometry(0.104, 0.0022, 6, 40),
      new MeshBasicMaterial({ color, transparent: true, opacity: 0.18, depthWrite: false }),
    )
    this.outerRing.rotation.x = Math.PI / 2
    this.outerRing.position.y = 0.058
    this.group.add(this.outerRing)

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
    this.signalLight = new PointLight(color, 0, 0.5, 2)
    this.signalLight.position.y = 0.11
    this.group.add(this.signalLight)
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
    this.semanticGroup.visible = this.enabled
    this.rebuildSemanticVisual(visual.semanticType)
    const intensity = visual.brightness * (0.7 + visual.visualMotionIntensity * 0.3)
    ;(this.coin.material as MeshStandardMaterial).emissiveIntensity = intensity
    ;(this.coin.material as MeshStandardMaterial).opacity = this.enabled ? 1 : 0.42
    ;(this.pressureRing.material as MeshBasicMaterial).opacity = this.enabled ? 0.18 + visual.chaos * 0.35 : 0.07
    ;(this.outerRing.material as MeshBasicMaterial).opacity = this.enabled ? 0.12 + visual.chaos * 0.2 : 0.04
    ;(this.innerRing.material as MeshPhysicalMaterial).emissiveIntensity = this.enabled ? 0.24 + visual.brightness * 0.55 : 0.08
    this.pile.scale.setScalar(Math.max(0.72, visual.resourcePileRadiusM / 0.06))
    this.signalLight.intensity = this.enabled ? 0.05 + visual.brightness * 0.38 + visual.particleActivity * 0.18 : 0
    this.floorGlow.visible = this.enabled
    ;(this.floorGlow.material as MeshBasicMaterial).opacity = this.enabled ? 0.045 + visual.brightness * 0.13 : 0
    this.floorGlow.scale.setScalar(0.82 + visual.physicalRadiusM * 2.4)
    // The old floating column/cap read as a sci-fi status widget rather than
    // a place a fly would investigate. Signal is now carried by the physical
    // prop, floor glow, and neon token label.
    this.signalColumn.visible = false
    this.signalCap.visible = false
    const columnMaterial = this.signalColumn.material as MeshStandardMaterial
    columnMaterial.emissiveIntensity = 0.25 + visual.brightness * 1.2
  }

  private rebuildSemanticVisual(type: HabitatProperties['semanticType']) {
    if (this.semanticGroup.userData.type === type) return
    this.semanticGroup.traverse((object) => {
      const mesh = object as Mesh
      mesh.geometry?.dispose()
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      materials.forEach((material) => material?.dispose())
    })
    this.semanticGroup.clear()
    this.semanticGroup.userData.type = type
    const add = (geometry: any, material: MeshStandardMaterial, x: number, y: number, z: number) => {
      const mesh = new Mesh(geometry, material)
      mesh.position.set(x, y, z)
      mesh.castShadow = true
      this.semanticGroup.add(mesh)
    }
    if (type === 'food') {
      // Bruised fruit and a curved banana are the attractive odor source.
      add(new CylinderGeometry(0.052, 0.058, 0.018, 14), new MeshStandardMaterial({ color: 0x403b2d, roughness: 0.94 }), 0, 0.062, 0)
      add(new TorusGeometry(0.018, 0.005, 7, 14, Math.PI * 1.35), new MeshStandardMaterial({ color: 0xe0b83c, roughness: 0.78 }), -0.025, 0.085, 0.012)
      add(new SphereGeometry(0.022, 8, 6), new MeshStandardMaterial({ color: 0xe86f45, roughness: 0.72 }), -0.032, 0.075, 0.014)
      add(new SphereGeometry(0.018, 8, 6), new MeshStandardMaterial({ color: 0x8ebd4b, roughness: 0.8 }), 0.028, 0.072, -0.012)
      add(new SphereGeometry(0.013, 7, 5), new MeshStandardMaterial({ color: 0x9a4d31, roughness: 0.92 }), 0.012, 0.075, 0.022)
    } else if (type === 'rot') {
      add(new SphereGeometry(0.034, 8, 6), new MeshStandardMaterial({ color: 0x14191a, roughness: 0.98 }), -0.018, 0.078, 0.012)
      add(new SphereGeometry(0.026, 7, 5), new MeshStandardMaterial({ color: 0x52613a, roughness: 1 }), 0.026, 0.07, -0.01)
      add(new SphereGeometry(0.014, 7, 5), new MeshStandardMaterial({ color: 0x8a6b37, roughness: 1 }), 0.004, 0.086, 0.024)
    } else if (type === 'trash') {
      add(new CylinderGeometry(0.026, 0.021, 0.075, 12), new MeshStandardMaterial({ color: 0x2b3538, metalness: 0.42, roughness: 0.78 }), -0.026, 0.09, 0.008)
      add(new TorusGeometry(0.026, 0.004, 6, 14), new MeshStandardMaterial({ color: 0x59686b, metalness: 0.54, roughness: 0.62 }), -0.026, 0.13, 0.008)
      add(new SphereGeometry(0.029, 8, 6), new MeshStandardMaterial({ color: 0x121517, roughness: 0.98 }), 0.026, 0.074, -0.014)
    } else {
      add(new BoxGeometry(0.065, 0.048, 0.055), new MeshStandardMaterial({ color: 0x805938, roughness: 0.9 }), -0.025, 0.082, 0.012)
      add(new BoxGeometry(0.008, 0.052, 0.058), new MeshStandardMaterial({ color: 0x34271d, roughness: 0.94 }), -0.025, 0.083, 0.012)
      add(new BoxGeometry(0.008, 0.048, 0.058), new MeshStandardMaterial({ color: 0x34271d, roughness: 0.94 }), 0.002, 0.083, 0.012)
      add(new BoxGeometry(0.031, 0.024, 0.031), new MeshStandardMaterial({ color: 0x4d6470, metalness: 0.28, roughness: 0.76 }), 0.031, 0.067, -0.012)
    }
  }

  get isEnabled() {
    return this.enabled
  }

  update(timeSeconds: number) {
    const visual = this.enabled ? this.properties : NEUTRAL_PROPERTIES
    const pulse = 0.82 + Math.sin(timeSeconds * (1.1 + visual.visualMotionIntensity * 4.5) + this.basePosition.x * 2.7) * 0.18
    this.coin.scale.setScalar(0.98 + visual.visualMotionIntensity * 0.04 * pulse)
    this.pressureRing.scale.setScalar(0.94 + visual.chaos * 0.22 + visual.visualMotionIntensity * 0.08 * pulse)
    this.pressureRing.rotation.z = timeSeconds * (0.008 + visual.chaos * 0.04)
    this.innerRing.scale.setScalar(0.98 + visual.visualMotionIntensity * 0.06 * pulse)
    this.outerRing.scale.setScalar(0.96 + visual.chaos * 0.35 + visual.visualMotionIntensity * 0.12 * pulse)
    this.outerRing.rotation.z = -timeSeconds * (0.004 + visual.visualMotionIntensity * 0.02)
    this.signalLight.intensity = this.enabled ? 0.08 + visual.brightness * 0.65 + visual.particleActivity * (0.22 + pulse * 0.18) : 0
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

  setIdentity(id: string, label: string) {
    this.state = { ...this.state, id, label }
    this.label.material.map?.dispose()
    this.label.material.map = labelTexture(label)
    this.label.material.needsUpdate = true
    this.group.name = `TokenHabitat:${id}`
  }

  resetIdentity() {
    this.state = this.initialState
    this.group.name = `TokenHabitat:${this.state.id}`
  }

  resetPosition() {
    this.setPosition(this.basePosition)
  }

  dispose() {
    this.group.traverse((object) => {
      const mesh = object as Mesh
      mesh.geometry?.dispose()
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
      materials.forEach((material) => material?.dispose())
    })
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

function labelTexture(value: string) {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 96
  const context = canvas.getContext('2d')
  if (context) {
    context.clearRect(0, 0, canvas.width, canvas.height)
    context.shadowColor = 'rgba(40, 244, 205, 0.95)'
    context.shadowBlur = 18
    context.fillStyle = 'rgba(3, 12, 19, 0.94)'
    context.beginPath()
    context.roundRect(8, 8, canvas.width - 16, canvas.height - 16, 18)
    context.fill()
    context.shadowBlur = 0
    context.strokeStyle = 'rgba(69, 239, 216, 0.96)'
    context.lineWidth = 3
    context.stroke()
    context.fillStyle = '#8fffea'
    context.font = '700 34px monospace'
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.fillText(value.slice(0, 22), canvas.width / 2, canvas.height / 2 + 1)
  }
  const texture = new CanvasTexture(canvas)
  texture.needsUpdate = true
  return texture
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
    semanticType: semanticType(activityLevel, liquidity, risk),
  }
}

function semanticType(activity: number, liquidity: number, risk: number): HabitatProperties['semanticType'] {
  if (risk >= 0.62) return 'rot'
  if (activity < 0.28) return 'trash'
  if (liquidity >= 0.62) return 'food'
  return 'market'
}

function signal(state: TokenState, name: string, fallback: number) {
  return state.signals.find((candidate) => candidate.name === name)?.normalized ?? fallback
}

function signalValence(state: TokenState, name: string, fallback: number) {
  return state.signals.find((candidate) => candidate.name === name)?.valence ?? fallback
}
