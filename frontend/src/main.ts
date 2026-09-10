import './style.css'
import { Scene, Vector3, WebGLRenderer } from 'three'
import { Environment } from './world/Environment'
import { World } from './world/World'
import { BrainSocket } from './networking/BrainSocket'
import type { FlyAgent } from './fly/FlyAgent'
import { FlyPopulation } from './fly/FlyPopulation'
import { DebugRenderer } from './rendering/DebugRenderer'
import { FreeCamera } from './camera/FreeCamera'
import { FollowCamera } from './camera/FollowCamera'
import { FirstPersonCamera } from './camera/FirstPersonCamera'
import { SideCamera } from './camera/SideCamera'
import { FlightLogger } from './networking/FlightLog'
import { BODIES_PER_BRAIN, SWARM_SIZE, VISUAL_FLY_COUNT } from './fly/SwarmConfig'
import { PostProcessingPipeline, type RenderQuality } from './rendering/PostProcessing'
import { FlyTrails } from './world/FlyTrails'
import { PresentationCamera, type PresentationCameraMode } from './camera/PresentationCamera'
import { isLiveBrainSource, vectorToWire } from './networking/protocol'
import { BrainActivityPanel } from './rendering/BrainActivityPanel'

// The public experience is intentionally autonomous. Manual actuation remains
// available only inside the controller module for isolated developer tests; it
// is not selectable from the product UI or environment configuration.
const app = document.querySelector<HTMLDivElement>('#app')
if (!app) throw new Error('Missing #app root')

const canvas = document.createElement('canvas')
canvas.className = 'world-canvas'
app.append(canvas)

// Keep the initial empty room out of view. The first frame is shown only after
// the canonical Flybody scene is ready and the physics loop has produced a
// real motion sample, so loading never looks like a broken/empty simulation.
const startupScreen = document.createElement('div')
startupScreen.className = 'startup-screen'
startupScreen.innerHTML = `
  <div class="startup-card">
    <div class="startup-kicker">FRUIT FLY CAPITAL</div>
    <div class="startup-title">NEUROSWARM</div>
    <div class="startup-message">LOADING CANONICAL FLYBODY</div>
    <div class="startup-detail">Preparing the independent agents and first motion sample…</div>
    <div class="startup-progress"><span></span></div>
  </div>
`
app.append(startupScreen)
const startupMessage = startupScreen.querySelector<HTMLDivElement>('.startup-message')!
const startupProgress = startupScreen.querySelector<HTMLSpanElement>('.startup-progress span')!

const hud = document.createElement('div')
hud.className = 'hud'
hud.innerHTML = `
  <div class="brand"><span class="brand-mark">✦</span> FRUIT FLY CAPITAL</div>
  <div class="neuroswarm">NEUROSWARM</div>
  <a class="portfolio-link" href="./portfolio.html">VIEW FUND PORTFOLIO →</a>
`
app.append(hud)

const demoStatus = document.createElement('div')
demoStatus.className = 'demo-status'
app.append(demoStatus)

const status = document.createElement('div')
status.className = 'socket-status debug-only'
app.append(status)
const logButton = document.createElement('button')
logButton.className = 'log-button debug-only'
logButton.textContent = 'DOWNLOAD SELECTED FLY LOG'
app.append(logButton)
const scene = new Scene()
const renderer = new WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' })
renderer.setPixelRatio(1)
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.shadowMap.enabled = false

const environment = new Environment()
environment.setupLighting(scene)

const causalStatus = document.createElement('div')
causalStatus.className = 'causal-status debug-only'
causalStatus.textContent = 'CAUSE MAP · selecting a fly…'
app.append(causalStatus)

const populationStatus = document.createElement('div')
populationStatus.className = 'population-status debug-only'
populationStatus.innerHTML = `<strong>NEUROSWARM</strong><br>VISUAL FLIES ${VISUAL_FLY_COUNT} · INDEPENDENT BRAINS ${SWARM_SIZE} · BODIES / BRAIN ${BODIES_PER_BRAIN}`
app.append(populationStatus)

