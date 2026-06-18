from __future__ import annotations

from dataclasses import dataclass, field


"""Typed settings used by the maintainable public slicing API.

The inherited Fractal Cortex routines in :mod:`legacy_engine` exchange most
settings as positional lists. Positional lists are compact, but they are hard to
review safely because a new field can shift every following index. This module
therefore exposes named dataclasses at the package boundary, then converts them
to the exact positional order expected by the legacy routines only at the last
possible moment.

Maintenance rule:
    When a new print option is added, add a named field here first, document its
    unit and UI meaning, then update :meth:`PrintSettings.to_legacy_list` and
    the matching index comments in ``legacy_engine.py`` together.

给不熟悉代码的人看的说明：
    这个文件保存“打印参数说明书”。界面上的温度、层高、速度、填充率等
    输入，最终都需要变成切片算法能理解的数据。这里用带名字的字段保存
    这些参数，让开发者一眼能看出每个数字表示什么。

    旧算法仍然要求一串按固定顺序排列的列表。`to_legacy_list()` 就负责把
    “有名字、容易理解的参数”转换成“旧算法要求的固定顺序”。因此这个文件
    是新代码和旧算法之间的重要翻译层。
"""


@dataclass(slots=True)
class PrintSettings:
    """All print parameters that become temperatures, speeds, shells, and flags.

    The defaults match the values shown in the current GUI. Units follow the
    slicer convention used throughout this project: Celsius for temperatures,
    millimeters for distances, and millimeters per second for speeds.
    """

    # Material temperatures. These values control heating commands in G-code.
    # The "initial" values are used for the first layer because the first layer
    # often needs slightly higher temperature to stick to the bed.
    nozzle_temp: float = 200.0
    initial_nozzle_temp: float = 205.0
    bed_temp: float = 60.0
    initial_bed_temp: float = 65.0

    # Strength and resolution. `shell_thickness` is a count of perimeter loops;
    # `layer_height` is the vertical distance between neighboring slice planes.
    infill_percentage: float = 20.0
    shell_thickness: int = 3
    layer_height: float = 0.3

    # Head movement. These speeds describe how fast the nozzle moves when it is
    # printing material and when it is only traveling between printed paths.
    print_speed: float = 100.0
    initial_print_speed: float = 50.0
    travel_speed: float = 150.0
    initial_travel_speed: float = 100.0

    # Travel-move quality options. Z hop raises the nozzle before a non-printing
    # move. Retraction pulls filament back before travel to reduce stringing.
    enable_z_hop: bool = True
    enable_retraction: bool = True
    retraction_distance: float = 1.0
    retraction_speed: float = 20.0

    # Feature flags. A flag is a true/false switch. Supports are currently a
    # reserved setting in the UI. Brim generation is already connected to the
    # legacy engine and creates extra first-layer lines around the part.
    enable_supports: bool = False
    enable_brim: bool = False

    # Inline G-code axis labels used by 5-axis motion export. Machines can name
    # rotary axes differently, so the user can choose the two letters written
    # beside rotary angles in the final G-code.
    linked_axis_a_symbol: str = "A"
    linked_axis_b_symbol: str = "B"

    def to_legacy_list(self) -> list[float | int | bool | str]:
        """Return settings in the positional order required by ``legacy_engine``.

        Keep this method deliberately explicit. The comments beside each item
        document the legacy index contract used by slicing and G-code writing.
        That makes index-related regressions easier to spot during review.
        """
        return [
            self.nozzle_temp,  # 0: normal nozzle temperature, deg C
            self.initial_nozzle_temp,  # 1: first-layer nozzle temperature, deg C
            self.bed_temp,  # 2: normal bed temperature, deg C
            self.initial_bed_temp,  # 3: first-layer bed temperature, deg C
            self.infill_percentage,  # 4: sparse infill density, percent
            self.shell_thickness,  # 5: perimeter loop count
            self.layer_height,  # 6: layer height, mm
            self.print_speed,  # 7: normal extrusion move speed, mm/s
            self.initial_print_speed,  # 8: first-layer extrusion speed, mm/s
            self.travel_speed,  # 9: normal non-extruding move speed, mm/s
            self.initial_travel_speed,  # 10: first-layer travel speed, mm/s
            self.enable_z_hop,  # 11: lift nozzle during travel moves
            self.enable_retraction,  # 12: retract filament before travel moves
            self.retraction_distance,  # 13: filament retraction length, mm
            self.retraction_speed,  # 14: filament retraction speed, mm/s
            self.enable_supports,  # 15: reserved support-generation flag
            self.enable_brim,  # 16: generate brim paths on the first layer
            self.linked_axis_a_symbol,  # 17: first rotary G-code axis word
            self.linked_axis_b_symbol,  # 18: second rotary G-code axis word
        ]


@dataclass(slots=True)
class SliceDirection:
    """One 5-axis slice plane.

    `start` is a point on the plane. `theta` and `phi` describe the plane
    normal with the same spherical-angle convention used by the GUI. Values are
    stored as plain tuples and floats so they remain easy to serialize in tests
    or future command-line tools.
    """

    # A point on the slicing plane. In the GUI, these are the X/Y/Z fields in
    # the slicing direction editor.
    start: tuple[float, float, float] = (0.0, 0.0, 0.0)
    # Direction angles for the slicing plane. In the GUI, these are theta and
    # phi. The legacy engine converts them into a normal vector.
    theta: float = 0.0
    phi: float = 0.0


@dataclass(slots=True)
class SlicingPlan:
    """A complete ordered list of slice planes for 5-axis slicing.

    The order matters. The legacy 5-axis routine uses it to split the mesh into
    chunks and then calculate each chunk under its local build direction.
    """

    # The full list of slice directions. Two default directions match the 5-axis
    # editor's starter state, where the first direction is the base direction and
    # the user can define an additional direction.
    directions: list[SliceDirection] = field(
        default_factory=lambda: [SliceDirection(), SliceDirection()]
    )

    def to_legacy_list(self) -> list[object]:
        """Return ``[count, starts, angle_pairs]`` for the legacy 5-axis code."""
        return [
            len(self.directions),  # Number of user-defined slicing directions.
            [list(direction.start) for direction in self.directions],  # Plane points.
            [[direction.theta, direction.phi] for direction in self.directions],  # Plane angles.
        ]
