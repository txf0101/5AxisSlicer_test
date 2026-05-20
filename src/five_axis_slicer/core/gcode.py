from __future__ import annotations

from pathlib import Path

from . import legacy_engine
from .settings import SliceDirection
from .slicer import SliceResult


def write_3_axis_gcode(path: str | Path, name: str, result: SliceResult) -> None:
    legacy_engine.write_3_axis_gcode(
        str(path),
        name,
        result.settings.to_legacy_list(),
        result.transform3d,
        result.adhesion,
        result.shells,
        result.internal_infill,
        result.solid_infill,
    )


def write_5_axis_gcode(
    path: str | Path,
    name: str,
    result: SliceResult,
    directions: list[SliceDirection],
) -> None:
    legacy_engine.write_5_axis_gcode(
        str(path),
        name,
        result.settings.to_legacy_list(),
        [list(direction.start) for direction in directions],
        [[direction.theta, direction.phi] for direction in directions],
        result.transform3d,
        result.adhesion,
        result.shells,
        result.internal_infill,
        result.solid_infill,
    )
