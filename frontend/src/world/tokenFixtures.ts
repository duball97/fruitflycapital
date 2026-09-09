import { Vector3 } from 'three'
import type { TokenState } from './TokenHabitat'

export const MOCK_TOKEN_STATES: TokenState[] = [
  {
    id: 'TOKEN-A',
    label: 'ACTIVE / HEALTHY',
    activity: 0.88,
    liquidityDepth: 0.92,
    flowImbalance: 0.42,
    volatility: 0.18,
    socialActivity: 0.64,
    risk: 0.08,
    stableStructure: 0.92,
  },
  {
    id: 'TOKEN-B',
    label: 'QUIET / STABLE',
    activity: 0.18,
    liquidityDepth: 0.86,
    flowImbalance: 0.02,
    volatility: 0.06,
    socialActivity: 0.08,
    risk: 0.06,
    stableStructure: 0.96,
  },
  {
    id: 'TOKEN-C',
    label: 'ACTIVE / DANGEROUS',
    activity: 0.84,
    liquidityDepth: 0.22,
    flowImbalance: -0.25,
    volatility: 0.9,
    socialActivity: 0.72,
    risk: 0.9,
    stableStructure: 0.24,
  },
]

export const MOCK_HABITAT_POSITIONS = [
  new Vector3(-0.67, 0, -0.68),
  new Vector3(0.64, 0, -0.22),
  new Vector3(0.58, 0, 0.62),
]

export const MOCK_HABITAT_COLORS = [0x4bd6a0, 0x6ca8ff, 0xff6e80]
