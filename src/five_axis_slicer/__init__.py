"""Package marker for the 5AxisSlicer application.

给新开发者看的说明：
    这个文件可以理解为整个 `five_axis_slicer` 包的门牌。Python 看到
    `src/five_axis_slicer` 目录里有这个文件，就会把该目录当成一个可以
    导入的包。其他文件就可以写 `import five_axis_slicer` 或导入它下面的
    `core`、`ui` 等模块。

    这个文件目前只保存版本号，不启动界面，不执行切片，也不读取 STL。
    真正的桌面程序入口在 `app.py`，命令行的 `python -m five_axis_slicer`
    入口在 `__main__.py`。核心切片能力集中在 `core` 目录，界面集中在
    `ui` 目录。

维护提示：
    如果后续发布正式版本，请让这里的 `__version__` 与 `pyproject.toml`
    中的版本号保持一致。版本号是开发者判断当前代码状态的重要线索。
"""

__version__ = "0.1.0"
