from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from five_axis_slicer.ui.window import Graphics_Window  # noqa: E402
import five_axis_slicer.ui.controller as ui  # noqa: E402


def assert_hidden_text_is_clear() -> None:
    for state, pairs in ui.SETTINGS_TEXT_WIDGETS.items():
        if state == ui.settingsState:
            continue
        for key, widget in pairs:
            if widget.get_text() != "":
                raise RuntimeError(f"Hidden settings text leaked: {state}:{key}")

    for state, pairs in ui.SETTINGS_UNIT_WIDGETS.items():
        if state == ui.settingsState:
            continue
        for key, widget in pairs:
            if widget.get_text() != "":
                raise RuntimeError(f"Hidden settings unit leaked: {state}:{key}")

    for state, pairs in ui.GEOMETRY_TEXT_WIDGETS.items():
        if state == ui.geometryActionState:
            continue
        for key, widget in pairs:
            if widget.get_text() != "":
                raise RuntimeError(f"Hidden geometry text leaked: {state}:{key}")


def main() -> None:
    win = Graphics_Window(
        width=1080,
        height=720,
        resizable=True,
        caption="Language smoke",
    )
    try:
        ui.initialize_all_widgets(win.gui, win.windowHeight)
        before = (
            ui.R_printMode.currentlyChecked,
            ui.R_viewMode.currentlyChecked,
            ui.R_optionMode.currentlyChecked,
        )
        if ui.L_settingsTitle.get_text() != "打印设置":
            raise RuntimeError("Chinese UI title was not applied.")
        if ui.L_languageToggle.get_text() != "中文 / EN":
            raise RuntimeError("Language toggle label is not visible in Chinese mode.")
        assert_hidden_text_is_clear()

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
        if ui.L_languageToggle.get_text() != "中文 / EN":
            raise RuntimeError("Language toggle label is not visible in English mode.")
        assert_hidden_text_is_clear()

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
