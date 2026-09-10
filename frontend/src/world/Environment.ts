import { AmbientLight, Color, DirectionalLight, Fog, Group, HemisphereLight, PointLight, Scene, SRGBColorSpace, TextureLoader, Vector3 } from 'three'
import { Arena } from './Arena'
import { CityBackdrop } from './CityBackdrop'
import { MOCK_HABITAT_COLORS, MOCK_HABITAT_POSITIONS, MOCK_TOKEN_STATES } from './tokenFixtures'
import { TokenHabitat, type HabitatScenario } from './TokenHabitat'
import type { OdorFieldSample } from '../fly/FlySensors'
import type { EnvironmentUpdateMessage } from '../networking/protocol'
import { ParticleField } from './ParticleField'
import type { TokenState } from './TokenState'

const WORLD_HABITAT_CAPACITY = 128
const HABITAT_PALETTE = [0x4bd6a0, 0x6ca8ff, 0xff6e80, 0xf5c84c, 0xa980ff, 0xff9b5c, 0x56d9d0, 0xff80b8]

export class Environment {
  readonly group = new Group()
  readonly arena = new Arena()
  readonly city = new CityBackdrop()
  readonly bounds = this.arena.bounds
  private readonly habitatsById = new Map<string, TokenHabitat>()
  private readonly habitatList: TokenHabitat[] = []
  private readonly slotsById = new Map<string, number>()
  readonly particles: ParticleField
  get habitats() {
    return this.habitatList
  }
  private lastAppliedMarketObservedAtMs = 0
  scenario: HabitatScenario = 'live'

  constructor() {
    this.group.name = 'Environment'
    this.group.add(this.city.group)
    this.group.add(this.arena.group)
    this.particles = new ParticleField(this.habitatList, 24, WORLD_HABITAT_CAPACITY)
    this.group.add(this.particles.mesh)
    this.setHabitatScenario('live')
  }

  setHabitatScenario(scenario: HabitatScenario) {
    this.scenario = scenario
    if (scenario === 'live') this.lastAppliedMarketObservedAtMs = 0
    if (scenario !== 'live' && this.habitatList.length === 0) {
      MOCK_TOKEN_STATES.forEach((state, index) => this.addHabitat(
        state,
        MOCK_HABITAT_POSITIONS[index]!,
        MOCK_HABITAT_COLORS[index]!,
      ))
    }
    // Live Graph is an external-data mode. Keep fixture values hidden while
    // the backend is disabled, waiting, or returning an error; otherwise a
    // failed live feed looks like real market data in the scene.
    const appearanceScenario = scenario === 'live' ? 'off' : scenario
    this.habitatList.forEach((habitat) => {
      if (scenario !== 'live') habitat.resetIdentity()
      habitat.setScenario(appearanceScenario)
    })
    if (scenario === 'swapped') {
      this.habitatList.forEach((habitat, index) => habitat.setPosition(MOCK_HABITAT_POSITIONS[(index + 1) % MOCK_HABITAT_POSITIONS.length] ?? this.positionFor(habitat.state.id, index)))
    } else {
      this.habitatList.forEach((habitat) => habitat.resetPosition())
    }
  }

  applyMarketHabitats(update: EnvironmentUpdateMessage['environment']) {
    if (update.observedAtMs <= this.lastAppliedMarketObservedAtMs) return
    this.lastAppliedMarketObservedAtMs = update.observedAtMs
    // The market snapshot is authoritative. New IDs create new habitats,
    // existing IDs retain their position, and departed IDs are retired.
    const incomingIds = new Set<string>()
    for (const state of update.habitats.slice(0, WORLD_HABITAT_CAPACITY)) {
      incomingIds.add(state.id)
      let habitat = this.habitatsById.get(state.id)
      if (!habitat) {
        habitat = this.addHabitat(tokenStateFromEnvironment(state), this.positionFor(state.id, this.habitatList.length), this.colorFor(state.id))
      } else {
        habitat.setIdentity(state.id, state.label)
      }
      habitat.setPhysicalProperties({
        physicalRadiusM: state.physicalRadiusM,
        resourcePileRadiusM: state.resourcePileRadiusM,
        visualMotionIntensity: state.visualMotionIntensity,
        brightness: state.brightness,
        particleActivity: state.particleActivity,
        chaos: state.chaos,
        attractiveOdor: state.attractiveOdor,
        aversiveDanger: state.aversiveDanger,
        semanticType: state.semanticType === 'food' || state.semanticType === 'rot' || state.semanticType === 'trash' || state.semanticType === 'market'
          ? state.semanticType
          : 'market',
      })
    }
    for (let index = this.habitatList.length - 1; index >= 0; index -= 1) {
      const habitat = this.habitatList[index]!
      if (incomingIds.has(habitat.state.id)) continue
      this.group.remove(habitat.group)
      habitat.dispose()
      this.habitatsById.delete(habitat.state.id)
      this.slotsById.delete(habitat.state.id)
      this.habitatList.splice(index, 1)
    }
  }