const brainUrl = import.meta.env.VITE_BRAIN_WS_URL ?? 'ws://127.0.0.1:8765'
const brainSocket = new BrainSocket(brainUrl)
const flightLog = new FlightLogger()
const brainUpdateHz = Math.max(1, Number(import.meta.env.VITE_BRAIN_UPDATE_HZ ?? 2) || 2)
let selectedIndex = 0
let lastMarketUiStatus = ''

// The pilot population is deliberately a numbered set of real CNS agents.
// Additional bodies are explicitly render-only followers of these primaries.
const population = new FlyPopulation({ brainSocket, brainUpdateHz, size: SWARM_SIZE })
const { agents, renderers: flyRenderers, followers } = population
const followerRenderers = followers.map((follower) => follower.renderer)
const visualRenderers = [...flyRenderers, ...followerRenderers]

const world = new World(scene, agents, environment)
visualRenderers.forEach((flyRenderer) => world.add(flyRenderer.group))

const bodyStatus = document.createElement('div')
bodyStatus.className = 'body-status debug-only'
bodyStatus.textContent = 'BODY · loading canonical Flybody XML + OBJ assets'
app.append(bodyStatus)
let canonicalBodiesReady = false
void Promise.all(visualRenderers.map((flyRenderer) => flyRenderer.ready)).then(() => {
  const firstRenderer = flyRenderers[0]
  const allCanonical = visualRenderers.every((flyRenderer) => flyRenderer.assetStatus === 'canonical')
  bodyStatus.textContent = `BODY · ${allCanonical ? `canonical Flybody loaded · ${firstRenderer?.meshCount ?? 0} XML geoms × ${VISUAL_FLY_COUNT} visual flies` : 'canonical Flybody asset error · see console'} · ${SWARM_SIZE} independent brains · ${BODIES_PER_BRAIN} bodies/brain`
  canonicalBodiesReady = true
})

const debug = new DebugRenderer(app, 'FLY #001', 'right')
let debugPanelVisible = false
debug.setPanelVisible(debugPanelVisible)
world.add(debug.group)

const brainActivityPanel = new BrainActivityPanel(app)

const trails = new FlyTrails(agents)
world.add(trails.mesh)

const free = new FreeCamera(renderer.domElement)
const follow = new FollowCamera()
const firstPerson = new FirstPersonCamera()
const side = new SideCamera()
const presentation = new PresentationCamera()
const cameras = [free.camera, follow.camera, firstPerson.camera, side.camera, presentation.camera] as const
// Start in the user-controlled free orbit. Cinematic views remain opt-in via
// the camera panel; they should never take over the first view.
let cameraIndex = 0
let activeCamera = cameras[cameraIndex] ?? cameras[0]!
const cameraFocus = new Vector3()
const pipeline = new PostProcessingPipeline(renderer, scene, activeCamera)
let renderQuality: RenderQuality = 'performance'
const storedQuality = window.localStorage.getItem('ffc.renderQuality')
if (storedQuality === 'demo' || storedQuality === 'performance') renderQuality = storedQuality
pipeline.setQuality(renderQuality)
presentation.setMode('overview')

const performanceStatus = document.createElement('div')
performanceStatus.className = 'performance-status debug-only'
performanceStatus.textContent = 'PERF · measuring…'
app.append(performanceStatus)

// Keep the public view calm. Detailed telemetry remains in the DOM for
// developer inspection, but there is no user-facing debug switch.
app.classList.add('presentation-demo')

