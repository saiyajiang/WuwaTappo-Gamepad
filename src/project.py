# -*- coding: utf-8 -*-
"""
项目元信息
==========

托盘「关于」里显示的作者和仓库地址来自这里。
换作者或换仓库时改这两行即可，改完重启托盘程序生效。

Project meta - the About dialog reads AUTHOR and GITHUB_URL from here.
"""

AUTHOR = "saiyajiang"
GITHUB_URL = "https://github.com/saiyajiang/WuwaTappo-Gamepad"

PROJECT_NAME = "Wuwa Tappo Gamepad Bridge"
VERSION = "1.0.0"

# 本项目自身的许可证（第三方组件见 NOTICE.txt）
LICENSE_NAME = "MIT"

# 第三方 / 平台组件。这里只列运行时会用到的，不含可选 DLL。
THIRD_PARTY = (
    ("CPython", "Python 软件基金会", "PSF License"),
    ("SDL2（可选，用户自行下载）", "Sam Lantinga / SDL contributors", "zlib License"),
)

# 平台提供的公开 API（不属于"开源库"，但一并说明来源）
PLATFORM_APIS = (
    ("Win32 SendInput", "Microsoft Windows"),
    ("Win32 PostMessage", "Microsoft Windows"),
    ("Shell_NotifyIcon", "Microsoft Windows"),
    ("XInput", "Microsoft Windows"),
)


def is_placeholder() -> bool:
    """作者或地址还是占位符吗（用于启动时提醒）。"""
    return "your-name" in GITHUB_URL or "未填写" in AUTHOR
