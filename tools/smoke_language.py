from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from five_axis_slicer.ui.window import Graphics_Window  # noqa: E402
import five_axis_slicer.ui.controller as ui  # noqa: E402


def safe_text(widget) -> str:
    """Read text from either Glooey labels or local wrapper widgets."""
    try:
        return widget.get_text()
    except AttributeError:
        return getattr(widget, "text", "")


def assert_hidden_text_is_clear() -> None:
    """Ensure hidden deck labels do not leak into inactive GUI pages.

    The GUI reuses several Glooey deck rows for different settings tabs. When a
    tab changes language, inactive rows must be cleared so text from another tab
    does not remain visible behind the active page.
    """
    for state, pairs in ui.SETTINGS_TEXT_WIDGETS.items():
        if state == ui.settingsState:
            continue
        for key, widget in pairs:
            if safe_text(widget) != "":
                raise RuntimeError(f"Hidden settings text leaked: {state}:{key}")

    for state, pairs in ui.SETTINGS_UNIT_WIDGETS.items():
        if state == ui.settingsState:
            continue
        for key, widget in pairs:
            if safe_text(widget) != "":
                raise RuntimeError(f"Hidden settings unit leaked: {state}:{key}")

    for state, pairs in ui.GEOMETRY_TEXT_WIDGETS.items():
        if state == ui.geometryActionState:
            continue
        for key, widget in pairs:
            if safe_text(widget) != "":
                raise RuntimeError(f"Hidden geometry text leaked: {state}:{key}")


def main() -> None:
    """Open a window, switch UI language, and verify functional state survives."""
    win = Graphics_Window(
        width=1080,
        height=720,
        resizable=True,
        caption="Language smoke",
    )
    try:
        # Widgets are created at import time, then attached to the concrete GUI
        # here. This mirrors the real application startup path closely enough to
        # catch controller registration issues.
        ui.initialize_all_widgets(win.gui, win.windowHeight)
        before = (
            ui.R_printMode.currentlyChecked,
            ui.R_viewMode.currentlyChecked,
            ui.R_optionMode.currentlyChecked,
        )
        if ui.L_settingsTitle.get_text() != "打印设置":
            raise RuntimeError("Chinese UI title was not applied.")
        if ui.B_languageToggle.label != "中文 / EN":
            raise RuntimeError("Language toggle label is not visible in Chinese mode.")
        assert_hidden_text_is_clear()

        # The first toggle should translate labels while preserving selected
        # radio buttons and active decks.
        ui.toggle_language()
        after = (
            ui.R_printMode.currentlyChecked,
            ui.R_viewMode.currentlyChecked,
            ui.R_optionMode.currentlyChecked,
        )
        if before != after:
            raise RuntimeError("Language switching changed functional state.")
        if ui.L_settingsTitle.get_text() != "Print Settings":
            raise RuntimeError("English UI title was not applied.")
        if ui.B_languageToggle.label != "中文 / EN":
            raise RuntimeError("Language toggle label is not visible in English mode.")
        assert_hidden_text_is_clear()

        # Also exercise the actual button handler, because direct function calls
        # can miss callback wiring mistakes.
        ui.B_languageToggle.on_click(ui.B_languageToggle)
        if ui.CURRENT_LANGUAGE != "zh":
            raise RuntimeError("Language toggle button did not switch back to Chinese.")
        if before != (
            ui.R_printMode.currentlyChecked,
            ui.R_viewMode.currentlyChecked,
            ui.R_optionMode.currentlyChecked,
        ):
            raise RuntimeError("Language button click changed functional state.")
        assert_hidden_text_is_clear()

        print("language smoke ok:", before, "->", after)
    finally:
        win.close()


if __name__ == "__main__":
    main()
