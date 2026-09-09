import './style.css'
import { Scene, Vector3, WebGLRenderer } from 'three'
import { Environment } from './world/Environment'
import { World } from './world/World'
import { BrainSocket } from './networking/BrainSocket'
import { FlyAgent } from './fly/FlyAgent'
import { KeyboardState, ManualController, MaleCNSController, StationaryController, SwitchableController } from './fly/FlyController'
import { FlyRenderer } from './rendering/FlyRenderer'
import { DebugRenderer } from './rendering/DebugRenderer'
import { FreeCamera } from './camera/FreeCamera'
import { FollowCamera } from './camera/FollowCamera'
import { FirstPersonCamera } from './camera/FirstPersonCamera'
import { SideCamera } from './camera/SideCamera'
import { FlightLogger } from './networking/FlightLog'

const app = document.querySelector<HTMLDivElement>('#app')
if (!app) throw new Error('Missing #app root')

const canvas = document.createElement('canvas')
canvas.className = 'world-canvas'
app.append(canvas)

const hud = document.createElement('div')
hud.className = 'hud'
hud.innerHTML = `
  <div class="brand"><span class="brand-mark">✦</span> MALECNS / FLY WORLD</div>
  <div class="subtitle">Connectome-constrained embodied flight sandbox</div>
  <div class="controls-hint">
    <span><kbd>W</kbd><kbd>S</kbd> pitch</span>
    <span><kbd>A</kbd><kbd>D</kbd> yaw</span>
    <span><kbd>Q</kbd><kbd>E</kbd> roll</span>
    <span><kbd>Shift</kbd> thrust</span>
    <span><kbd>Ctrl</kbd> descend</span>
    <span><kbd>M</kbd> manual / MaleCNS</span>
    <span><kbd>1–4</kbd> cameras</span>
    <span><kbd>V</kbd> debug vectors</span>
    <span>mouse drag orbit · right-drag pan · wheel zoom</span>
  </div>
`
app.append(hud)

const status = document.createElement('div')
status.className = 'socket-status'
app.append(status)
const logButton = document.createElement('button')
logButton.className = 'log-button'
logButton.textContent = 'DOWNLOAD FLIGHT LOG'
app.append(logButton)
const modeButton = document.createElement('button')
modeButton.className = 'mode-button'
modeButton.textContent = 'MODE: MALECNS · FLY A / FLY B OFF (M)'
app.append(modeButton)
const architectureStatus = document.createElement('div')
architectureStatus.className = 'architecture-status'
architectureStatus.textContent = 'AGENTS · Fly A autonomous candidate · Fly B OFF · separate CNS state'
app.append(architectureStatus)

const scene = new Scene()
const renderer = new WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' })
// Retina rendering multiplies the expensive canonical Flybody scene by four
// pixels. One device pixel is the stable interactive default; users can still
// zoom the camera without increasing simulation cost.
renderer.setPixelRatio(1)
renderer.setSize(window.innerWidth, window.innerHeight)
renderer.shadowMap.enabled = false

const environment = new Environment()
environment.setupLighting(scene)

const scenarioPanel = document.createElement('div')
scenarioPanel.className = 'scenario-panel'
const scenarioTitle = document.createElement('span')
scenarioTitle.textContent = 'HABITATS'
scenarioPanel.append(scenarioTitle)
const scenarioButtons: Array<[string, HTMLButtonElement]> = []
for (const [scenario, label] of [['off', 'A · OFF'], ['different', 'B · DIFFERENT'], ['swapped', 'C · SWAPPED'], ['live', 'D · LIVE GRAPH']] as const) {
  const button = document.createElement('button')
  button.textContent = label
  button.setAttribute('aria-pressed', String(scenario === environment.scenario))
  button.addEventListener('click', () => {
    environment.setHabitatScenario(scenario)
    scenarioButtons.forEach(([candidate, candidateButton]) => candidateButton.setAttribute('aria-pressed', String(candidate === scenario)))
    scenarioTitle.textContent = `HABITATS · ${label}`
  })
  scenarioButtons.push([scenario, button])
  scenarioPanel.append(button)
}
app.append(scenarioPanel)

