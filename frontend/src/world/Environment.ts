import { AmbientLight, Color, DirectionalLight, Fog, Group, HemisphereLight, PointLight, Scene, SRGBColorSpace, TextureLoader, Vector3 } from 'three'
import { Arena } from './Arena'
import { CityBackdrop } from './CityBackdrop'
import { MOCK_HABITAT_COLORS, MOCK_HABITAT_POSITIONS, MOCK_TOKEN_STATES } from './tokenFixtures'
import { TokenHabitat, type HabitatScenario } from './TokenHabitat'
import type { OdorFieldSample } from '../fly/FlySensors'
import type { EnvironmentUpdateMessage } from '../networking/protocol'
import { ParticleField } from './ParticleField'
import type { TokenState } from './TokenState'

// The city is a directory of the first 100 tracked markets. This is separate
// from the smaller deep-observer tier on the backend.
const WORLD_HABITAT_CAPACITY = 100
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
      const nextState = tokenStateFromEnvironment(state)
      let habitat = this.habitatsById.get(state.id)
      if (!habitat) {
        habitat = this.addHabitat(nextState, this.positionFor(state.id, this.habitatList.length), this.colorFor(state.id))
      } else {
        habitat.setMarketState(nextState)
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
          // A fly should smell the strongest nearby source, not a saturated
          // sum of 100 overlapping habitats. Max-preserving the field keeps a
          // spatial gradient so the autonomous controller can still approach
          // a particular token place.
          attractive: Math.max(total.attractive, field.attractive),
          aversive: Math.max(total.aversive, field.aversive),
        }
      },
      { attractive: 0, aversive: 0 },
    )
  }

  /**
   * Contact is evaluated after physics, outside the CNS sensory payload.
   * The brain receives odor and bilateral gradients; swarm telemetry may
   * identify which habitat was actually touched afterward.
   */
  habitatContactAt(position: Vector3) {
    let nearest: { habitatId: string; distanceM: number; radiusM: number } | null = null
    for (const habitat of this.habitatList) {
      const distanceM = position.distanceTo(habitat.group.position)
      const radiusM = Math.max(0.045, habitat.properties.physicalRadiusM * 0.55 + 0.025)
      if (!nearest || distanceM < nearest.distanceM) nearest = { habitatId: habitat.state.id, distanceM, radiusM }
    }
    return {
      contact: nearest !== null && nearest.distanceM <= nearest.radiusM,
      habitatId: nearest?.habitatId ?? null,
      distanceM: nearest?.distanceM ?? Number.POSITIVE_INFINITY,
      radiusM: nearest?.radiusM ?? 0,
    }
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
    const columns = 10
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
    scene.fog = new Fog(0x1b3438, 2.5, 9.5)
    scene.add(new HemisphereLight(0x92c4c3, 0x152227, 1.26))
    scene.add(new AmbientLight(0x3b6d70, 0.78))
    const key = new DirectionalLight(0xffcf92, 1.95)
    key.position.set(-1.5, 2.2, 1.1)
    key.castShadow = false
    scene.add(key)
    const fill = new DirectionalLight(0x83d9ed, 1.18)
    fill.position.set(1.2, 1.1, -1.3)
    scene.add(fill)
    const moon = new DirectionalLight(0x87b9ff, 0.5)
    moon.position.set(-1.8, 2.8, -2.2)
    scene.add(moon)
    // Low-intensity street pools sell the night scene without turning every
    // habitat into an overexposed glowing disk.
    for (const [x, z, color] of [[-1.8, -1.4, 0x37b8ff], [1.65, 0.9, 0xff8c48], [0.2, 1.75, 0x72f0bf]] as const) {
      const streetLight = new PointLight(color, 0.62, 1.7, 2)
      streetLight.position.set(x, 0.46, z)
      scene.add(streetLight)
    }
  }

}

function tokenStateFromEnvironment(state: EnvironmentUpdateMessage['environment']['habitats'][number]): TokenState {
  const numberSignal = (name: string, fallback: number | null = null) => {
    const value = state.signals?.find((signal) => signal.name === name)?.value
    return typeof value === 'number' && Number.isFinite(value) ? value : fallback
  }
  return {
    id: state.id,
    label: state.label,
    tokenAddress: null,
    poolId: null,
    observedAtMs: 0,
    market: {
      priceInPair: null,
      priceUsd: numberSignal('market.priceUsd'),
      marketCapUsd: numberSignal('market.marketCapUsd'),
      fdvUsd: numberSignal('market.fdvUsd'),
      volume5mUsd: numberSignal('market.volume5mUsd', 0) ?? 0,
      volume15mUsd: numberSignal('market.volume15mUsd', 0) ?? 0,
      volume1hUsd: numberSignal('market.volume1hUsd', 0) ?? 0,
      volume24hUsd: numberSignal('market.volume24hUsd'),
    },
    flow: {
      buyCount5m: numberSignal('flow.buyCount5m', 0) ?? 0,
      sellCount5m: numberSignal('flow.sellCount5m', 0) ?? 0,
      buyUsd5m: numberSignal('flow.buyUsd5m', 0) ?? 0,
      sellUsd5m: numberSignal('flow.sellUsd5m', 0) ?? 0,
      flowImbalance: numberSignal('flow.imbalance', 0) ?? 0,
      txVelocity5m: numberSignal('flow.txVelocity5m', 0) ?? 0,
      txAcceleration: numberSignal('flow.txAcceleration', 0) ?? 0,
    },
    liquidity: {
      liquidityUsd: numberSignal('liquidity.usd', 0) ?? 0,
      liquidityDeltaUsd: numberSignal('liquidity.deltaUsd'),
      volumeLiquidityRatio1h: numberSignal('liquidity.volumeLiquidityRatio1h', 0) ?? 0,
      marketCapToLiquidity: numberSignal('liquidity.marketCapToLiquidity'),
      fdvToLiquidity: numberSignal('liquidity.fdvToLiquidity'),
      volume24hToMarketCap: numberSignal('liquidity.volume24hToMarketCap'),
      volume24hToLiquidity: numberSignal('liquidity.volume24hToLiquidity'),
    },
    holders: { status: 'unavailable', holderCount: null, growth24h: null, top10Concentration: null },
    security: { status: 'unavailable', honeypot: null, contractVerified: null, ownerControl: null },
    social: { status: 'unavailable', mentions: null, sentiment: null },
    lore: { status: 'unavailable', catalysts: [] },
    signals: (state.signals ?? []).map((signal) => ({
      ...signal,
      value: typeof signal.value === 'number' || typeof signal.value === 'string' || signal.value === null ? signal.value : null,
    })),
    provenance: state.provenance ?? [],
    financial: state.financialTrace ?? null,
  }
}

function hashString(value: string) {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) hash = Math.imul(hash ^ value.charCodeAt(index), 16777619)
  return hash >>> 0
}
