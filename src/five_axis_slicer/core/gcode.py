from __future__ import annotations

from pathlib import Path

from . import legacy_engine
from .settings import SliceDirection
from .slicer import SliceResult


"""G-code export helpers.

The slicer stores calculated paths as Shapely and Trimesh objects. This module
keeps file export behind two small functions so GUI code, scripts, and
future CLI commands do not need to know the long positional argument lists of
the legacy writers.

    G-code 是打印机执行的命令文件。它会告诉打印机什么时候移动，移动到
    哪里，什么时候挤出材料，什么时候加热，什么时候结束打印。

    切片算法算出来的是“路径数据”。这个文件负责把路径数据交给旧写出函数，
    由旧写出函数把路径变成真正的 `.gcode` 文件。这样界面和自动化脚本只要
    调用这里的两个函数，不需要知道旧写出函数的很多参数顺序。
"""


def write_3_axis_gcode(path: str | Path, name: str, result: SliceResult) -> None:
    """Write a 3-axis :class:`SliceResult` to a ``.gcode`` file.

    `path` is the output file. `name` is written into the G-code header by the
    legacy writer. `result` carries the paths and the exact print settings used
    during slicing.
    """
    legacy_engine.write_3_axis_gcode(
        str(path),  # Legacy writer expects a plain string path.
        name,  # Human-readable model or job name for the G-code header.
        result.settings.to_legacy_list(),  # Positional settings contract.
        result.transform3d,  # Per-layer transforms.
        result.adhesion,  # Brim or adhesion paths.
        result.shells,  # Shell/perimeter paths.
        result.internal_infill,  # Sparse infill paths.
        result.solid_infill,  # Solid infill paths.
    )


def write_5_axis_gcode(
    path: str | Path,
    name: str,
    result: SliceResult,
    directions: list[SliceDirection],
) -> None:
    """Write a 5-axis result and its slice-plane directions to G-code.

    The direction list is passed explicitly because 5-axis export needs the
    original plane starts and angle pairs to emit rotary axis words.
    """
    legacy_engine.write_5_axis_gcode(
        str(path),  # Legacy writer expects a plain string path.
        name,  # Human-readable model or job name for the G-code header.
        result.settings.to_legacy_list(),  # Positional settings contract.
        [list(direction.start) for direction in directions],  # Plane points.
        [[direction.theta, direction.phi] for direction in directions],  # Angles.
        result.transform3d,  # Per-chunk or per-layer transforms.
        result.adhesion,  # Brim or adhesion paths.
        result.shells,  # Shell/perimeter paths.
        result.internal_infill,  # Sparse infill paths.
        result.solid_infill,  # Solid infill paths.
    )