const keyboard = new KeyboardState()
const brainUrl = import.meta.env.VITE_BRAIN_WS_URL ?? 'ws://127.0.0.1:8765'
const brainSocket = new BrainSocket(brainUrl)
const flightLog = new FlightLogger()
logButton.addEventListener('click', () => flightLog.download())
const manual = new ManualController(keyboard)
const brainUpdateHz = Math.max(1, Number(import.meta.env.VITE_BRAIN_UPDATE_HZ ?? 10) || 10)
const malecnsA = new MaleCNSController(brainSocket, 'fly-a', brainUpdateHz)
const controllerA = new SwitchableController(manual, malecnsA)
const controllerB = new StationaryController()
controllerA.setMode('malecns')
// Start one CNS fly in a distant launch zone and keep the second body off.
// The brain receives sensory fields only; it is not given a token position or
// target coordinate.
const agentA = new FlyAgent('fly-a', controllerA, new Vector3(-0.025, 0.64, 0.94))
const agentB = new FlyAgent('fly-b', controllerB, new Vector3(0.025, 0.68, 0.94))
modeButton.addEventListener('click', () => {
  controllerA.toggleMode()
})
const world = new World(scene, [agentA, agentB], environment)
const flyRendererA = new FlyRenderer()
const flyRendererB = new FlyRenderer()
world.add(flyRendererA.group)
world.add(flyRendererB.group)
const bodyStatus = document.createElement('div')
bodyStatus.className = 'body-status'
bodyStatus.textContent = 'BODY · loading canonical Flybody XML + OBJ assets'
app.append(bodyStatus)
void Promise.all([flyRendererA.ready, flyRendererB.ready, environment.swarmReady]).then(() => {
  bodyStatus.textContent = `BODY · ${flyRendererA.assetStatus === 'canonical' && flyRendererB.assetStatus === 'canonical' ? `canonical Flybody loaded · ${flyRendererA.meshCount} XML geoms` : 'asset fallback · inspect console'} · CNS AGENTS · 1 active (A) · FLY B OFF · SWARM VISUALS · ${environment.swarmCount}/6`
})

const debugA = new DebugRenderer(app, 'FLY A', 'right')
const debugB = new DebugRenderer(app, 'FLY B', 'left')
world.add(debugA.group)
world.add(debugB.group)

const free = new FreeCamera(renderer.domElement)
const follow = new FollowCamera()
const firstPerson = new FirstPersonCamera()
const side = new SideCamera()
const cameras = [free.camera, follow.camera, firstPerson.camera, side.camera] as const
// Free orbit is the useful default: the cursor can zoom to the flies and pan
// around them. Follow view remains available with key 2.
let cameraIndex = 0
let activeCamera = cameras[cameraIndex]
let debugVectorsVisible = false
debugA.setVectorsVisible(debugVectorsVisible)
debugB.setVectorsVisible(debugVectorsVisible)

function resize() {
  renderer.setSize(window.innerWidth, window.innerHeight)
  for (const camera of cameras) {
    camera.aspect = window.innerWidth / window.innerHeight
    camera.updateProjectionMatrix()
  }
}
window.addEventListener('resize', resize)

window.addEventListener('keydown', (event) => {
  if (event.repeat) return
  if (event.code === 'KeyM') {
    controllerA.toggleMode()
  }
  if (event.code === 'KeyV') {
    debugVectorsVisible = !debugVectorsVisible
    debugA.setVectorsVisible(debugVectorsVisible)
    debugB.setVectorsVisible(debugVectorsVisible)
  }
  const cameraKey = Number(event.code.replace('Digit', ''))
  if (cameraKey >= 1 && cameraKey <= 4) cameraIndex = cameraKey - 1
})

brainSocket.onStatusChange((next) => {
  status.innerHTML = `<span class="status-dot ${next}"></span> brain socket ${next} <span class="socket-url">${brainUrl}</span>`
  if (next === 'connected') brainSocket.requestEnvironment()
})
brainSocket.connect()
window.setInterval(() => brainSocket.requestEnvironment(), 15000)

const clock = performance.now()
let previous = clock
let nextLogAt = 0
function animate(now: number) {
  const delta = (now - previous) / 1000
  previous = now
  world.update(delta)
  const marketEnvironment = brainSocket.environmentUpdate()
  if (environment.scenario === 'live' && marketEnvironment?.status === 'ok') environment.applyMarketHabitats(marketEnvironment)
  if (world.elapsedSeconds >= nextLogAt) {
    flightLog.record(agentA, brainSocket, world.elapsedSeconds)
    flightLog.record(agentB, brainSocket, world.elapsedSeconds)
    nextLogAt += 0.05
  }
  flyRendererA.update(agentA, world.elapsedSeconds)
  flyRendererB.update(agentB, world.elapsedSeconds)
  debugA.update(agentA, world.elapsedSeconds, brainSocket.getStatus(), brainSocket.stimulationFor(agentA.id), brainSocket.activityFor(agentA.id))
  debugB.update(agentB, world.elapsedSeconds, brainSocket.getStatus(), brainSocket.stimulationFor(agentB.id), brainSocket.activityFor(agentB.id))
  const modeLabel = agentA.mode === 'manual' ? 'MANUAL · FLY A / FLY B OFF' : 'MALECNS · FLY A / FLY B OFF'
  modeButton.textContent = `MODE: ${modeLabel} (M)`
  architectureStatus.textContent = agentA.mode === 'manual'
    ? 'AGENTS · Fly A keyboard → actuator interface · Fly B OFF'
    : 'AGENTS · Fly A sensors → MaleCNS → decoder → actuators · Fly B OFF'

  activeCamera = cameras[cameraIndex] ?? cameras[0]
  if (cameraIndex === 0) free.update()
  if (cameraIndex === 1) follow.update(agentA)
  if (cameraIndex === 2) firstPerson.update(agentA)
  if (cameraIndex === 3) side.update(agentA)
  renderer.render(scene, activeCamera)
  requestAnimationFrame(animate)
}
requestAnimationFrame(animate)
