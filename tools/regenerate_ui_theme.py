from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "five_axis_slicer" / "assets" / "image_resources"

TEXT = (17, 17, 17, 255)
SECONDARY = (102, 102, 102, 255)
ACCENT = (17, 17, 17, 255)
PANEL = (245, 245, 247, 255)
WHITE = (255, 255, 255, 255)
HOVER = (246, 246, 246, 255)
DOWN = (232, 232, 232, 255)
DISABLED = (235, 235, 235, 255)
OUTLINE = (208, 208, 208, 255)
TRANSPARENT = (255, 255, 255, 0)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        ROOT / "src" / "five_axis_slicer" / "assets" / "Roboto-Regular.ttf",
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def rounded(size, fill, outline=OUTLINE, radius=12, width=1):
    image = Image.new("RGBA", size, TRANSPARENT)
    draw = ImageDraw.Draw(image)
    box = (0, 0, size[0] - 1, size[1] - 1)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    return image


def write(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def existing_size(path: Path) -> tuple[int, int]:
    return Image.open(path).size


def center_text(draw, box, text, fill=TEXT, size=12, bold=False) -> None:
    fnt = font(size, bold=bold)
    bbox = draw.textbbox((0, 0), text, font=fnt)
    x = box[0] + (box[2] - box[0] - (bbox[2] - bbox[0])) / 2
    y = box[1] + (box[3] - box[1] - (bbox[3] - bbox[1])) / 2 - 1
    draw.text((x, y), text, font=fnt, fill=fill)


def button_image(path: Path, state: str, label: str | None = None, icon: str | None = None) -> None:
    size = existing_size(path)
    fill = {"base": WHITE, "over": HOVER, "down": DOWN, "disabled": DISABLED}.get(state, WHITE)
    image = rounded(size, fill, OUTLINE, radius=min(14, max(6, size[1] // 2)))
    draw = ImageDraw.Draw(image)
    if icon == "folder":
        draw.rounded_rectangle((14, 18, size[0] - 13, size[1] - 12), radius=7, fill=(242, 242, 242, 255), outline=ACCENT, width=2)
        draw.rounded_rectangle((16, 13, 34, 22), radius=4, fill=(242, 242, 242, 255), outline=ACCENT, width=2)
    elif icon == "plus":
        cx, cy = size[0] // 2, size[1] // 2
        draw.line((cx - 9, cy, cx + 9, cy), fill=ACCENT, width=3)
        draw.line((cx, cy - 9, cx, cy + 9), fill=ACCENT, width=3)
    elif icon == "trash":
        cx = size[0] // 2
        draw.rounded_rectangle((cx - 8, 18, cx + 8, size[1] - 10), radius=3, outline=ACCENT, width=2)
        draw.line((cx - 11, 15, cx + 11, 15), fill=ACCENT, width=2)
        draw.line((cx - 5, 12, cx + 5, 12), fill=ACCENT, width=2)
    elif icon == "clear":
        cx, cy = size[0] // 2, size[1] // 2
        draw.line((cx - 9, cy - 9, cx + 9, cy + 9), fill=ACCENT, width=3)
        draw.line((cx + 9, cy - 9, cx - 9, cy + 9), fill=ACCENT, width=3)
    elif icon == "check":
        cx, cy = size[0] // 2, size[1] // 2
        draw.line((cx - 10, cy, cx - 3, cy + 7, cx + 12, cy - 9), fill=ACCENT, width=3, joint="curve")
    if label:
        center_text(draw, (0, 0, size[0], size[1]), label, fill=ACCENT, size=12, bold=True)
    write(path, image)


def radio(path: Path, state: str) -> None:
    size = existing_size(path)
    fill = WHITE
    outline = OUTLINE
    if state == "over":
        fill = HOVER
    elif state == "down":
        fill = DOWN
    elif state == "checked":
        fill = (238, 238, 238, 255)
        outline = ACCENT
    write(path, rounded(size, fill, outline, radius=min(14, max(8, size[1] // 2)), width=2 if state == "checked" else 1))


def geometry_radio(path: Path, state: str, icon: str) -> None:
    size = existing_size(path)
    fill = WHITE
    outline = OUTLINE
    if state == "over":
        fill = HOVER
    elif state == "down":
        fill = DOWN
    elif state == "checked":
        fill = (238, 238, 238, 255)
        outline = ACCENT

    image = rounded(size, fill, outline, radius=14, width=2 if state == "checked" else 1)
    draw = ImageDraw.Draw(image)
    cx, cy = size[0] // 2, size[1] // 2
    color = ACCENT
    if icon == "translate":
        draw.line((cx, cy - 15, cx, cy + 15), fill=color, width=3)
        draw.line((cx - 15, cy, cx + 15, cy), fill=color, width=3)
        draw.polygon([(cx, cy - 20), (cx - 5, cy - 11), (cx + 5, cy - 11)], fill=color)
        draw.polygon([(cx, cy + 20), (cx - 5, cy + 11), (cx + 5, cy + 11)], fill=color)
        draw.polygon([(cx - 20, cy), (cx - 11, cy - 5), (cx - 11, cy + 5)], fill=color)
        draw.polygon([(cx + 20, cy), (cx + 11, cy - 5), (cx + 11, cy + 5)], fill=color)
    elif icon == "rotate":
        draw.arc((cx - 17, cy - 17, cx + 17, cy + 17), 25, 315, fill=color, width=3)
        draw.polygon([(cx + 15, cy - 15), (cx + 21, cy - 6), (cx + 10, cy - 6)], fill=color)
    elif icon == "scale":
        draw.line((cx - 13, cy + 13, cx + 13, cy - 13), fill=color, width=3)
        draw.polygon([(cx + 17, cy - 17), (cx + 6, cy - 15), (cx + 15, cy - 6)], fill=color)
        draw.polygon([(cx - 17, cy + 17), (cx - 6, cy + 15), (cx - 15, cy + 6)], fill=color)
    write(path, image)


def panel(path: Path, radius: int = 16) -> None:
    size = existing_size(path)
    write(path, rounded(size, WHITE, OUTLINE, radius=radius))


def draw_text(draw: ImageDraw.ImageDraw, xy, text, fill=TEXT, size=12, bold=False) -> None:
    draw.text(xy, text, font=font(size, bold=bold), fill=fill)


def starting_box(path: Path, language: str) -> None:
    size_source = path if path.exists() else path.with_name("background.png")
    size = existing_size(size_source)
    image = rounded(size, WHITE, OUTLINE, radius=12)
    draw = ImageDraw.Draw(image)
    label = "初始切片方向数量" if language == "zh" else "Starting Number of Slicing Directions"
    draw_text(draw, (26, 15), label, size=13, bold=True)
    write(path, image)


def slicing_box(path: Path, language: str) -> None:
    size_source = path if path.exists() else path.with_name("background.png")
    size = existing_size(size_source)
    image = rounded(size, WHITE, OUTLINE, radius=16)
    draw = ImageDraw.Draw(image)
    if language == "zh":
        current = "当前切片方向"
        start = "起始位置"
        direction = "方向"
    else:
        current = "Current Slicing Direction"
        start = "Starting Position"
        direction = "Direction"

    draw_text(draw, (86, 18), current, size=13, bold=True)
    draw.rounded_rectangle((12, 50, 198, 200), radius=18, fill=(250, 250, 250, 255), outline=OUTLINE)
    draw.rounded_rectangle((210, 50, 397, 168), radius=18, fill=(250, 250, 250, 255), outline=OUTLINE)
    draw_text(draw, (58, 58), start, size=11)
    draw_text(draw, (285 if language == "zh" else 274, 58), direction, size=11)
    draw_text(draw, (45, 87), "X", fill=(34, 34, 34, 255), size=13)
    draw_text(draw, (45, 127), "Y", fill=(102, 102, 102, 255), size=13)
    draw_text(draw, (45, 167), "Z", fill=(153, 153, 153, 255), size=13)
    draw_text(draw, (241, 87), "θ", size=14)
    draw_text(draw, (241, 127), "φ", size=14)
    write(path, image)


def checkbox(path: Path, checked: bool, state: str) -> None:
    size = existing_size(path)
    fill = {"base": WHITE, "over": HOVER, "down": DOWN}.get(state, WHITE)
    image = rounded(size, fill, ACCENT if checked else OUTLINE, radius=6, width=2 if checked else 1)
    draw = ImageDraw.Draw(image)
    if checked:
        draw.line((5, size[1] // 2, size[0] // 2 - 1, size[1] - 6, size[0] - 5, 5), fill=ACCENT, width=3)
    write(path, image)


def blank_logo() -> None:
    path = ASSETS / "logo" / "logo.png"
    if path.exists():
        write(path, Image.new("RGBA", existing_size(path), TRANSPARENT))


def axis_icon(path: Path) -> None:
    size = existing_size(path)
    image = Image.new("RGBA", size, TRANSPARENT)
    draw = ImageDraw.Draw(image)
    origin = (max(8, size[0] // 4), size[1] - max(8, size[1] // 5))
    x_end = (size[0] - max(8, size[0] // 8), origin[1])
    y_end = (origin[0] + max(10, size[0] // 4), origin[1] - max(10, size[1] // 4))
    z_end = (origin[0], max(6, size[1] // 8))

    for end, shade in [
        (x_end, (34, 34, 34, 255)),
        (y_end, (102, 102, 102, 255)),
        (z_end, (153, 153, 153, 255)),
    ]:
        draw.line((origin[0], origin[1], end[0], end[1]), fill=shade, width=max(2, size[0] // 40))
        dx = end[0] - origin[0]
        dy = end[1] - origin[1]
        length = max((dx * dx + dy * dy) ** 0.5, 1)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        arrow = max(5, size[0] // 12)
        base = (end[0] - ux * arrow, end[1] - uy * arrow)
        draw.polygon(
            [
                end,
                (base[0] + px * arrow * 0.45, base[1] + py * arrow * 0.45),
                (base[0] - px * arrow * 0.45, base[1] - py * arrow * 0.45),
            ],
            fill=shade,
        )
    write(path, image)


def main() -> None:
    blank_logo()
    axis_icon(ASSETS / "slicingDirectionBox_Images" / "edit" / "coords.png")
    axis_icon(ASSETS / "slicingDirectionBox_Images" / "edit" / "sphericalCoords.png")

    for bg in [
        "viewMode_Radio_Button_Images/background.png",
        "printMode_Radio_Button_Images/background.png",
        "optionMode_Radio_Button_Images/background.png",
        "geometryAction_Radio_Button_Images/background.png",
        "rotateMode_Radio_Button_Images/background.png",
        "geometryActionPopUpBox_Images/background.png",
        "geometryActionPopUpBox_Images/scaleBackground.png",
    ]:
        panel(ASSETS / bg)

    panel(ASSETS / "geometryActionPopUpBox_Images/blank.png")

    starting_box(ASSETS / "slicingDirectionBox_Images" / "startingBox" / "background_zh.png", "zh")
    starting_box(ASSETS / "slicingDirectionBox_Images" / "startingBox" / "background_en.png", "en")
    slicing_box(ASSETS / "slicingDirectionBox_Images" / "background_zh.png", "zh")
    slicing_box(ASSETS / "slicingDirectionBox_Images" / "background_en.png", "en")
    starting_box(ASSETS / "slicingDirectionBox_Images" / "startingBox" / "background.png", "zh")
    slicing_box(ASSETS / "slicingDirectionBox_Images" / "background.png", "zh")

    radio_roots = [
        "viewMode_Radio_Button_Images/prepare",
        "viewMode_Radio_Button_Images/preview",
        "printMode_Radio_Button_Images/5AxisMode",
        "printMode_Radio_Button_Images/3AxisMode",
        "optionMode_Radio_Button_Images/material",
        "optionMode_Radio_Button_Images/strength",
        "optionMode_Radio_Button_Images/resolution",
        "optionMode_Radio_Button_Images/movement",
        "optionMode_Radio_Button_Images/supports",
        "optionMode_Radio_Button_Images/adhesion",
        "rotateMode_Radio_Button_Images/x",
        "rotateMode_Radio_Button_Images/y",
        "rotateMode_Radio_Button_Images/z",
    ]
    for root in radio_roots:
        radio(ASSETS / root / "R_uncheckedBase.png", "base")
        radio(ASSETS / root / "R_uncheckedOver.png", "over")
        radio(ASSETS / root / "R_uncheckedDown.png", "down")
        radio(ASSETS / root / "R_checked.png", "checked")

    for root, icon in [
        ("geometryAction_Radio_Button_Images/translate", "translate"),
        ("geometryAction_Radio_Button_Images/rotate", "rotate"),
        ("geometryAction_Radio_Button_Images/scale", "scale"),
    ]:
        geometry_radio(ASSETS / root / "R_uncheckedBase.png", "base", icon)
        geometry_radio(ASSETS / root / "R_uncheckedOver.png", "over", icon)
        geometry_radio(ASSETS / root / "R_uncheckedDown.png", "down", icon)
        geometry_radio(ASSETS / root / "R_checked.png", "checked", icon)

    for state in ["base", "over", "down"]:
        button_image(ASSETS / "File_Button_Images" / f"{state}.png", state, icon="folder")
        button_image(ASSETS / "Slice_Button_Images" / "slice" / f"{state}.png", state, label="切片 Slice")
        button_image(ASSETS / "Slice_Button_Images" / "saveGcodeAs" / f"{state}.png", state, label="保存 Save")
        button_image(ASSETS / "apply_Button_Images" / f"{state}.png", state, icon="check")
        button_image(ASSETS / "slicingDirectionBox_Images" / "startingBox" / "apply" / f"{state}.png", state, icon="check")
        button_image(ASSETS / "slicingDirectionBox_Images" / "addNew" / f"{state}.png", state, icon="plus")
        button_image(ASSETS / "slicingDirectionBox_Images" / "remove" / f"{state}.png", state, icon="trash")
        button_image(ASSETS / "slicingDirectionBox_Images" / "removeAll" / f"{state}.png", state, icon="clear")

    button_image(ASSETS / "Slice_Button_Images" / "slice" / "disabled.png", "disabled", label="切片 Slice")
    button_image(ASSETS / "slicingDirectionBox_Images" / "startingBox" / "apply" / "disabled.png", "disabled", icon="check")

    checkbox_names = {
        "checkedBase.png": (True, "base"),
        "checkedOver.png": (True, "over"),
        "checkedDown.png": (True, "down"),
        "uncheckedBase.png": (False, "base"),
        "uncheckedOver.png": (False, "over"),
        "uncheckedDown.png": (False, "down"),
    }
    for name, (checked, state) in checkbox_names.items():
        checkbox(ASSETS / "CheckBox_Images" / name, checked, state)


if __name__ == "__main__":
    main()