  updateVisuals(timeSeconds: number) {
    this.habitatList.forEach((habitat) => habitat.update(timeSeconds))
    this.particles.update(timeSeconds)
  }

  sampleOdorAt(position: Vector3, timeSeconds: number): OdorFieldSample {
    return this.habitatList.reduce(
      (total, habitat) => {
        const field = habitat.odorAt(position, timeSeconds)
        return {
          attractive: Math.min(1, total.attractive + field.attractive),
          aversive: Math.min(1, total.aversive + field.aversive),
        }
      },
      { attractive: 0, aversive: 0 },
    )
  }

  private addHabitat(state: TokenState, position: Vector3, color: number) {
    const habitat = new TokenHabitat(state, position, color)
    this.habitatsById.set(state.id, habitat)
    this.habitatList.push(habitat)
    this.group.add(habitat.group)
    return habitat
  }

  private colorFor(id: string) {
    return HABITAT_PALETTE[hashString(id) % HABITAT_PALETTE.length] ?? HABITAT_PALETTE[0]!
  }

  private positionFor(id: string, fallbackIndex: number) {
    const slot = this.slotFor(id, fallbackIndex)
    const columns = 16
    const rows = Math.ceil(WORLD_HABITAT_CAPACITY / columns)
    const x = -0.86 + (slot % columns) * (1.72 / (columns - 1))
    const z = -0.86 + Math.floor(slot / columns) * (1.72 / Math.max(1, rows - 1))
    return new Vector3(x, 0, z)
  }

  private slotFor(id: string, fallbackIndex: number) {
    const existing = this.slotsById.get(id)
    if (existing !== undefined) return existing
    const occupied = new Set(this.slotsById.values())
    let slot = hashString(id) % WORLD_HABITAT_CAPACITY
    for (let attempt = 0; attempt < WORLD_HABITAT_CAPACITY; attempt += 1) {
      if (!occupied.has(slot)) {
        this.slotsById.set(id, slot)
        return slot
      }
      slot = (slot + 1) % WORLD_HABITAT_CAPACITY
    }
    const fallback = fallbackIndex % WORLD_HABITAT_CAPACITY
    this.slotsById.set(id, fallback)
    return fallback
  }

  setupLighting(scene: Scene) {
    // The image is a Three.js scene background, not a UI overlay. Keep a
    // dark fallback while it loads so the city never flashes pale gray.
    scene.background = new Color(0x061017)
    const background = new TextureLoader().load('/design/fruit-fly-capital-canva-background.png', (texture) => {
      texture.colorSpace = SRGBColorSpace
      scene.background = texture
    })
    background.colorSpace = SRGBColorSpace
    scene.fog = new Fog(0x102b2b, 1.35, 4.8)
    scene.add(new HemisphereLight(0x476d78, 0x081318, 0.72))
    scene.add(new AmbientLight(0x17333a, 0.32))
    const key = new DirectionalLight(0xffc77d, 1.35)
    key.position.set(-1.5, 2.2, 1.1)
    key.castShadow = false
    scene.add(key)
    const fill = new DirectionalLight(0x61b9d6, 0.72)
    fill.position.set(1.2, 1.1, -1.3)
    scene.add(fill)
    // Low-intensity street pools sell the night scene without turning every
    // habitat into an overexposed glowing disk.
    for (const [x, z, color] of [[-1.8, -1.4, 0x37b8ff], [1.65, 0.9, 0xff8c48], [0.2, 1.75, 0x72f0bf]] as const) {
      const streetLight = new PointLight(color, 0.42, 1.3, 2)
      streetLight.position.set(x, 0.46, z)
      scene.add(streetLight)
    }
  }

}

function tokenStateFromEnvironment(state: EnvironmentUpdateMessage['environment']['habitats'][number]): TokenState {
  return {
    id: state.id,
    label: state.label,
    tokenAddress: null,
    poolId: null,
    observedAtMs: 0,
    market: { priceInPair: null, volume5mUsd: 0, volume15mUsd: 0, volume1hUsd: 0 },
    flow: { buyCount5m: 0, sellCount5m: 0, buyUsd5m: 0, sellUsd5m: 0, flowImbalance: 0, txVelocity5m: 0, txAcceleration: 0 },
    liquidity: { liquidityUsd: 0, liquidityDeltaUsd: null, volumeLiquidityRatio1h: 0 },
    holders: { status: 'unavailable', holderCount: null, growth24h: null, top10Concentration: null },
    security: { status: 'unavailable', honeypot: null, contractVerified: null, ownerControl: null },
    social: { status: 'unavailable', mentions: null, sentiment: null },
    lore: { status: 'unavailable', catalysts: [] },
    signals: [],
    provenance: [],
  }
}

function hashString(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619)
  return hash >>> 0
}
