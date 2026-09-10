import { AmbientLight, Color, DirectionalLight, Fog, Group, HemisphereLight, Scene, Vector3 } from 'three'
import { Arena } from './Arena'
import { MOCK_HABITAT_COLORS, MOCK_HABITAT_POSITIONS, MOCK_TOKEN_STATES } from './tokenFixtures'
import { TokenHabitat, type HabitatScenario } from './TokenHabitat'
import type { OdorFieldSample } from '../fly/FlySensors'
import type { EnvironmentUpdateMessage } from '../networking/protocol'
import { ParticleField } from './ParticleField'
import { PropLibrary } from './PropLibrary'

export class Environment {
  readonly group = new Group()
  readonly arena = new Arena()
  readonly bounds = this.arena.bounds
  readonly habitats: TokenHabitat[]
  readonly particles: ParticleField
  readonly propsGroup = new Group()
  readonly propsReady: Promise<void>
  private readonly propLibrary = new PropLibrary()
  private lastAppliedMarketObservedAtMs = 0
  scenario: HabitatScenario = 'different'

  constructor() {
    this.group.name = 'Environment'
    this.group.add(this.arena.group)
    this.habitats = MOCK_TOKEN_STATES.map((state, index) => {
      const habitat = new TokenHabitat(state, MOCK_HABITAT_POSITIONS[index]!, MOCK_HABITAT_COLORS[index]!)
      this.group.add(habitat.group)
      return habitat
    })
    this.particles = new ParticleField(this.habitats)
    this.group.add(this.particles.mesh)
    this.propsGroup.name = 'LocalCC0Props'
    this.group.add(this.propsGroup)
    this.propsReady = this.loadLocalProps()
    this.setHabitatScenario('different')
  }

  setHabitatScenario(scenario: HabitatScenario) {
    this.scenario = scenario
    if (scenario === 'live') this.lastAppliedMarketObservedAtMs = 0
    // Live Graph is an external-data mode. Keep fixture values hidden while
    // the backend is disabled, waiting, or returning an error; otherwise a
    // failed live feed looks like real market data in the scene.
    const appearanceScenario = scenario === 'live' ? 'off' : scenario
    this.habitats.forEach((habitat) => habitat.setScenario(appearanceScenario))
    if (scenario === 'swapped') {
      this.habitats.forEach((habitat, index) => habitat.setPosition(MOCK_HABITAT_POSITIONS[(index + 1) % MOCK_HABITAT_POSITIONS.length]!))
    } else {
      this.habitats.forEach((habitat) => habitat.resetPosition())
    }
  }

  applyMarketHabitats(update: EnvironmentUpdateMessage['environment']) {
    if (update.observedAtMs <= this.lastAppliedMarketObservedAtMs) return
    this.lastAppliedMarketObservedAtMs = update.observedAtMs
    // A fresh snapshot is authoritative. Clear stale values before applying
    // the configured habitats from this response.
    this.habitats.forEach((habitat) => habitat.setScenario('off'))
    for (const [index, state] of update.habitats.entries()) {
      // Discovered markets use canonical chain-aware IDs (for example
      // ethereum:0xpair), while the prototype has three fixed visual slots.
      // Match known fixture IDs when present and otherwise place the first
      // discovered markets into those slots deterministically.
      const habitat = this.habitats.find((candidate) => candidate.state.id === state.id) ?? this.habitats[index]
      if (!habitat) continue
      habitat.setPhysicalProperties({
        physicalRadiusM: state.physicalRadiusM,
        resourcePileRadiusM: state.resourcePileRadiusM,
        visualMotionIntensity: state.visualMotionIntensity,
        brightness: state.brightness,
        particleActivity: state.particleActivity,
        chaos: state.chaos,
        attractiveOdor: state.attractiveOdor,
        aversiveDanger: state.aversiveDanger,
      })
    }
  }

  updateVisuals(timeSeconds: number) {
    this.habitats.forEach((habitat) => habitat.update(timeSeconds))
    this.particles.update(timeSeconds)
  }

  sampleOdorAt(position: Vector3, timeSeconds: number): OdorFieldSample {
    return this.habitats.reduce(
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

  setupLighting(scene: Scene) {
    scene.background = new Color(0x7e8d87)
    scene.fog = new Fog(0x7e8d87, 3.2, 6.5)
    scene.add(new HemisphereLight(0xe8f4ed, 0x5e6962, 2.1))
    scene.add(new AmbientLight(0xc6d5cf, 0.52))
    const key = new DirectionalLight(0xffe8c5, 3.2)
    key.position.set(-1.5, 2.2, 1.1)
    key.castShadow = false
    scene.add(key)
    const fill = new DirectionalLight(0xbad5ff, 1.15)
    fill.position.set(1.2, 1.1, -1.3)
    scene.add(fill)
  }

  private async loadLocalProps() {
    try {
      const [trashCan, cardboardBox] = await Promise.all([
        this.propLibrary.place('trashCan', new Vector3(-0.88, 0, -0.18), 0.18),
        this.propLibrary.place('cardboardBox', new Vector3(0.86, 0, -0.55), 0.13),
      ])
      trashCan.rotation.y = -0.28
      cardboardBox.rotation.y = 0.32
      this.propsGroup.add(trashCan, cardboardBox)
    } catch (error) {
      // Local props are presentation-only. A missing optional CC0 asset must
      // never block the biological world from starting.
      console.warn(`Optional local CC0 props unavailable: ${error instanceof Error ? error.message : String(error)}`)
    }
  }

}
