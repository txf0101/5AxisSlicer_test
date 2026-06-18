# 2026-06-18 发布复盘

## 发布范围

本次发布目标是把当前 5AxisSlicer 项目推送到
`txf0101/5AxisSlicer_test`。发布清单限定为根目录运行文件、
`src/five_axis_slicer`、`tools`、`docs` 和 `example/pipe`。

`Open5X` 与 `Fractal-Cortex-main` 保持本地参考资料身份，不进入提交。
`example` 下除 `pipe` 外的叶轮、扇叶和球形 NEU 校徽示例不进入提交。

## 判断依据

`docs/MAINTAINER_GUIDE.md` 已说明日常开发边界主要在
`src/five_axis_slicer`、`tools`、`docs` 和 `example/pipe`。README 的中文
段落补充了项目用途、依赖安装、启动命令和 Pipe 示例说明，便于中文读者快速
定位运行入口。

## 可复用做法

后续发布前先读维护文档，再用 `git status -sb` 和 `git diff --stat`
识别混杂工作树。示例目录按用户指定白名单处理，避免把大体积参考资料或临时
输出带入远程仓库。

## 检查记录

已检查 README 与 `docs` 中的禁用句式、占位文本和来源缺口提示。
发布前还需运行语法编译和核心 smoke 检查，并确认最终推送只包含预期路径。
