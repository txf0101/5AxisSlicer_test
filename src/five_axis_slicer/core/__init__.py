"""Public imports for the slicer core package.

给新开发者看的说明：
    `core` 目录保存“切片器真正做计算的部分”。界面可以变化，按钮图片可以
    变化，但核心层需要稳定，因为它决定 STL 怎样变成路径、路径怎样变成
    G-code。

    本文件把核心层最常用、最应该被外部调用的名字集中导出。这样其他代码
    可以写：

        from five_axis_slicer.core import PrintSettings, slice_meshes_3_axis

    调用者就不需要知道这些对象分别来自 `settings.py` 还是 `slicer.py`。

维护提示：
    新增公开核心能力时，先确认它是稳定接口，再加入 `__all__`。临时函数、
    试验函数、只服务某个算法内部的函数应留在原模块里，避免外部代码过早
    依赖不稳定细节。
"""

from .settings import PrintSettings, SliceDirection, SlicingPlan
from .slicer import SliceResult, slice_meshes_3_axis, slice_meshes_5_axis

__all__ = [
    "PrintSettings",
    "SliceDirection",
    "SlicingPlan",
    "SliceResult",
    "slice_meshes_3_axis",
    "slice_meshes_5_axis",
]
