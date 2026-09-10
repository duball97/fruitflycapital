# Flybody flight-control audit

## Decision

NeuroSwarm must keep navigation in the MaleCNS path. Flybody is the motor
execution layer: it may generate wing beats, stabilize the body, and convert a
bounded motor intent into joint actions, but it must never receive a token ID,
market score, habitat ranking, target coordinate, or portfolio state.

The repository currently has the reusable browser-side boundary in
`src/malecns/motor/flight_adapter.py`. It accepts only neural readouts and
emits a bounded low-level flight command. The optional MuJoCo backend accepts
Flybody's native actuator vector separately; it does not invent a mapping from
market data to joints.

## Upstream files inspected

| Upstream component | Finding |
| --- | --- |
| `flybody/fly_envs.py` | `flight_imitation` and `vision_guided_flight` each expose one user action. |
| `flybody/tasks/pattern_generators.py` | `WingBeatPatternGenerator` produces a continuous wing pattern. The defaults are 218 Hz, a +/-5% frequency range, 201 discrete frequencies, and six wing-joint outputs (three per wing). |
| `flybody/tasks/flight_imitation.py` | The single action is clipped to `[-1, 1]`, changes requested wingbeat frequency, and adds WPG position error to the six wing controls. It is not a target-navigation controller. |
| `flybody/tasks/vision_flight.py` | The vision task has the same one-dimensional wingbeat control boundary. Its vision/task observables are for the trained task policy and are not part of NeuroSwarm navigation. |
| `flybody/agents/network_factory_vis.py` | The two-level controller restores a separately downloaded low-level checkpoint. Its high-level network emits a seven-dimensional steering command; this vision policy must not choose NeuroSwarm habitat targets. |
| `flybody/download_data.py` | Checkpoints are downloaded separately from Janelia Figshare (`controller-reuse-checkpoints` or `trained-policies`). No pretrained checkpoint is included in this checkout. |

## What is installed here

- The canonical Flybody XML and OBJ meshes are vendored and used by the
  renderer.
- A TypeScript WingBeatPattern bridge preserves the upstream WPG control idea
  for visual wing motion.
- `MaleCNSFlightAdapter` is the explicit neural-readout-to-motor boundary.
- `MuJoCoFlybody` is an optional wrapper for the native actuator vector.
- The actual trained Flybody controller checkpoint and a running MuJoCo pose
  server are **not** installed. Therefore the current browser is not allowed
  to claim that it is running the pretrained RL policy.

The adapter is a continuous low-level cruise primitive, not a target-seeking
preview. Neural thrust and turn readouts determine its bounded modulation;
wingbeat generation and stabilization remain the low-level responsibility.
When the upstream checkpoint is installed, it can replace the low-level
implementation behind this same adapter boundary without changing the market
or CNS layers.

## Independence and performance plan

One immutable low-level policy can be shared by 16 CNS agents. The policy
weights are shared; each agent must retain independent CNS state, recurrent
state, random stream, WPG phase, and MuJoCo physics state. Sharing those state
objects would make agents appear identical.

The upstream constants use a MuJoCo physics timestep of approximately `5e-5`
seconds and a control timestep of approximately `2e-4` seconds. This checkout
has not benchmarked 1, 4, 8, and 16 full MuJoCo bodies, so no throughput claim
is made. The required benchmark order is 1 -> 4 -> 8 -> 16. If 16 full bodies
are too expensive, batch low-level inference, step physics at a lower control
frequency, or simulate 16 canonical bodies and attach render-only followers.

## Telemetry boundary

Telemetry is intentionally separate:

```text
MaleCNS readouts
  -> maleCnsCommand
  -> lowLevelFlightCommand
  -> flybodyJointAction (only when native Flybody physics is connected)
  -> physicalVelocity / physicalPosition
```

The first two stages are available in the realtime brain response. Native
joint and physical-pose fields remain optional until the MuJoCo worker is
connected; they must not be fabricated by the browser.

## Required validation experiment

Before calling the flight path biologically validated, record a fixed sensory
sequence and compare:

1. sensory frame and stimulated neuron IDs;
2. MaleCNS spikes and documented descending-neuron rates;
3. decoded CNS command;
4. low-level command and wingbeat phase;
5. native joint action, physical velocity, and position.

The decisive test is that changing the sensory stimulus changes the CNS
readout and consequently the motor output, while the low-level controller
never receives market semantics or a target coordinate.
