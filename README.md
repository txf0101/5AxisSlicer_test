# 5AxisSlicer_test V1.0

This repository contains a focused Python replication of the Fractal Cortex
five axis slicer workflow. It is intended as a backup and version management
repository for the current replicated project state.

## 中文简述

本仓库保存 5AxisSlicer 的当前项目状态，用于五轴 FDM 切片流程的备份、
演示和后续维护。项目主体位于 `src/five_axis_slicer`，桌面界面使用
Pyglet/Glooey，几何计算依赖 Trimesh、Shapely 和 Manifold3D。

运行前使用现有 Conda 环境并安装依赖：

```powershell
conda activate 5AxisSlicer
pip install -r requirements.txt
```

启动界面：

```powershell
.\run_app.ps1
```

示例目录只保留 `example/pipe`：`pipe_fitting.stl` 是输入模型，
`pipe_fitting.gcode` 是当前本地生成的输出。

## Contents

- `src/five_axis_slicer/core`: slicing settings, 3 axis and 5 axis slicing
  entry points, legacy algorithm bridge, and G-code writing logic.
- `src/five_axis_slicer/ui`: Pyglet and Glooey user interface code.
- `src/five_axis_slicer/assets`: packaged fonts and generated button images.
- `docs/BEGINNER_PROJECT_GUIDE.md`: Chinese beginner guide for readers who do
  not yet know the codebase or the slicing workflow.
- `docs/MAINTAINER_GUIDE.md`: maintainer-oriented project map, data flow, and
  extension notes for new developers.
- `tools/regenerate_ui_theme.py`: helper for regenerating GUI image assets.
- `example/pipe`: the current locally generated pipe fitting G-code output.
- `run_app.ps1`: starts the GUI in the `5AxisSlicer` Conda environment.

## Reference Basis

The replication work was compared against the local Fractal Cortex reference
project kept in the development workspace. Those reference files are not
bundled in this repository.

- `Fractal-Cortex-main/Fractal-Cortex-main/README.md`
- `Fractal-Cortex-main/Fractal-Cortex-main/LICENSE`
- `Fractal-Cortex-main/Fractal-Cortex-main/fractal-cortex/*.py`
- `Fractal-Cortex-main/Fractal-Cortex-main/examples/example_5_axis_gcode_for_pipe_fitting.gcode`
- `Fractal-Cortex-main/Fractal-Cortex-main/examples/pipe_fitting.stl`
- `Fractal-Cortex-main/Fractal-Cortex-main/examples/Step_4.PNG`
- `Fractal-Cortex-main/Fractal-Cortex-main/examples/Step_5.PNG`

## Environment

Use the existing Conda environment:

```powershell
conda activate 5AxisSlicer
pip install -r requirements.txt
```

Pinned geometry dependencies are important for robust slice polygon recovery:

- `numpy==1.26.4`
- `shapely==2.0.4`
- `trimesh==4.3.1`
- `manifold3d==3.4.1`

## Run

```powershell
.\run_app.ps1
```

## Pipe Fitting Local Output

The file `example/pipe/pipe_fitting.gcode` is the local generated output kept
for backup and comparison during development. The reference setup used during
manual comparison was:

| Direction | X | Y | Z | theta | phi |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| 2 | 20.0 | 0.0 | 60.0 | 75.0 | 0.0 |
| 3 | -20.0 | 0.0 | 105.0 | 45.0 | -120.0 |