const cameraTargetPanel = document.createElement('div')
cameraTargetPanel.className = 'camera-target-panel debug-only'
const cameraTargetLabel = document.createElement('span')
cameraTargetLabel.textContent = 'INSPECT FLY'
cameraTargetPanel.append(cameraTargetLabel)
const flySelector = document.createElement('select')
flySelector.setAttribute('aria-label', 'Select fly to inspect')
for (let index = 0; index < SWARM_SIZE; index += 1) {
  const option = document.createElement('option')
  option.value = String(index)
  option.textContent = `#${String(index + 1).padStart(3, '0')}`
  flySelector.append(option)
}
flySelector.value = String(selectedIndex)
flySelector.addEventListener('change', () => setSelectedFly(Number(flySelector.value), false))
cameraTargetPanel.append(flySelector)
const focusButton = document.createElement('button')
focusButton.textContent = 'FOCUS'
focusButton.addEventListener('click', () => {
  cameraIndex = 0
  free.focusOn(cameraTargetPosition())
})
cameraTargetPanel.append(focusButton)
for (const [label, mode] of [
  ['SWARM', 'overview'],
  ['TOKEN', 'token'],
  ['AUTO', 'director'],
] as Array<[string, PresentationCameraMode]>) {
  const button = document.createElement('button')
  button.textContent = label
  button.addEventListener('click', () => {
    presentation.setMode(mode)
    cameraIndex = 4
  })
  cameraTargetPanel.append(button)
}
const followButton = document.createElement('button')
followButton.textContent = 'FOLLOW'
followButton.addEventListener('click', () => { cameraIndex = 1 })
cameraTargetPanel.append(followButton)
const freeButton = document.createElement('button')
freeButton.textContent = 'FREE'
freeButton.addEventListener('click', () => { cameraIndex = 0 })
cameraTargetPanel.append(freeButton)
app.append(cameraTargetPanel)

function setSelectedFly(index: number, focus: boolean) {
  selectedIndex = population.select(index)
  flySelector.value = String(selectedIndex)
  debug.setLabel(`FLY #${String(selectedIndex + 1).padStart(3, '0')}`)
  if (focus && cameraIndex === 0) free.focusOn(cameraTargetPosition())
}

function cameraTargetPosition() {
  return cameraFocus.copy(agents[selectedIndex]!.body.position)
}

function cameraTargetAgent() {
  return agents[selectedIndex]!
}

let debugVectorsVisible = false
debug.setVectorsVisible(debugVectorsVisible)

function resize() {
  renderer.setSize(window.innerWidth, window.innerHeight)
  pipeline.resize(window.innerWidth, window.innerHeight)
  for (const camera of cameras) {
    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
  }
}
window.addEventListener('resize', resize)

brainSocket.onStatusChange((next) => {
  status.innerHTML = `<span class="status-dot ${next}"></span> brain socket ${next} <span class="socket-url">${brainUrl}</span>`
  if (next === 'connected') brainSocket.requestEnvironment()
})
brainSocket.connect()
window.setInterval(() => brainSocket.requestEnvironment(), 15000)

logButton.addEventListener('click', () => flightLog.download())

