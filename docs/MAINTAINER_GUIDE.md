# 5AxisSlicer Maintainer Guide

This guide is based on the current repository files: `README.md`,
`pyproject.toml`, `src/five_axis_slicer`, `tools`, and `example/pipe`. It is a
developer entry point for understanding project boundaries, data flow, and
safe extension points.

## Project Goal

This repository maintains a Python five-axis FDM slicer. The package entry is
`src/five_axis_slicer`. The desktop GUI uses Pyglet, Glooey, and OpenGL. The
geometry stack uses Trimesh, Shapely, and Manifold3D. The `Open5X` and
`Fractal-Cortex-main` folders mainly serve as reference implementations,
example material, or historical source material. Day-to-day feature work should
normally target `src/five_axis_slicer`, `tools`, and `docs`.

## Directory Responsibilities

`src/five_axis_slicer/core` contains reusable slicing capability. `settings.py`
defines named parameter objects, `slicer.py` exposes 3-axis and 5-axis slicing
entry points, `gcode.py` writes calculated results to G-code, and
`legacy_engine.py` preserves the main migrated geometry and writer logic.

`src/five_axis_slicer/ui` contains desktop GUI capability. `window.py` manages
the Pyglet window, camera, OpenGL rendering, STL loading, and background
calculation worker. `controller.py` manages widget instances, language
switching, page switching, parameter reading, slicing requests, and save
actions. `widgets.py` wraps Glooey controls and reusable input components.

`tools` contains lightweight maintenance scripts. `smoke_core.py` checks core
slicing and G-code writing. `smoke_language.py` checks language switching and
hidden deck text behavior. `regenerate_ui_theme.py` regenerates GUI image
assets.

`example/pipe` stores the current example STL and G-code output. It is useful
for manual comparison and demonstrations. Long-term regression tests should
prefer smaller synthetic geometry or dedicated fixtures so routine checks stay
fast.

## Main Data Flow

In GUI mode, `five_axis_slicer.app:main` calls `ui.window.main()` and creates a
`Graphics_Window`. After the user loads STL files, the window stores models as
Trimesh objects and `controller.py` reads widget values into slicing settings.
3-axis slicing calls `legacy_engine.slice_in_3_axes()`. 5-axis slicing calls
`legacy_engine.slice_in_5_axes()`. After the calculation finishes, the
controller keeps the result structures for preview rendering and G-code export.

In script or test mode, developers should prefer `five_axis_slicer.core.slicer`.
The caller passes Trimesh objects, `PrintSettings`, and optionally a
`SlicingPlan`, then receives a `SliceResult`. The caller can then use
`five_axis_slicer.core.gcode` to write G-code. This path is better for tests,
automation, and future command-line tools because it isolates legacy positional
arguments inside the core wrapper.

## Maintenance Conventions

When adding a slicing parameter, first add a named field to `PrintSettings` and
document its unit. Then update `to_legacy_list()`, GUI value reading, and G-code
writing together. This keeps the positional legacy contract reviewable.

When adding visible GUI text, put the text in the `TEXT` dictionary in
`controller.py`, then register the widget through the existing registration
helpers. This keeps Chinese and English UI labels synchronized by key.

When changing `legacy_engine.py`, keep developer-facing comments in Chinese and
document the input shape, output shape, and geometry assumption near the
function being changed. The file carries migrated reference logic and several
long functions, so behavior changes should include a focused smoke check or
regression fixture.

When adding a tool script, make it runnable from the repository root and state
what it verifies, what it depends on, and where it writes temporary files. The
current scripts insert `src` into `sys.path` so developers can run them before
installing the package.

## Checks

Run the full smoke entry after core changes:

```powershell
.\run_smoke.ps1
```

Run only core slicing and writer verification:

```powershell
& 'C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe' tools\smoke_core.py
```

Run syntax and import compilation:

```powershell
& 'C:\Users\Tang Xufeng\.conda\envs\5AxisSlicer\python.exe' -m compileall -q src tools
```

If UI language, widget registration, or deck switching changes, run
`tools\smoke_language.py`. That script opens a Pyglet window, so it is best run
inside a desktop session.

## Next Maintainability Work

First, gradually reduce global state in `controller.py` by separating parameter
reading, widget registration, and slicing execution. Second, add small input
fixtures for key `legacy_engine.py` geometry functions, especially brim, shell,
infill, and 5-axis chunk splitting. Third, replace the broad `object` fields in
`SliceResult` with named path data structures as those structures become stable.
Fourth, resave `docs/PROJECT_ANALYSIS.md` with a verified encoding before using
it as a primary onboarding document, because it currently renders as mojibake in
this PowerShell session.
