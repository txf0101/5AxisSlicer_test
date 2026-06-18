"""Allow `python -m five_axis_slicer` to start the GUI.

给新开发者看的说明：
    Python 有一个约定：当用户在命令行执行 `python -m 包名` 时，会寻找该
    包里的 `__main__.py`。因此，本文件负责把 `python -m five_axis_slicer`
    这种启动方式转交给 `app.py`。

    这里没有直接创建窗口，因为项目已经有统一入口 `app.py`。保持单一入口
    能减少维护成本：以后如果启动流程需要增加日志、配置读取或错误提示，只
    需要改 `app.py` 或 `ui.window.main()`，不用在多个入口重复修改。
"""

from .app import main


if __name__ == "__main__":
    main()
