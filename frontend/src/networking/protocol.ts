import type { Quaternion, Vector3 } from 'three'

export type FlyMode = 'manual' | 'malecns' | 'preview' | 'off'

export interface EyeSample {
  direction: { x: number; y: number; z: number }
  azimuthRad: number
  elevationRad: number
  luminance: number
  contrast: number
  opticFlow: number
  objectAngularSizeRad: number
}

export interface EyeObservation {
  samples: EyeSample[]
  meanLuminance: number
  meanContrast: number
  meanOpticFlow: number
}

export interface OdorObservation {
  concentration: number
  leftAntenna: number
  rightAntenna: number
  aversiveConcentration: number
  temporalChange: number
  airflowImplemented: false
}

export interface MotionObservation {
  angularVelocity: { x: number; y: number; z: number }
  bodyVelocity: { x: number; y: number; z: number }
  translationalSpeed: number
  gravityAlignment: number
  windDirection: null
  windSpeed: 0
  windImplemented: false
}

export interface ContactObservation {
  ground: boolean
  obstacle: boolean
  wall: boolean
}

export interface ActuatorCommand {
  forwardThrust: number
  verticalThrust: number
  yawTorque: number
  pitchTorque: number
  rollTorque: number
}

export interface SensorFrame {
  leftEye: EyeObservation
  rightEye: EyeObservation
  odor: OdorObservation
  motion: MotionObservation
  contact: ContactObservation
  timestampMs: number
}

export interface StimulationEntry {
  bodyId: number
  rateHz: number
  population?: string
}

export interface MaleCNSSensoryStimulation {
  visual: StimulationEntry[]
  olfactory: StimulationEntry[]
  mechanosensory: StimulationEntry[]
  unimplemented: string[]
}

export interface FlightCommand {
  thrust: number
  yaw: number
  pitch: number
  roll: number
}

export interface BrainActivity {
  flightCommand: FlightCommand
  descendingRates: Record<string, number>
  spikeCounts: Record<string, number>
  source?: string
}

export interface BrainInputMessage {
  type: 'brain_input'
  flyId: string
  mode: FlyMode
  sensors: SensorFrame
  spikeRates?: Record<string, number>
  spikeCounts?: Record<string, number>
}

export interface BrainOutputMessage {
  type: 'brain_output'
  flyId: string
  commands: ActuatorCommand
  timestampMs: number
  source?: string
  stimulation?: MaleCNSSensoryStimulation
  flightCommand?: FlightCommand
  descendingRates?: Record<string, number>
  spikeCounts?: Record<string, number>
  spikeRates?: Record<string, number>
}

export interface EnvironmentUpdateMessage {
  type: 'environment_update'
  environment: {
    source: 'graph-uniswap'
    status: 'disabled' | 'ok' | 'error'
    observedAtMs: number
    habitats: Array<{
      id: string
      label: string
      physicalRadiusM: number
      resourcePileRadiusM: number
      visualMotionIntensity: number
      brightness: number
      particleActivity: number
      chaos: number
      attractiveOdor: number
      aversiveDanger: number
      signals?: Array<{
        name: string
        value: unknown
        normalized: number
        importance: number
        valence: number
        confidence: number
        freshness: number
        source: string
        observedAtMs: number
      }>
      provenance?: Array<Record<string, unknown>>
    }>
    rawMarketFieldsForwardedToFly: false
    error?: string
  }
}

export interface BrainHelloMessage {
  type: 'hello'
  protocol: 'male-cns-fly-world'
  version: 1
}

export type BrainMessage = BrainInputMessage | BrainOutputMessage | BrainHelloMessage | EnvironmentUpdateMessage

export function vectorToWire(vector: Vector3) {
  return { x: vector.x, y: vector.y, z: vector.z }
}

export function quaternionToWire(quaternion: Quaternion) {
  return { x: quaternion.x, y: quaternion.y, z: quaternion.z, w: quaternion.w }
}

export function isBrainOutputMessage(value: unknown): value is BrainOutputMessage {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<BrainOutputMessage>
  const commands = candidate.commands
  return (
    candidate.type === 'brain_output' &&
    typeof candidate.flyId === 'string' &&
    !!commands &&
    typeof commands.forwardThrust === 'number' &&
    typeof commands.verticalThrust === 'number' &&
    typeof commands.yawTorque === 'number' &&
    typeof commands.pitchTorque === 'number' &&
    typeof commands.rollTorque === 'number'
  )
}

export function isEnvironmentUpdateMessage(value: unknown): value is EnvironmentUpdateMessage {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<EnvironmentUpdateMessage>
  return candidate.type === 'environment_update' && !!candidate.environment && typeof candidate.environment === 'object'
}
