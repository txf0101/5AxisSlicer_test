from pathlib import Path
import sys
import tempfile

import trimesh


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from five_axis_slicer.core.gcode import write_3_axis_gcode  # noqa: E402
from five_axis_slicer.core.settings import PrintSettings  # noqa: E402
from five_axis_slicer.core.slicer import slice_meshes_3_axis  # noqa: E402


def main() -> None:
    mesh = trimesh.creation.box(extents=(10.0, 10.0, 4.0))
    mesh.apply_translation((0.0, 0.0, 2.0))

    settings = PrintSettings(
        infill_percentage=0.0,
        shell_thickness=1,
        layer_height=1.0,
        enable_z_hop=False,
        enable_retraction=False,
    )
    result = slice_meshes_3_axis([mesh], settings=settings, workers=1)

    if result.mode != "3_axis":
        raise RuntimeError("Unexpected slicing mode.")
    if not result.transform3d or len(result.transform3d) != len(result.shells):
        raise RuntimeError("Unexpected slice dimensions.")

    tmp_parent = PROJECT_ROOT / "tmp"
    tmp_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=tmp_parent) as tmp_dir:
        gcode_path = Path(tmp_dir) / "smoke_box.gcode"
        write_3_axis_gcode(gcode_path, "smoke_box", result)
        gcode_text = gcode_path.read_text(encoding="utf-8")
        if "SLICER:       Fractal Cortex" not in gcode_text:
            raise RuntimeError("G-code header was not written.")

    print(f"smoke ok: {len(result.transform3d)} layers")


if __name__ == "__main__":
    main()
