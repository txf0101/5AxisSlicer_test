# 5AxisSlicer 中文入门导览

本文面向刚接触本项目、暂时不熟悉代码的人。内容依据当前仓库中的 `README.md`、`pyproject.toml`、`src/five_axis_slicer`、`tools`、`example/pipe` 和 `docs/MAINTAINER_GUIDE.md` 编写。

## 这个项目解决什么问题

本项目维护一个五轴 FDM 切片器。用户把 STL 三维模型放进程序，设置喷嘴温度、热床温度、层高、速度、填充、边裙和五轴切片方向等参数，程序会计算打印路径，并把路径保存成打印机可以读取的 G-code 文件。

可以把流程理解为：

```text
STL 三维模型
  -> 读取模型
  -> 按层或按五轴方向切开模型
  -> 计算外壳路径、实心填充路径、内部填充路径和边裙
  -> 在界面中预览路径
  -> 写出 G-code 文件
```

## 先看哪些文件

第一次接触项目时，建议按这个顺序看：

1. `README.md`：了解项目内容、依赖、运行方式和示例文件。
2. `docs/BEGINNER_PROJECT_GUIDE.md`：理解项目整体流程，也就是本文。
3. `docs/MAINTAINER_GUIDE.md`：理解维护边界、数据流和后续扩展位置。
4. `src/five_axis_slicer/app.py`：了解桌面程序从哪里启动。
5. `src/five_axis_slicer/ui/window.py`：了解窗口、三维视图、模型加载和后台切片任务。
6. `src/five_axis_slicer/ui/controller.py`：了解按钮、输入框、语言切换、参数读取和保存 G-code。
7. `src/five_axis_slicer/core/slicer.py`：了解给测试脚本和未来命令行使用的清晰切片入口。
8. `src/five_axis_slicer/core/legacy_engine.py`：了解主要几何算法和 G-code 写出逻辑。

## 目录分别负责什么

`src/five_axis_slicer/core` 是核心计算层。这里负责把模型切成层，把层转成路径，再把路径写成 G-code。长期维护时，核心层应该尽量保持稳定和可测试。

`src/five_axis_slicer/ui` 是界面层。这里负责窗口、按钮、输入框、鼠标交互、语言切换和三维预览。用户看到和点击的东西基本都在这一层。

`src/five_axis_slicer/assets` 保存字体和按钮图片。界面图片由脚本生成或保存，代码会按路径加载这些资源。

`tools` 保存维护脚本。`smoke_core.py` 用一个小盒子模型检查核心切片和 G-code 写出。`smoke_language.py` 检查中英文切换后按钮状态是否保持正常。

`example/pipe` 保存管件示例 STL 和当前生成的 G-code。它适合人工对比和演示。

`Open5X` 与 `Fractal-Cortex-main` 更适合作为参考资料或历史来源。日常维护通常先看 `src/five_axis_slicer`。

## 程序启动时发生什么

运行 `.\run_app.ps1` 后，脚本会启动 Python 程序。Python 入口在 `src/five_axis_slicer/app.py`。这个入口继续调用 `src/five_axis_slicer/ui/window.py` 里的 `main()`。

窗口创建后，程序会准备三类对象：

1. 窗口和相机：负责三维视角、缩放、旋转和平移。
2. 控件面板：负责材料、强度、精度、喷嘴运动、支撑和附着等参数输入。
3. 后台计算队列：负责把耗时切片任务放到后台执行，避免界面卡住。

## 用户点击切片时发生什么

用户点击切片按钮后，程序会从界面读取当前参数。参数包括温度、层高、填充率、速度、是否启用 Z hop、是否启用回抽、五轴联动轴符号等。

随后程序会根据当前模式选择不同路径：

```text
3 轴模式
  -> legacy_engine.slice_in_3_axes()
  -> 按水平层切片
  -> 生成外壳、填充、边裙

5 轴模式
  -> legacy_engine.slice_in_5_axes()
  -> 先按用户设置的切片方向把模型分成多个 chunk
  -> 每个 chunk 使用自己的方向切片
  -> 生成每个 chunk 的外壳、填充和路径
```

切片完成后，结果会保存在界面控制器的结果变量里。预览按钮会把这些结果转换成三维线段并显示在窗口里。保存按钮会把这些结果写成 G-code。

## 几个重要概念

STL：三维模型文件，保存模型表面网格。

切片：把三维模型按一层一层或按五轴方向分割，得到每层轮廓。

Shell：外壳路径，也就是模型外壁和内壁的打印线。

Internal infill：内部填充路径，用较稀疏的线条填充模型内部。

Solid infill：实心填充路径，通常用于上下表面、悬空或需要更强支撑的区域。

Brim：边裙，在第一层模型外侧增加几圈线，提高附着能力。

G-code：打印机执行的命令文件，里面有移动、加热、挤出、回抽等指令。

Chunk：五轴模式中的模型分块。每个 chunk 对应一个切片方向。

## 修改项目时怎么避免破坏功能

改界面文字时，优先改 `src/five_axis_slicer/ui/controller.py` 里的 `TEXT` 字典，然后检查 `register_localized_widgets()` 是否注册了对应控件。

改打印参数时，需要同时检查四个位置：

1. `src/five_axis_slicer/core/settings.py` 的 `PrintSettings`。
2. `src/five_axis_slicer/ui/controller.py` 的默认值和 `update_values()`。
3. `src/five_axis_slicer/ui/controller.py` 的 `slice_function()`。
4. `src/five_axis_slicer/core/legacy_engine.py` 顶部的 `printSettings` 索引表。

改切片算法时，优先从 `src/five_axis_slicer/core/legacy_engine.py` 找到对应阶段。该文件顶部已经把流程分成模型切面、外壳生成、区域分类、填充路径、预览转换和 G-code 写出。核心算法文件中的开发者注释应保持中文，并写清楚输入、输出、坐标变换和几何假设。每次改动后都应运行检查脚本。

改窗口交互时，优先看 `src/five_axis_slicer/ui/window.py`。这里管理鼠标、键盘、相机、模型选择和 OpenGL 绘制。

## 必须做的检查

只检查语法和导入：

```powershell
& 'C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe' -m compileall -q src tools
```

检查核心切片和 G-code 写出：

```powershell
& 'C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe' tools\smoke_core.py
```

检查界面语言切换：

```powershell
& 'C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe' tools\smoke_language.py
```

运行完整烟雾检查：

```powershell
.\run_smoke.ps1
```

## 后续维护建议

第一，继续把大文件拆成更清楚的小模块。`controller.py` 可以逐步拆出参数读取、语言注册、切片方向编辑和保存逻辑。第二，给 `legacy_engine.py` 的关键几何函数增加小型测试。第三，把当前的全局状态逐步收拢成对象，让新开发者更容易追踪数据从哪里来、到哪里去。第四，保持文档、注释和烟雾测试同步更新，让每次改动都有说明和检查依据。