const clock = performance.now()
let previous = clock
let nextLogAt = 0
let nextCausalUiAt = 0
let nextSwarmTelemetryAt = 0
let startupReleased = false
let nextPerfUiAt = 0
function animate(now: number) {
  const delta = (now - previous) / 1000
  previous = now
  world.update(delta)
  followers.forEach((follower) => follower.update(delta, world.elapsedSeconds))
  environment.updateVisuals(world.elapsedSeconds)
  trails.update(agents, selectedIndex, delta)
  updateStartupGate(delta)
  const marketEnvironment = brainSocket.environmentUpdate()
  if (marketEnvironment?.status === 'ok') environment.applyMarketHabitats(marketEnvironment)
  updateMarketStatus(marketEnvironment)

  if (world.elapsedSeconds >= nextSwarmTelemetryAt) {
    brainSocket.sendSwarmTelemetry({
      type: 'swarm_telemetry',
      timestampMs: Date.now(),
      agents: agents.map((agent) => ({
        flyId: agent.id,
        timestampMs: Date.now(),
        position: vectorToWire(agent.body.position),
        habitats: environment.habitats.map((habitat) => ({
          habitatId: habitat.state.id,
          distanceM: agent.body.position.distanceTo(habitat.group.position),
          radiusM: habitat.properties.physicalRadiusM,
          contact: false,
        })),
      })),
    })
    nextSwarmTelemetryAt += 0.25
  }

  if (world.elapsedSeconds >= nextLogAt) {
    flightLog.record(agents[selectedIndex]!, brainSocket, world.elapsedSeconds)
    nextLogAt += 0.1
  }

  flyRenderers.forEach((flyRenderer, index) => {
    flyRenderer.setSelected(index === selectedIndex)
    flyRenderer.update(agents[index]!, world.elapsedSeconds)
  })
  const selectedAgent = agents[selectedIndex]!
  // Diagnostics are intentionally not part of the product view. Avoid doing
  // hidden DOM/raster work or ArrowHelper math on every frame when the panels
  // are disabled; this matters with 80 canonical Flybody renderers.
  if (debugPanelVisible || debugVectorsVisible) {
    debug.update(selectedAgent, world.elapsedSeconds, brainSocket.getStatus(), brainSocket.stimulationFor(selectedAgent.id), brainSocket.activityFor(selectedAgent.id))
  }
  if (debugPanelVisible) {
    brainActivityPanel.update(selectedAgent, brainSocket.activityFor(selectedAgent.id), brainSocket.stimulationFor(selectedAgent.id), world.elapsedSeconds)
  }
  if (debugPanelVisible && world.elapsedSeconds >= nextCausalUiAt) {
    updateCausalStatus(selectedAgent)
    nextCausalUiAt += 0.25
  }
  if (debugPanelVisible) {
    const liveBrains = agents.reduce((count, agent) => count + (isLiveBrainSource(brainSocket.activityFor(agent.id)?.source) ? 1 : 0), 0)
    const cnsActive = agents.reduce((count, agent) => {
      const activity = brainSocket.activityFor(agent.id)
      return count + (activity !== null && isLiveBrainSource(activity.source) && Object.values(activity.spikeCounts).some((count) => count > 0) ? 1 : 0)
    }, 0)
    const cnsMotorControlled = agents.reduce((count, agent) => {
      if (agent.mode !== 'malecns') return count
      const activity = brainSocket.activityFor(agent.id)
      const command = agent.actuators.get()
      const nonNeutral = command.forwardThrust > 0 || Math.abs(command.yawTorque) > 0 || Math.abs(command.pitchTorque) > 0 || Math.abs(command.rollTorque) > 0
      return count + (isLiveBrainSource(activity?.source) && nonNeutral ? 1 : 0)
    }, 0)
    const movingAgents = agents.reduce((count, agent) => count + (agent.body.velocity.length() > 0.002 ? 1 : 0), 0)
    populationStatus.innerHTML = `<strong>NEUROSWARM</strong><br>VISIBLE FLIES ${VISUAL_FLY_COUNT} · INDEPENDENT BRAINS ${SWARM_SIZE} · BODIES / BRAIN ${BODIES_PER_BRAIN}<br>CNS RUNTIMES ${liveBrains}/${SWARM_SIZE} · CNS ACTIVE ${cnsActive}/${SWARM_SIZE} · MOVING ${movingAgents}/${SWARM_SIZE}<br>MALECNS DRIVE ${cnsMotorControlled}/${SWARM_SIZE}`
  }
  activeCamera = cameras[cameraIndex] ?? cameras[0]!
  if (cameraIndex === 0) free.update()
  const followedAgent = cameraTargetAgent()
  if (cameraIndex === 1) follow.update(followedAgent)
  if (cameraIndex === 2) firstPerson.update(followedAgent)
  if (cameraIndex === 3) side.update(followedAgent)
  if (cameraIndex === 4) presentation.update(world.elapsedSeconds, agents, environment.habitats, selectedIndex)

  visualRenderers.forEach((flyRenderer, index) => {
    const distance = flyRenderer.group.position.distanceTo(activeCamera.position)
    const selectedPrimary = index < flyRenderers.length && index === selectedIndex
    flyRenderer.setSelected(selectedPrimary)
    const lod = selectedPrimary || distance < 0.42 ? 'full' : distance < 1.15 ? 'medium' : 'low'
    flyRenderer.setLod(lod)
  })

  const marketLabel = marketEnvironment?.status === 'ok'
    ? `${marketEnvironment.habitats.length} TOKEN PLACES`
    : 'WAITING FOR TOKEN DATA'
  const brainLabel = brainSocket.getStatus() === 'connected' ? 'AUTONOMOUS FLY BRAINS' : 'CONNECTING TO FLY BRAINS'
  demoStatus.innerHTML = `<strong>NEUROSWARM</strong><span>${VISUAL_FLY_COUNT} FLIES · ${SWARM_SIZE} INDEPENDENT BRAINS</span><span>${marketLabel} · ${brainLabel}</span>`
  pipeline.render(delta, activeCamera)
  if (debugPanelVisible && world.elapsedSeconds >= nextPerfUiAt) {
    const lodCounts = visualRenderers.reduce((counts, flyRenderer) => {
      const lod = flyRenderer.currentLod
      counts[lod] += 1
      return counts
    }, { full: 0, medium: 0, low: 0 })
    const fps = delta > 0 ? Math.round(1 / delta) : 0
    performanceStatus.textContent = `PERF · ${fps} FPS · ${renderer.info.render.calls} calls · ${renderer.info.render.triangles} tris · LOD full/med/low ${lodCounts.full}/${lodCounts.medium}/${lodCounts.low} · particles ${environment.particles.count} · brain ${brainUpdateHz} Hz · ${renderQuality.toUpperCase()}`
    nextPerfUiAt += 0.25
  }
  requestAnimationFrame(animate)
}

