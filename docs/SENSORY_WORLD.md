# Embodied sensory world

This document separates observations available to the virtual fly from the
software encodings used to send observations to the MaleCNS adapter.

## World-to-sensor observations

| Channel | Implementation | What reaches the brain | Status |
|---|---|---|---|
| Left/right vision | 5 azimuth x 2 elevation rays per eye (20 samples total), cast against the Three.js environment | Per sample: body-relative direction, azimuth, elevation, luminance, contrast, optic-flow proxy, object angular size | Implemented |
| Odor | Gaussian diffusion-like fields around the three synthetic token habitats; left/right antenna samples are offset from the body | Center concentration, left/right antenna concentration, temporal change | Implemented as synthetic world input |
| Body motion | Body angular velocity and translational velocity transformed into the body frame | Angular velocity, body-frame velocity, speed, gravity alignment | Implemented as feedback; not mapped to CNS by default |
| Wind | No airflow solver or wind field | `windImplemented=false`, null direction, zero speed | Explicitly unimplemented |
| Contact | Body bounds and floor contact state | Ground and wall booleans; obstacle is always false in the minimal arena | Implemented as feedback; not mapped to CNS by default |

The fly does not send the food/pile position, obstacle coordinates, target position,
or world-space target vectors to the Python process. World coordinates are used
inside the local sensor implementation only to calculate physical observations.

## Synthetic token habitats

The current NeuroSwarm milestone contains three local `TokenHabitat` coin-pile objects,
not a token API or a financial data feed. Their mock states are:

| Habitat | Mock state | Physical fields exposed to the fly |
|---|---|---|
| TOKEN-A | ACTIVE / HEALTHY | brightness, canonical Flybody swarm motion, attractive odor, low danger |
| TOKEN-B | QUIET / STABLE | lower motion/brightness, attractive odor, low danger |
| TOKEN-C | ACTIVE / DANGEROUS | high motion/chaos, attractive odor, aversive danger |

Scenario `A · OFF` sets the synthetic habitat sensory fields to neutral;
`B · DIFFERENT` uses the default state/site assignment; `C · SWAPPED` rotates
the state/site assignment. These fields are deliberately a local synthetic
stimulus layer. They are not real tokens, prices, balances, wallet data, or
social-network data.

Each coin pile displays two canonical Flybody swarm members. They begin in a
shared distant launch zone and use the synthetic attraction, activity, and
danger parameters to determine how far they approach their associated pile.
This is a visual swarm demonstration, not six additional MaleCNS simulations;
only the two foreground flies have independent CNS agent IDs.

Attractive odor is sampled by the existing odor channel and encoded to the
documented `ORN_DA1` population. Aversive danger is currently visible in the
debug sensor frame but is not mapped into MaleCNS: the adapter reports
`aversive_odor_to_maleCNS` as unimplemented. This avoids inventing an aversive
olfactory population from a desired behavior.

## Vision approximation

The eyes are not thousands of cameras. Each eye has a fixed 10-ray angular
sampling lattice covering a broad forward field. A ray hit samples the first
visible Three.js mesh. Luminance is derived from the mesh material color;
contrast is distance from a fixed dark ambient reference. Object angular size
uses the hit mesh bounding sphere. Optic flow is an approximation from
tangential body velocity, hit distance, and body angular velocity. It is a
reference sensor representation, not a photoreceptor or lamina model.

## MaleCNS encoding

`src/malecns/brain/sensory_encoding.py` loads the exact IDs from
`data/mappings/malecns_sensory_motor_ids.csv`:

- visual mean luminance → exact `R8d` left/right IDs
- odor concentration → exact `ORN_DA1` IDs
- mechanosensory stimulation → empty by default
- optic flow → observed in the frame but not equated with a visual rate
  population

The scalar-to-rate conversion `rate_hz = 150 * bounded_signal` is an
`OUR_ASSUMPTION` encoder, while the IDs and population labels are
`MALECNS_DATA`. No new CNS edge is created, no connection weight is modified,
and no neuron is selected by trial-and-error activity.

Wind, gravity, contact, optic flow, and aversive odor are returned in the
sensory frame but are reported as unimplemented MaleCNS mappings. The debug
panel shows those channels and the encoded body-ID counts returned by the
Python WebSocket adapter.
