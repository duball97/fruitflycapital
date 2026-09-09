import { Vector3 } from 'three'

/**
 * Sixteen is the next interactive pilot target. A larger value can be selected
 * explicitly with VITE_SWARM_SIZE after benchmarking the per-fly brain
 * scheduler; the UI caps this experiment at 100 agents.
 */
const configuredSize = Number(import.meta.env.VITE_SWARM_SIZE)
export const SWARM_SIZE = Number.isInteger(configuredSize) && configuredSize >= 1 && configuredSize <= 100
  ? configuredSize
  : 16

/**
 * Shared initial condition. The small deterministic offsets stop the bodies
 * from spawning on top of one another while keeping the swarm visibly far
 * from the coin piles.
 */
export const SWARM_LAUNCH_CENTER = new Vector3(0, 0.66, 0.84)

export function swarmFlyId(index: number) {
  return `fly-${String(index + 1).padStart(3, '0')}`
}

export function swarmSpawnPosition(index: number) {
  const angle = index * 2.399963229728653
  const radius = 0.1 + (index % 5) * 0.025
  return new Vector3(
    SWARM_LAUNCH_CENTER.x + Math.cos(angle) * radius,
    SWARM_LAUNCH_CENTER.y + ((index % 7) - 3) * 0.012,
    SWARM_LAUNCH_CENTER.z + Math.sin(angle) * radius,
  )
}