function updateStartupGate(delta: number) {
  if (startupReleased) return
  const movingAgents = agents.reduce((count, agent) => count + (agent.body.velocity.length() > 0.002 ? 1 : 0), 0)
  if (!canonicalBodiesReady) {
    startupMessage.textContent = 'LOADING CANONICAL FLYBODY'
    startupProgress.style.width = '42%'
  } else if (movingAgents < Math.max(1, Math.ceil(SWARM_SIZE * 0.5))) {
    startupMessage.textContent = 'STARTING SWARM MOTION'
    startupProgress.style.width = '78%'
  } else {
    startupMessage.textContent = 'SWARM IN MOTION'
    startupProgress.style.width = '100%'
  }

  // There is deliberately no preview timeout. The public scene opens only
  // after the live MaleCNS path has produced real physical movement.
  if (canonicalBodiesReady && brainSocket.getStatus() === 'connected' && movingAgents >= Math.max(1, Math.ceil(SWARM_SIZE * 0.5))) {
    startupReleased = true
    startupScreen.classList.add('is-ready')
    window.setTimeout(() => startupScreen.remove(), 500)
  }
}

function updateMarketStatus(environmentUpdate: ReturnType<BrainSocket['environmentUpdate']>) {
  const status = environmentUpdate?.status ?? 'waiting'
  const detail = environmentUpdate?.error ?? environmentUpdate?.reason ?? 'waiting for the Python market feed'
  const uiStatus = `${status}:${detail}`
  if (uiStatus === lastMarketUiStatus) return
  lastMarketUiStatus = uiStatus
  demoStatus.title = detail
}

function updateCausalStatus(agent: FlyAgent) {
  const stimulation = brainSocket.stimulationFor(agent.id)
  const activity = brainSocket.activityFor(agent.id)
  const frame = agent.sensors.getFrame()
  const command = agent.actuators.get()
  const brainStep = activity !== null && isLiveBrainSource(activity.source)
    ? `Brian2 output · DN ${Object.values(activity.descendingRates).some((rate) => rate > 0) ? 'active' : 'quiet'}`
    : activity
      ? 'decoder-only output · no live Brian2 provider'
      : 'waiting for this fly\'s brain output'
  causalStatus.innerHTML = [
    `<strong>CAUSE MAP · ${agent.id}</strong> · ${brainStep}`,
    `senses: vision L/R ${frame.leftEye.meanLuminance.toFixed(2)}/${frame.rightEye.meanLuminance.toFixed(2)} · odor ${frame.odor.concentration.toFixed(2)} · wall ${frame.contact.wall}`,
    `spikes/DN: ${stimulation ? `${stimulation.visual.length} visual + ${stimulation.olfactory.length} odor` : 'not encoded yet'} → decoded MaleCNS output → command ${command.forwardThrust.toFixed(2)} thrust · ${command.yawTorque.toFixed(2)} yaw · ${command.pitchTorque.toFixed(2)} pitch`,
  ].join('<br>')
}

requestAnimationFrame(animate)
