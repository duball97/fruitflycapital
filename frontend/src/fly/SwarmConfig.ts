import { Vector3 } from 'three'

/**
 * The first population experiment is intentionally small. Every entry below
 * is a real FlyAgent; scale beyond this only after independence is verified.
 */
export const SWARM_SIZE = 8

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
