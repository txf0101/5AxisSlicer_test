from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class PrintSettings:
    nozzle_temp: float = 200.0
    initial_nozzle_temp: float = 205.0
    bed_temp: float = 60.0
    initial_bed_temp: float = 65.0
    infill_percentage: float = 20.0
    shell_thickness: int = 3
    layer_height: float = 0.3
    print_speed: float = 100.0
    initial_print_speed: float = 50.0
    travel_speed: float = 150.0
    initial_travel_speed: float = 100.0
    enable_z_hop: bool = True
    enable_retraction: bool = True
    retraction_distance: float = 1.0
    retraction_speed: float = 20.0
    enable_supports: bool = False
    enable_brim: bool = False

    def to_legacy_list(self) -> list[float | int | bool]:
        return [
            self.nozzle_temp,
            self.initial_nozzle_temp,
            self.bed_temp,
            self.initial_bed_temp,
            self.infill_percentage,
            self.shell_thickness,
            self.layer_height,
            self.print_speed,
            self.initial_print_speed,
            self.travel_speed,
            self.initial_travel_speed,
            self.enable_z_hop,
            self.enable_retraction,
            self.retraction_distance,
            self.retraction_speed,
            self.enable_supports,
            self.enable_brim,
        ]


@dataclass(slots=True)
class SliceDirection:
    start: tuple[float, float, float] = (0.0, 0.0, 0.0)
    theta: float = 0.0
    phi: float = 0.0


@dataclass(slots=True)
class SlicingPlan:
    directions: list[SliceDirection] = field(
        default_factory=lambda: [SliceDirection(), SliceDirection()]
    )

    def to_legacy_list(self) -> list[object]:
        return [
            len(self.directions),
            [list(direction.start) for direction in self.directions],
            [[direction.theta, direction.phi] for direction in self.directions],
        ]
