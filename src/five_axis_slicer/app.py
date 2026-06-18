"""Application entry point for the desktop slicer GUI.

给新开发者看的说明：
    这个文件是“启动桌面程序”的最短路径。安装项目后，`pyproject.toml`
    里的脚本入口 `five-axis-slicer = "five_axis_slicer.app:main"` 会指向
    这里。运行脚本时，Python 会导入本文件，然后调用从 `ui.window`
    转交过来的 `main()`。

启动后发生的事情：
    1. `ui.window.main()` 创建 Pyglet 窗口；
    2. 窗口创建右侧参数面板和左侧三维预览区；
    3. 用户选择 STL 文件后，窗口读取模型并显示；
    4. 用户点击切片后，界面把模型和参数交给核心切片逻辑；
    5. 切片完成后，用户可以预览路径或保存 G-code。

维护提示：
    这个文件应保持很小。启动细节放在 `ui.window`，参数控件放在
    `ui.controller`，切片算法放在 `core`。入口文件越短，后续排查启动问题
    越容易。
"""

from .ui.window import main


if __name__ == "__main__":
    main()
