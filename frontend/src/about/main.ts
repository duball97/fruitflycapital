import './style.css'
import { AmbientLight, Color, DirectionalLight, Group, PerspectiveCamera, Quaternion, Scene, SRGBColorSpace, Vector3, WebGLRenderer } from 'three'
import { FlyRenderer } from '../rendering/FlyRenderer'
import type { ActuatorCommand } from '../networking/protocol'

const app = document.querySelector<HTMLElement>('#about-app')!

app.innerHTML = `
  <header class="site-header">
    <a class="site-brand" href="/" aria-label="FruitFly Capital home"><img src="/fruitfly-logo.png" alt="" /><span>FRUITFLY CAPITAL</span></a>
    <nav class="site-nav" aria-label="Primary navigation"><a href="/">Simulation</a><a class="is-active" href="/about/">About</a><a href="/portfolio/">Portfolio</a><a href="/#buy">Buy</a><a href="https://x.com/fruitflycap" target="_blank" rel="noreferrer">Community</a></nav>
    <a class="header-social" href="https://x.com/fruitflycap" target="_blank" rel="noreferrer" aria-label="FruitFly Capital on X"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18.9 2H22l-6.77 7.74L23.2 22h-6.24l-4.89-6.39L6.48 22H3.36l7.24-8.28L2.8 2h6.4l4.42 5.84L18.9 2Zm-1.1 17.7h1.73L8.28 4.2H6.42L17.8 19.7Z" /></svg><span>@fruitflycap</span></a>
  </header>
  <main>
    <section class="about-hero"><div class="hero-copy"><p class="eyebrow">FRUITFLY CAPITAL</p><h1>What happens when we give a crypto wallet to a swarm of fly brains?</h1><p class="lede">FruitFly Capital is a crypto experiment in autonomous biological decision-making. A population of simulated fruit flies explores a market, senses token habitats, and forms portfolio proposals from its collective behavior.</p><a class="about-cta" href="/">ENTER THE SIMULATION <span>→</span></a></div><div class="model-card"><div class="model-label"><span>CANONICAL FLYBODY PREVIEW</span><span>ROTATING MODEL</span></div><div class="model-stage"><canvas id="fly-model-canvas" aria-label="Rotating canonical fruit fly model"></canvas><span id="fly-model-status" class="model-status">LOADING CANONICAL FLYBODY…</span></div><p>One small agent. A measurable signal.</p></div></section>
    <section class="research-story"><div class="research-copy"><p class="eyebrow">THE MAP BEHIND THE MODEL</p><h2>A complete male fruit fly brain connectome</h2><p>Google Research, HHMI Janelia, and collaborators mapped the complete male fruit fly brain and central nervous system. The published connectome contains more than 166,000 neurons and 125 million synaptic connections, creating a detailed map of how sensory inputs can flow through the brain toward action.</p><p>FruitFly Capital takes inspiration from that milestone: the flies in this experiment are independent agents with sensory state, motor output, and observable behavior—not a single scripted cursor.</p><a class="source-link" href="https://research.google/blog/a-connectomics-milestone-mapping-the-complete-male-fruit-fly-brain/" target="_blank" rel="noreferrer">READ THE GOOGLE RESEARCH ARTICLE <span>↗</span></a></div><figure class="research-figure"><img src="/about/male-fruit-fly-brain-map.png" alt="Colorful 3D visualization of the male fruit fly brain connectome" loading="lazy" /><figcaption>Visualization of the mapped male fruit fly brain and its neural connections.</figcaption></figure></section>
    <section class="about-grid"><article><span class="section-index">01</span><h2>Biological signal</h2><p>Each fly has its own brain, sensory inputs, flight path, and memory of contact with a token habitat. The system observes attraction, approach, landing, dwell, and departure as measurable behavior.</p></article><article><span class="section-index">02</span><h2>Collective portfolio</h2><p>One fly represents one independent vote. With 100 flies, each agent can represent roughly 1% of the biological portfolio. Repeated visits and sustained dwell make a signal stronger than a passing encounter.</p></article><article><span class="section-index">03</span><h2>Proposal first</h2><p>The simulation makes the decision process visible before execution. Buy and sell intents are logged from fly behavior, while wallet actions remain bounded and auditable.</p></article></section>
    <section class="visual-rail"><figure><img src="/fruitfly-social-card.png" alt="FruitFly Capital visual identity" loading="lazy" /></figure><figure><img src="/design/fruit-fly-capital-canva-background.png" alt="FruitFly Capital abstract market background" loading="lazy" /></figure></section>
  </main>
  <footer class="site-footer"><span>FRUITFLY CAPITAL · AUTONOMOUS BIOLOGICAL FUND</span><a href="/">SIMULATION</a><a href="/portfolio/">PORTFOLIO</a><a href="https://x.com/fruitflycap" target="_blank" rel="noreferrer">X @FRUITFLYCAP</a><span class="footer-source">RESEARCH INSPIRED BY GOOGLE RESEARCH + HHMI JANELIA</span></footer>
`

const canvas = document.querySelector<HTMLCanvasElement>('#fly-model-canvas')!
const modelStatus = document.querySelector<HTMLSpanElement>('#fly-model-status')!
const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true })
renderer.outputColorSpace = SRGBColorSpace
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
const scene = new Scene()
scene.background = new Color(0x0b1718)
scene.add(new AmbientLight(0xc9fff0, 1.8))
const key = new DirectionalLight(0x9be8c7, 3.2)
key.position.set(2, 3, 4)
scene.add(key)
const rim = new DirectionalLight(0x73a8ff, 1.8)
rim.position.set(-3, 1, -2)
scene.add(rim)
const camera = new PerspectiveCamera(28, 1, 0.001, 10)
camera.position.set(0, 0.025, 0.2)
const model = new Group()
scene.add(model)
const flyRenderer = new FlyRenderer()
const neutralCommand: ActuatorCommand = { forwardThrust: 0, verticalThrust: 0.5, yawTorque: 0, pitchTorque: 0, rollTorque: 0 }
const flyPosition = new Vector3()
const flyQuaternion = new Quaternion()
model.add(flyRenderer.group)

function resize() {
  const width = Math.max(1, canvas.clientWidth)
  const height = Math.max(1, canvas.clientHeight)
  renderer.setSize(width, height, false)
  camera.aspect = width / height
  camera.updateProjectionMatrix()
}
resize()
window.addEventListener('resize', resize)

void flyRenderer.ready.then(() => {
  if (flyRenderer.assetStatus === 'canonical') {
    modelStatus.hidden = true
  } else {
    modelStatus.textContent = 'CANONICAL FLYBODY UNAVAILABLE'
    modelStatus.classList.add('is-error')
  }
})

let last = performance.now()
function animate(now: number) {
  const delta = Math.min(0.05, (now - last) / 1000)
  last = now
  flyRenderer.updatePose(flyPosition, flyQuaternion, neutralCommand, now / 1000)
  model.rotation.y += delta * 0.55
  model.rotation.x = Math.sin(now * 0.00035) * 0.06
  renderer.render(scene, camera)
  requestAnimationFrame(animate)
}
requestAnimationFrame(animate)
