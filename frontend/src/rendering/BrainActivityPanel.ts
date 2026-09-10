import type { FlyAgent } from '../fly/FlyAgent'
import { isLiveBrainSource, type BrainActivity, type MaleCNSSensoryStimulation } from '../networking/protocol'

/**
 * Small, intentionally explicit interpretability panel for the selected fly.
 * It does not infer a causal relationship from motion: the source badge and
 * the recorded spike/DN window come directly from the brain socket payload.
 */
export class BrainActivityPanel {
  readonly element: HTMLDivElement
  private readonly sourceBadge: HTMLSpanElement
  private readonly agentLabel: HTMLSpanElement
  private readonly inputBar: HTMLSpanElement
  private readonly spikeBar: HTMLSpanElement
  private readonly dnBar: HTMLSpanElement
  private readonly commandBar: HTMLSpanElement
  private readonly stats: HTMLDivElement
  private readonly raster: HTMLDivElement
  private lastSampleAt = Number.NEGATIVE_INFINITY
  private lastFlyId = ''
  private readonly history = new Map<string, number[]>()

  constructor(uiRoot: HTMLElement) {
    this.element = document.createElement('div')
    this.element.className = 'brain-activity-panel debug-only'
    this.element.innerHTML = `
      <div class="brain-panel-heading"><strong>NEURAL TRACE</strong><span class="brain-source"></span></div>
      <div class="brain-panel-agent"></div>
      <div class="brain-flow-row"><span>INPUT</span><i class="brain-flow-track"><b class="brain-input-bar"></b></i><span>SPIKES</span><i class="brain-flow-track"><b class="brain-spike-bar"></b></i></div>
      <div class="brain-flow-row"><span>DN</span><i class="brain-flow-track"><b class="brain-dn-bar"></b></i><span>COMMAND</span><i class="brain-flow-track"><b class="brain-command-bar"></b></i></div>
      <div class="brain-raster" aria-label="Recent neural activity"></div>
      <div class="brain-panel-stats"></div>
    `
    uiRoot.append(this.element)
    this.sourceBadge = this.element.querySelector<HTMLSpanElement>('.brain-source')!
    this.agentLabel = this.element.querySelector<HTMLSpanElement>('.brain-panel-agent')!
    this.inputBar = this.element.querySelector<HTMLSpanElement>('.brain-input-bar')!
    this.spikeBar = this.element.querySelector<HTMLSpanElement>('.brain-spike-bar')!
    this.dnBar = this.element.querySelector<HTMLSpanElement>('.brain-dn-bar')!
    this.commandBar = this.element.querySelector<HTMLSpanElement>('.brain-command-bar')!
    this.stats = this.element.querySelector<HTMLDivElement>('.brain-panel-stats')!
    this.raster = this.element.querySelector<HTMLDivElement>('.brain-raster')!
  }

  update(agent: FlyAgent, activity: BrainActivity | null, stimulation: MaleCNSSensoryStimulation | null, elapsedSeconds: number) {
    if (elapsedSeconds - this.lastSampleAt < 0.1 && agent.id === this.lastFlyId) return
    this.lastSampleAt = elapsedSeconds
    this.lastFlyId = agent.id

    const visualInput = stimulation ? Math.min(1, stimulation.visual.length / 100) : 0
    const odorInput = stimulation ? Math.min(1, stimulation.olfactory.length / 250) : 0
    const input = Math.max(visualInput, odorInput)
    const spikes = activity ? Object.values(activity.spikeCounts).reduce((sum, count) => sum + Math.max(0, count), 0) : 0
    const spikeLevel = Math.min(1, spikes / 24)
    const dnPeak = activity ? Math.max(0, ...Object.values(activity.descendingRates)) : 0
    const dnLevel = Math.min(1, dnPeak / 80)
    const live = isLiveBrainSource(activity?.source)
    const neuralCommand = live ? activity?.flightCommand : undefined
    const actuatorCommand = agent.actuators.get()
    const commandLevel = Math.min(1, Math.max(
      actuatorCommand.forwardThrust,
      Math.abs(actuatorCommand.yawTorque),
      Math.abs(actuatorCommand.pitchTorque),
      Math.abs(actuatorCommand.rollTorque),
    ))
    this.sourceBadge.textContent = live
      ? 'LIVE BRIAN2 → DECODER'
      : activity
        ? 'DECODER OUTPUT · NO LIVE BRAIN'
        : 'WAITING FOR BRAIN OUTPUT'
    this.sourceBadge.dataset.state = live ? 'live' : 'waiting'
    this.agentLabel.textContent = `${agent.id} · ${agent.mode.toUpperCase()} · ${live ? 'measured neural window' : 'interpretation unavailable'}`
    setBar(this.inputBar, input)
    setBar(this.spikeBar, spikeLevel)
    setBar(this.dnBar, dnLevel)
    setBar(this.commandBar, commandLevel)

    const samples = this.history.get(agent.id) ?? []
    samples.push(spikeLevel)
    if (samples.length > 28) samples.shift()
    this.history.set(agent.id, samples)
    this.raster.replaceChildren(...samples.map((value) => {
      const cell = document.createElement('i')
      cell.style.height = `${Math.max(10, Math.round(value * 100))}%`
      cell.dataset.level = value > 0.02 ? 'active' : 'quiet'
      return cell
    }))
    const neuralLevel = neuralCommand
      ? Math.min(1, Math.max(neuralCommand.thrust, Math.abs(neuralCommand.yaw), Math.abs(neuralCommand.pitch), Math.abs(neuralCommand.roll)))
      : 0
    this.stats.textContent = `SPIKES ${spikes} · DN PEAK ${dnPeak.toFixed(2)} Hz · BRAIN CMD ${neuralLevel.toFixed(2)} · ACTUATOR ${commandLevel.toFixed(2)} · INPUT ${input.toFixed(2)}`
  }
}

function setBar(element: HTMLSpanElement, value: number) {
  element.style.transform = `scaleX(${Math.max(0.02, Math.min(1, value))})`
  element.dataset.active = value > 0.02 ? 'true' : 'false'
}
