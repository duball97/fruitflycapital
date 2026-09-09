import { Color, DirectionalLight, Fog, Group, HemisphereLight, Scene, Vector3 } from 'three'
import { Arena } from './Arena'
import { MOCK_HABITAT_COLORS, MOCK_HABITAT_POSITIONS, MOCK_TOKEN_STATES } from './tokenFixtures'
import { TokenHabitat, type HabitatScenario } from './TokenHabitat'
import type { OdorFieldSample } from '../fly/FlySensors'
import type { EnvironmentUpdateMessage } from '../networking/protocol'

export class Environment {
  readonly group = new Group()
  readonly arena = new Arena()
  readonly bounds = this.arena.bounds
  readonly habitats: TokenHabitat[]
  readonly swarmReady: Promise<void>
  scenario: HabitatScenario = 'different'
  private lastVisualUpdate = Number.NEGATIVE_INFINITY

  constructor() {
    this.group.name = 'Environment'
    this.group.add(this.arena.group)
    this.habitats = MOCK_TOKEN_STATES.map((state, index) => {
      const habitat = new TokenHabitat(state, MOCK_HABITAT_POSITIONS[index]!, MOCK_HABITAT_COLORS[index]!)
      this.group.add(habitat.group)
      return habitat
    })
    this.swarmReady = Promise.all(this.habitats.map((habitat) => habitat.swarmReady)).then(() => undefined)
    this.setHabitatScenario('different')
  }

  get swarmCount() {
    return this.habitats.reduce((count, habitat) => count + habitat.swarmCount, 0)
  }

  get visualSwarmCapacity() {
    return this.habitats.length * 3
  }

  setHabitatScenario(scenario: HabitatScenario) {
    this.scenario = scenario
    this.habitats.forEach((habitat, index) => habitat.setScenario(scenario))
    if (scenario === 'swapped') {
      this.habitats.forEach((habitat, index) => habitat.setPosition(MOCK_HABITAT_POSITIONS[(index + 1) % MOCK_HABITAT_POSITIONS.length]!))
    } else {
      this.habitats.forEach((habitat) => habitat.resetPosition())
    }
  }

  applyMarketHabitats(update: EnvironmentUpdateMessage['environment']) {
    for (const state of update.habitats) {
      const habitat = this.habitats.find((candidate) => candidate.state.id === state.id)
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

  update(elapsedSeconds: number) {
    if (elapsedSeconds - this.lastVisualUpdate < 1 / 30) return
    this.lastVisualUpdate = elapsedSeconds
    this.habitats.forEach((habitat) => habitat.update(elapsedSeconds))
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
    scene.background = new Color(0x07111d)
    scene.fog = new Fog(0x07111d, 2.5, 5)
    scene.add(new HemisphereLight(0x9bc6ff, 0x162130, 1.25))
    const key = new DirectionalLight(0xfff0d0, 2.2)
    key.position.set(-1.5, 2.2, 1.1)
    key.castShadow = true
    key.shadow.mapSize.set(512, 512)
    scene.add(key)
  }

}
