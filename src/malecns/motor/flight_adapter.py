"""MaleCNS readout to Flybody low-level flight boundary.

The adapter intentionally knows nothing about habitats, markets, or target
positions.  MaleCNS supplies only neural readouts; the low-level side keeps a
continuous wingbeat/cruise state and applies the bounded steering modulation.
When the upstream Flybody checkpoint is available, this same boundary is the
place where its native joint-action policy can replace the browser-compatible
cruise primitive.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LowLevelFlightCommand:
    """Bounded motor-level command, independent of world semantics."""

    forward_thrust: float
    vertical_thrust: float
    yaw: float
    pitch: float
    roll: float
    wingbeat_frequency_hz: float

    def as_dict(self) -> dict[str, float]:
        return {
            "forwardThrust": self.forward_thrust,
            "verticalThrust": self.vertical_thrust,
            "yawTorque": self.yaw,
            "pitchTorque": self.pitch,
            "rollTorque": self.roll,
            "wingbeatFrequencyHz": self.wingbeat_frequency_hz,
        }


class MaleCNSFlightAdapter:
    """Adapt neural readouts to a stable Flybody flight primitive.

    The upstream WPG continuously generates the wingbeat.  Until its trained
    checkpoint is installed in the optional MuJoCo worker, the browser's body
    uses this equivalent bounded motor boundary: a small cruise drive keeps an
    active fly airborne, while all directional changes still come from the
    neural readouts.  This is a low-level execution primitive, not navigation.
    """

    def __init__(
        self,
        *,
        base_cruise_thrust: float = 0.16,
        neural_thrust_gain: float = 0.68,
        base_wingbeat_hz: float = 218.0,
    ) -> None:
        self.base_cruise_thrust = _clip01(base_cruise_thrust)
        self.neural_thrust_gain = _clip01(neural_thrust_gain)
        self.base_wingbeat_hz = max(1.0, float(base_wingbeat_hz))

    def adapt(
        self,
        *,
        thrust: float,
        yaw: float,
        pitch: float,
        roll: float,
        active_rate_hz: float,
    ) -> LowLevelFlightCommand:
        """Return only motor-level output from bounded neural readouts."""

        neural_thrust = _clip01(thrust)
        neural_yaw = _clip_signed(yaw)
        neural_pitch = _clip_signed(pitch)
        neural_roll = _clip_signed(roll)
        has_neural_activity = max(float(active_rate_hz), neural_thrust, abs(neural_yaw), abs(neural_pitch), abs(neural_roll)) > 0.0
        cruise = self.base_cruise_thrust if has_neural_activity else 0.0
        return LowLevelFlightCommand(
            forward_thrust=_clip01(cruise + neural_thrust * self.neural_thrust_gain),
            vertical_thrust=0.5,
            yaw=_clip_signed(neural_yaw * 0.6),
            pitch=_clip_signed(neural_pitch * 0.45),
            roll=_clip_signed(neural_roll * 0.45),
            wingbeat_frequency_hz=self.base_wingbeat_hz,
        )


def _clip01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _clip_signed(value: float) -> float:
    return min(1.0, max(-1.0, float(value)))
