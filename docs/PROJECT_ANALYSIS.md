# 5AxisSlicer_test V1.0 工程解析

## 1. 阅读依据

本文依据当前仓库内的文件整理，主要包括：

| 类型 | 文件 |
| --- | --- |
| 项目说明 | `README.md` |
| 依赖与命令入口 | `pyproject.toml`、`requirements.txt`、`run_app.ps1` |
| 应用入口 | `src/five_axis_slicer/app.py`、`src/five_axis_slicer/__main__.py` |
| 界面层 | `src/five_axis_slicer/ui/window.py`、`src/five_axis_slicer/ui/controller.py`、`src/five_axis_slicer/ui/widgets.py` |
| 切片核心 | `src/five_axis_slicer/core/settings.py`、`src/five_axis_slicer/core/slicer.py`、`src/five_axis_slicer/core/legacy_engine.py`、`src/five_axis_slicer/core/gcode.py` |
| 示例输出 | `example/pipe/pipe_fitting.gcode` |

## 2. 项目定位

本工程是 Fractal Cortex 五轴 FDM 切片流程的 Python 复刻版，当前仓库名和版本在 `README.md` 与 `pyproject.toml` 中分别标明为 `5AxisSlicer_test V1.0` 与 `1.0.0`。工程目标集中在三个方面：提供一个可操作的 Pyglet/Glooey 桌面界面，复用并封装原有三轴与五轴切片算法，将切片结果导出为 G-code 供后续比对与备份。

项目采用 `src` 布局，核心包名为 `five_axis_slicer`。从依赖文件可以看到，它依赖 `trimesh` 处理 STL 网格，依赖 `shapely` 做二维多边形运算，依赖 `manifold3d` 支持 Trimesh 的布尔运算，依赖 `pyglet`、`glooey` 与 `PyOpenGL` 构建图形界面和三维预览。

## 3. 启动路径

应用入口很短，便于定位。`src/five_axis_slicer/app.py` 从 `ui.window` 导入 `main()` 并执行。`src/five_axis_slicer/__main__.py` 允许使用 `python -m five_axis_slicer` 启动。`pyproject.toml` 中的脚本入口 `five-axis-slicer = "five_axis_slicer.app:main"` 说明该项目安装成包后也可以通过命令行脚本启动。

在日常使用中，仓库提供了 `run_app.ps1` 启动 GUI。README 中提示使用现有 Conda 环境 `5AxisSlicer`，并要求安装 `requirements.txt` 中的依赖。

## 4. 目录结构

`src/five_axis_slicer/core` 是切片核心层。这里的 `settings.py` 定义打印参数和五轴切片平面，`slicer.py` 提供较清晰的三轴和五轴切片入口，`legacy_engine.py` 承载主要几何算法，`gcode.py` 负责把切片结果交给 G-code 写出函数。

`src/five_axis_slicer/ui` 是界面层。`window.py` 负责 Pyglet 窗口、OpenGL 渲染、STL 载入、预览绘制和后台计算调度。`controller.py` 负责界面控件实例、页签切换、语言切换、切片按钮、参数读取和保存 G-code。`widgets.py` 封装按钮、单选框、复选框、输入框等常用控件。

`src/five_axis_slicer/assets` 保存字体和由脚本生成的按钮图片。`tools` 保存界面资源维护脚本。`example/pipe/pipe_fitting.gcode` 是当前本地生成并纳入版本管理的管件 G-code 输出。

## 5. 界面层工作方式

GUI 由 `ui.window.Graphics_Window` 创建。窗口左侧是三维视口，右侧是打印设置区。用户载入 STL 后，`Render_Model.load_stl()` 使用 Trimesh 读取模型，并把顶点、法向量、索引上传为 OpenGL VBO。窗口循环在 `on_draw()` 中绘制构建圆盘、模型、切片平面和预览路径。

切片计算通过 `CalculationWorker` 放入线程池。这样界面仍能继续刷新，计算完成后 `check_calculation_results()` 从结果队列取回 Future，再调用回调更新按钮状态和切片状态文本。

右侧设置区使用多个 `glooey.Deck` 叠放同一行的不同页签内容。页签包括材料、强度、精度、喷头运动、支撑和附着。`controller.py` 中的 `set_settings_deck_states()` 负责把每一行切到当前页签状态，`apply_settings_language()` 负责把当前语言的文字写回控件。

## 6. 右下角几个框和勾选项的含义

截图里右下角圈出的控件属于 `喷头运动` 页签，代码依据在 `src/five_axis_slicer/ui/controller.py` 的 `r4c0SettingsDeck` 到 `r7c1SettingsDeck`，参数读取依据在 `update_values()`。这些控件依次表示：

| 中文界面名称 | 变量 | 用途 |
| --- | --- | --- |
| 空驶抬 Z（避开模型） | `enableZHop` | 空驶移动前抬高喷嘴，减少喷嘴擦碰已打印区域的风险 |
| 启用回抽（减少拉丝） | `enableRetraction` | 空驶前回抽耗材，减少拉丝 |
| 回抽距离 | `retractionDistance` | 每次回抽的耗材长度，单位为 mm |
| 回抽速度 | `retractionSpeed` | 回抽时的挤出轴速度，单位为 mm/s |

