# 5AxisSlicer_test V1.0

This repository contains a focused Python replication of the Fractal Cortex
five axis slicer workflow. It is intended as a backup and version management
repository for the current replicated project state.

## Contents

- `src/five_axis_slicer/core`: slicing settings, 3 axis and 5 axis slicing
  entry points, legacy algorithm bridge, and G-code writing logic.
- `src/five_axis_slicer/ui`: Pyglet and Glooey user interface code.
- `src/five_axis_slicer/assets`: packaged fonts and generated button images.
- `tools/smoke_core.py`: minimal core slicing and G-code write smoke check.
- `tools/smoke_language.py`: bilingual UI state smoke check.
- `tools/regenerate_ui_theme.py`: helper for regenerating GUI image assets.
- `example/pipe`: the current locally generated pipe fitting G-code output.
- `run_app.ps1`: starts the GUI in the `5AxisSlicer` Conda environment.
- `run_smoke.ps1`: runs the smoke checks.

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

## Smoke Check

```powershell
.\run_smoke.ps1
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
