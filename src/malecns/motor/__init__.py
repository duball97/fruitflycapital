"""MaleCNS motor/output population registries."""

from .registry import (
    descending_ids,
    forward_output_ids,
    stop_output_ids,
    turn_left_output_ids,
    turn_right_output_ids,
    walking_state_ids,
)
from .flight_decoder import FlightCommand, FlightDecodeResult, FlightMotorDecoder
from .flight_registry import flight_population_ids, flight_population_types

__all__ = [
    "descending_ids",
    "forward_output_ids",
    "stop_output_ids",
    "turn_left_output_ids",
    "turn_right_output_ids",
    "walking_state_ids",
    "FlightCommand",
    "FlightDecodeResult",
    "FlightMotorDecoder",
    "flight_population_ids",
    "flight_population_types",
]
