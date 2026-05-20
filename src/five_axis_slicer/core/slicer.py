from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import trimesh

from . import legacy_engine
from .settings import PrintSettings, SlicingPlan


@dataclass(slots=True)
class SliceResult:
    mode: str
    settings: PrintSettings
    transform3d: object
    adhesion: object
    shells: object
    internal_infill: object
    solid_infill: object


def _mesh_data(meshes: Iterable[trimesh.Trimesh]) -> list[object]:
    mesh_list = list(meshes)
    return [list(range(len(mesh_list))), dict(enumerate(mesh_list))]


def slice_meshes_3_axis(
    meshes: Iterable[trimesh.Trimesh],
    settings: PrintSettings | None = None,
    workers: int | None = None,
) -> SliceResult:
    settings = settings or PrintSettings()
    if workers is not None:
        legacy_engine.workerBees = workers

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
    settings = settings or PrintSettings()
    if workers is not None:
        legacy_engine.workerBees = workers

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