这些值会进入 `printSettings` 列表，并在 `legacy_engine.write_3_axis_gcode()` 与 `legacy_engine.write_5_axis_gcode()` 写出移动和挤出命令时使用。截图中它们显示在“材料”页签下方，造成了语义不清。本次修改新增 `set_movement_detail_visibility()`，将这些喷头运动参数收回到“喷头运动”页签里显示，同时把页签名从“运动”改为“喷头运动”，并增加一行说明文字：回抽距离和速度只在启用回抽后生效。

## 7. 切片参数的数据流

界面参数先以控件状态存在于 `controller.py`。用户点击切片后，`slice_function()` 调用 `update_values()` 读取温度、填充、层高、速度、Z hop、回抽、支撑和边裙等值，组装成 `printSettings` 列表。该列表按固定顺序传入 `slice_in_3_axes()` 或 `slice_in_5_axes()`。

核心层也提供了更易读的参数对象。`core/settings.py` 中的 `PrintSettings` 使用命名字段保存相同参数，`to_legacy_list()` 负责转换成 legacy 算法需要的位置列表。`SliceDirection` 表示一个五轴切片平面，包含平面上的起点和法向角度。`SlicingPlan` 则把多个切片方向合并成 `[count, starts, angle_pairs]` 结构。

## 8. 三轴切片流程

三轴入口在 `legacy_engine.slice_in_3_axes()`。流程可以概括为：

1. 读取一个或多个 STL 网格，多个模型时先用 Trimesh 合并。
2. 根据模型 Z 方向边界和层高生成 `slice_levels`。
3. `all_calculations()` 对每一层取截面，得到二维路径。
4. Shapely 多边形用于生成外壳偏置、内部填充区域和实心填充区域。
5. 如果启用边裙，初始层会通过 `create_brim()` 生成附着路径。
6. 返回变换矩阵、边裙、外壳、内部填充和实心填充，供预览和 G-code 导出使用。

三轴切片始终沿构建平台法向切层，适合普通平面逐层 FDM 打印。

## 9. 五轴切片流程

五轴入口在 `legacy_engine.slice_in_5_axes()`，主要计算在 `all_5_axis_calculations()`。它先把用户给定的切片方向转换为平面法向，然后用 `mesh.slice_plane()` 和布尔差集把模型拆成多个 chunk。每个 chunk 对应一个打印方向。

每个 chunk 会在自己的方向上生成局部层高，再对该 chunk 执行类似三轴的截面、外壳、填充和边裙计算。由于 chunk 的方向可能倾斜，代码会保留每层的 `to_3D` 变换矩阵，后续预览和写 G-code 时再把二维路径映射回三维空间。

五轴流程还包含喷嘴与热床间隙检查。`checkForBedNozzleCollisions()` 会把路径点变回三维坐标，通过切片方向角度估算喷嘴到热床的距离。如果发现小于阈值的危险位置，切片会停止并输出碰撞提示。

## 10. G-code 导出

G-code 写出函数位于 `core/legacy_engine.py`，对外封装位于 `core/gcode.py`。三轴导出调用 `write_3_axis_gcode()`，五轴导出调用 `write_5_axis_gcode()`。五轴导出除了 X、Y、z 和 E 轴以外，还会根据切片方向把两组联动旋转轴直接写进运动指令。界面中的“联动轴 1 符号”和“联动轴 2 符号”默认是 `A` 与 `B`，导出格式类似 `G1 F600 X0 Y0 z10 A90 B75 E0.1`；如果用户改成 `C` 与 `D`，则输出为 `C` 与 `D` 两个轴字。该格式参考 `Open5X/example/EXAMPLE.gcode` 中的五轴联动写法。

写出逻辑会参考 `enableZHop` 和 `enableRetraction`。开启回抽时，路径开始前会写入回抽命令，随后在需要挤出时恢复。开启 Z hop 时，空驶移动前会先抬高 Z。边裙、外壳、内部填充和实心填充按计算结果依次写出。

## 11. 示例与复刻比对

`example/pipe/pipe_fitting.gcode` 是当前本地保留的管件切片输出。README 中记录了管件参考切片方向：初始方向为原点和竖直方向，第二方向为 `X=20, Y=0, Z=60, theta=75, phi=0`，第三方向为 `X=-20, Y=0, Z=105, theta=45, phi=-120`。这些参数用于复刻官方示例中的分块打印姿态。

如果切片时出现 `No boolean backend`，说明 Trimesh 需要布尔后端。当前依赖中已经加入 `manifold3d==3.4.1`。如果出现 `unable to recover polygon!`，通常与某一层截面形成的多边形难以恢复有关，排查方向包括切片平面是否擦过模型复杂边界、模型是否水密、层高是否过小、布尔后端和几何库版本是否与当前仓库一致。

## 12. 已知状态与后续维护重点

`supports` 页签文字标注为“启用支撑（待实现）”，说明支撑生成当前仍属于预留功能。附着页签的边裙已经接入 `enableBrim`。喷头运动参数已改为只在“喷头运动”页签显示，减少在其他页签下出现无标签框和勾选框的情况。

后续维护建议优先关注四点。第一，继续把 `legacy_engine.py` 中的长函数拆出更小的纯函数，并用 `core/slicer.py` 暴露稳定入口。第二，为五轴切片保留小型 STL 的固定输入样例和输出样例，重点覆盖 chunk 数量、联动旋转轴和 G-code 头部参数。第三，给切片平面编辑区增加当前方向的可视化说明，避免 theta 与 phi 的输入含义混淆。第四，遇到 polygon 恢复问题时保留触发层号、切片方向和模型边界信息，便于复现。
