from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import trimesh

from . import legacy_engine
from .settings import PrintSettings, SlicingPlan


"""Public slicing API used by tests, scripts, and future non-GUI callers.

The heavy geometric work still lives in :mod:`legacy_engine`. This file is a
small boundary layer with two purposes:

* accept ordinary ``trimesh.Trimesh`` objects and typed settings;
* keep the legacy return structure wrapped in a named result object.

Keep new callers pointed at this module. Direct calls into ``legacy_engine.py``
should remain localized, because that file preserves a reference algorithm and
contains many positional data contracts.

给不熟悉代码的人看的说明：
    这个文件可以理解为“切片功能的前台服务窗口”。外部脚本或测试只需要把
    模型和参数交给这里，不需要直接接触复杂的几何算法文件。

    三轴切片入口是 `slice_meshes_3_axis()`。它适合普通逐层打印。
    五轴切片入口是 `slice_meshes_5_axis()`。它需要额外的 `SlicingPlan`
    来说明模型要按哪些方向切分。

    这两个函数最后都会返回 `SliceResult`。`SliceResult` 里面保存后续预览
    和保存 G-code 所需的所有路径数据。
"""


@dataclass(slots=True)
class SliceResult:
    """Toolpath data returned by one slicing run.

    The fields are intentionally close to the legacy return values because the
    G-code writer and preview renderer both expect these structures.
    """

    mode: str  # Which workflow produced this result: "3_axis" or "5_axis".
    settings: PrintSettings  # The exact print settings used for this result.
    transform3d: object  # Matrices that map 2D layer paths back into 3D space.
    adhesion: object  # Brim or other first-layer bed-adhesion paths.
    shells: object  # Outer and inner wall paths of the printed part.
    internal_infill: object  # Sparse internal fill paths inside the walls.
    solid_infill: object  # Dense fill paths for top, bottom, and exposed areas.


def _mesh_data(meshes: Iterable[trimesh.Trimesh]) -> list[object]:
    """Convert meshes into the ``[indices, mesh_dict]`` legacy shape.

    The legacy functions were originally driven by GUI-selected files. They
    expect a list of numeric selection indices and a dictionary from index to
    mesh object. This helper isolates that format so external code can pass a
    normal Python iterable.
    """
    mesh_list = list(meshes)
    selected_indices = list(range(len(mesh_list)))
    indexed_meshes = dict(enumerate(mesh_list))
    return [selected_indices, indexed_meshes]


def slice_meshes_3_axis(
    meshes: Iterable[trimesh.Trimesh],
    settings: PrintSettings | None = None,
    workers: int | None = None,
) -> SliceResult:
    """Slice meshes with ordinary vertical layers.

    Parameters
    ----------
    meshes:
        Trimesh objects already loaded by the caller.
    settings:
        Optional named print settings. Defaults mirror the current GUI.
    workers:
        Optional override for the legacy module's polygon worker count. Tests
        pass ``1`` to keep results deterministic and resource use small.
    """
    settings = settings or PrintSettings()
    if workers is not None:
        # The legacy engine reads a module-level worker count when it launches
        # parallel polygon jobs.
        legacy_engine.workerBees = workers

    # The legacy routine returns five parallel structures. Keep this unpacking
    # visible so future maintainers can track which output feeds preview and
    # which output feeds the G-code writer.
    transform3d, adhesion, shells, internal, solid = legacy_engine.slice_in_3_axes(
        settings.to_legacy_list(),
        _mesh_data(meshes),
    )

    return SliceResult(
        mode="3_axis",
        settings=settings,
        transform3d=transform3d,
        adhesion=adhesion,
        shells=shells,
        internal_infill=internal,
        solid_infill=solid,
    )


def slice_meshes_5_axis(
    meshes: Iterable[trimesh.Trimesh],
    plan: SlicingPlan,
    settings: PrintSettings | None = None,
    workers: int | None = None,
) -> SliceResult:
    """Slice meshes with an ordered 5-axis slicing plan.

    简单理解：
        先按照用户定义的方向把模型分成几个区域，再让每个区域按自己的方向
        生成层和路径。这样可以支持五轴打印中的多方向成形。
    """
    settings = settings or PrintSettings()
    if workers is not None:
        legacy_engine.workerBees = workers

    # `plan.to_legacy_list()` preserves direction order because the 5-axis
    # engine uses that order to split and orient mesh chunks.
    transform3d, adhesion, shells, internal, solid = legacy_engine.slice_in_5_axes(
        settings.to_legacy_list(),
        _mesh_data(meshes),
        plan.to_legacy_list(),
    )

    return SliceResult(
        mode="5_axis",
        settings=settings,
        transform3d=transform3d,
        adhesion=adhesion,
        shells=shells,
        internal_infill=internal,
        solid_infill=solid,
    )
