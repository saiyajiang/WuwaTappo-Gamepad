# -*- coding: utf-8 -*-
"""
三语支持：简体中文 / 繁體中文 / English
======================================

语言选择只在第一次运行时问一次，之后存进 lang.txt。
也可以随时改：托盘菜单里改，或跑 python src\\launcher.py --lang 。

控制台输出靠 SetConsoleOutputCP(65001) 切成 UTF-8，
这样中文/繁体不会变成乱码（Windows 控制台默认 GBK）。
"""

from __future__ import annotations

import ctypes
import os
import sys

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

_SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_SRC) if os.path.basename(_SRC).lower() == "src" else _SRC
LANG_FILE = os.path.join(ROOT, "lang.txt")

LANGS = ("sc", "tc", "en")            # 简体 / 繁體 / English
LANG_NAMES = {"sc": "简体中文", "tc": "繁體中文", "en": "English"}

_current = {"code": "sc"}


# ---------------------------------------------------------------------------
# Windows 控制台代码页：必须切成 UTF-8，否则中文输出是乱码
# ---------------------------------------------------------------------------

def fix_console_encoding() -> None:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if sys.platform.startswith("win"):
        try:
            k32 = ctypes.windll.kernel32
            k32.SetConsoleOutputCP(65001)
            k32.SetConsoleCP(65001)
        except Exception:
            pass


# pythonw 下没有 stdout，全部丢进日志文件
if sys.stdout is None:
    try:
        sys.stdout = sys.stderr = open(os.path.join(ROOT, "bridge.log"), "a",
                                       encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = sys.stderr = open(os.devnull, "w")


# ---------------------------------------------------------------------------
# 文案表
# ---------------------------------------------------------------------------

S = {
    # ---------- 通用 ----------
    "app.title": {
        "sc": "Wuwa Tappo · 手柄桥接",
        "tc": "Wuwa Tappo · 手把橋接",
        "en": "Wuwa Tappo · Gamepad Bridge",
    },
    "common.ok": {"sc": "正常", "tc": "正常", "en": "OK"},
    "common.warn": {"sc": "注意", "tc": "注意", "en": "Note"},
    "common.error": {"sc": "错误", "tc": "錯誤", "en": "Error"},
    "common.skip": {"sc": "跳过", "tc": "跳過", "en": "Skip"},
    "common.press_enter": {"sc": "按回车继续", "tc": "按 Enter 繼續", "en": "Press Enter"},
    "common.done": {"sc": "完成", "tc": "完成", "en": "Done"},
    "common.cancel": {"sc": "已取消", "tc": "已取消", "en": "Cancelled"},

    # ---------- 语言选择 ----------
    "lang.title": {
        "sc": "选择语言 / 選擇語言 / Select language",
        "tc": "选择语言 / 選擇語言 / Select language",
        "en": "选择语言 / 選擇語言 / Select language",
    },
    "lang.prompt": {
        "sc": "输入序号后回车",
        "tc": "輸入編號後按 Enter",
        "en": "Type a number and press Enter",
    },
    "lang.saved": {
        "sc": "语言已保存，下次不再询问。想改随时运行：python src\\launcher.py --lang",
        "tc": "語言已儲存，下次不再詢問。想修改請執行：python src\\launcher.py --lang",
        "en": "Language saved. To change it later: python src\\launcher.py --lang",
    },
    "lang.current": {
        "sc": "当前语言",
        "tc": "目前語言",
        "en": "Current language",
    },

    # ---------- 启动器 ----------
    "launch.python_missing": {
        "sc": "没找到 Python。请到 https://www.python.org 安装 3.10 以上版本，"
              "安装时务必勾选 \"Add python.exe to PATH\"。",
        "tc": "找不到 Python。請到 https://www.python.org 安裝 3.10 以上版本，"
              "安裝時務必勾選 \"Add python.exe to PATH\"。",
        "en": "Python not found. Install 3.10+ from https://www.python.org and "
              "make sure to tick \"Add python.exe to PATH\".",
    },
    "launch.sdl_found": {
        "sc": "已找到 SDL 运行时：{path}\n      已启用广谱手柄支持（Xbox / PS / Switch / 八位堂）。",
        "tc": "已找到 SDL 執行檔：{path}\n      已啟用手把廣泛支援（Xbox / PS / Switch / 8BitDo）。",
        "en": "SDL runtime found: {path}\n      Broad gamepad support enabled "
              "(Xbox / PS / Switch / 8BitDo).",
    },
    "launch.sdl_missing": {
        "sc": "没找到 SDL2.dll —— 可选，但 PS / Switch / 八位堂手柄需要它。",
        "tc": "找不到 SDL2.dll —— 選用，但 PS / Switch / 8BitDo 手把需要它。",
        "en": "SDL2.dll not found - optional, but required for PS / Switch / 8BitDo pads.",
    },
    "launch.sdl_url_title": {
        "sc": "官方下载地址：",
        "tc": "官方下載網址：",
        "en": "Official download:",
    },
    "launch.sdl_url": {
        "sc": "https://github.com/libsdl-org/SDL/releases",
        "tc": "https://github.com/libsdl-org/SDL/releases",
        "en": "https://github.com/libsdl-org/SDL/releases",
    },
    "launch.sdl_pick": {
        "sc": "取最新版的 SDL2-2.xx.x-win32-x64.zip（VC，64 位）",
        "tc": "下載最新版的 SDL2-2.xx.x-win32-x64.zip（VC，64 位元）",
        "en": "Grab the latest SDL2-2.xx.x-win32-x64.zip (VC, 64-bit)",
    },
    "launch.sdl_where": {
        "sc": "把解压出的 SDL2.dll 放进下面任一位置：",
        "tc": "將解壓出來的 SDL2.dll 放進以下任一位置：",
        "en": "Put the extracted SDL2.dll in either of these:",
    },
    "launch.sdl_continue": {
        "sc": "不装也能继续：会自动退回系统自带的 XInput，Xbox 系手柄正常工作。\n"
              "      以后补上 DLL 再跑一次本程序即可，无需其他改动。",
        "tc": "不裝也能繼續：會自動改用系統內建的 XInput，Xbox 系列手把可正常使用。\n"
              "      日後補上 DLL 再執行一次即可，不需其他設定。",
        "en": "You can continue without it: falls back to the system XInput, "
              "which works for Xbox-family pads.\n"
              "      Drop the DLL in later and run this again - nothing else to change.",
    },
    "launch.tappo_running": {
        "sc": "Wuwa Tappo 正在运行。",
        "tc": "Wuwa Tappo 正在執行。",
        "en": "Wuwa Tappo is running.",
    },
    "launch.tappo_missing": {
        "sc": "没检测到 Wuwa Tappo —— 请先启动它，否则直投模式找不到窗口。",
        "tc": "沒偵測到 Wuwa Tappo —— 請先啟動它，否則直投模式找不到視窗。",
        "en": "Wuwa Tappo is not running - start it first, otherwise the "
              "post channel cannot find its window.",
    },
    "launch.starting_tray": {
        "sc": "正在启动托盘程序 ...",
        "tc": "正在啟動托盤程式 ...",
        "en": "Starting the tray app ...",
    },
    "launch.tray_hint": {
        "sc": "托盘图标用法：左键双击 = 暂停/恢复，右键 = 菜单。\n"
              "      图标可能被 Windows 折进任务栏的 ∧ 里，去那里拖出来。",
        "tc": "托盤圖示用法：左鍵雙擊 = 暫停/恢復，右鍵 = 選單。\n"
              "      圖示可能被 Windows 收進工作列的 ∧ 裡，去那裡拖出來。",
        "en": "Tray icon: left double-click = pause/resume, right-click = menu.\n"
              "      Windows may hide it under the taskbar's ^ arrow - drag it out.",
    },
    "launch.detached": {
        "sc": "托盘程序已作为独立进程启动",
        "tc": "托盤程式已作為獨立行程啟動",
        "en": "Tray app started as an independent process",
    },
    "launch.running_bg": {
        "sc": "托盘程序正在后台运行",
        "tc": "托盤程式正在背景執行",
        "en": "Tray app is running in the background",
    },
    "launch.can_close": {
        "sc": "可以关闭这个窗口了 —— 它关不掉后台的托盘程序。",
        "tc": "可以關閉這個視窗了 —— 它關不掉背景的托盤程式。",
        "en": "You can close this window - it will NOT stop the background tray app.",
    },
    "launch.stop_hint": {
        "sc": "要彻底停止：运行 stop.bat，或托盘菜单 → 退出。",
        "tc": "要徹底停止：執行 stop.bat，或托盤選單 → 結束。",
        "en": "To stop it completely: run stop.bat, or tray menu -> Exit.",
    },
    "launch.log_hint": {
        "sc": "后台发生什么都不显示在窗口里，都写进 bridge.log。",
        "tc": "背景發生什麼都不顯示在視窗裡，都寫進 bridge.log。",
        "en": "Nothing shows here once in background - it all goes to bridge.log.",
    },
    "debug.is_debug_only": {
        "sc": "注意：这是排错模式，托盘程序挂在这个窗口下，关掉窗口它就会停。",
        "tc": "注意：這是除錯模式，托盤程式掛在這個視窗下，關掉視窗它就會停。",
        "en": "Note: this is debug mode - the tray app lives under this window, "
              "so closing it stops the app.",
    },
    "debug.use_launch": {
        "sc": "日常使用请运行 launch.bat，那个是真正后台运行，关窗口不受影响。",
        "tc": "日常使用請執行 launch.bat，那才是真正的背景執行，關視窗不受影響。",
        "en": "For everyday use run launch.bat - that one truly runs in the "
              "background and survives closing the window.",
    },
    "debug.title": {
        "sc": "排错模式（托盘程序 · 带控制台）",
        "tc": "除錯模式（托盤程式 · 含主控台）",
        "en": "Debug mode (tray app, with console)",
    },
    "debug.intro1": {
        "sc": "用带控制台的 Python 启动托盘，所有错误直接显示在这里。",
        "tc": "用含主控台的 Python 啟動托盤，所有錯誤直接顯示在這裡。",
        "en": "Starts the tray with a console Python, so every error shows here.",
    },
    "debug.intro2": {
        "sc": "托盘图标照常出现 —— 只是错误不再被隐藏。",
        "tc": "托盤圖示照常出現 —— 只是錯誤不再被隱藏。",
        "en": "The tray icon still appears - errors are just no longer hidden.",
    },
    "debug.hint1": {
        "sc": "窗口立刻关闭 = 程序崩溃，看上面的报错。",
        "tc": "視窗立刻關閉 = 程式崩潰，請看上方的錯誤。",
        "en": "Window closes instantly = crash. Read the error above.",
    },
    "debug.hint2": {
        "sc": "窗口保持打开 = 正常运行，去任务栏找图标（可能被收进 ∧）。",
        "tc": "視窗保持開啟 = 正常執行，去工作列找圖示（可能被收進 ∧）。",
        "en": "Window stays open = running fine. Find the icon in the taskbar "
              "(may be tucked under ^).",
    },
    "debug.exited": {
        "sc": "托盘程序已退出。上面的内容说明了原因。",
        "tc": "托盤程式已結束。上方的內容說明了原因。",
        "en": "Tray app exited. The output above explains why.",
    },
    "debug.log_at": {
        "sc": "完整堆栈也追加在：",
        "tc": "完整堆疊也附加在：",
        "en": "Full traceback also appended to:",
    },
    "launch.tray_died": {
        "sc": "托盘程序启动后立刻退出了（图标不会出现）。",
        "tc": "托盤程式啟動後立刻結束了（圖示不會出現）。",
        "en": "The tray app exited immediately (no icon will appear).",
    },
    "launch.tray_died_hint": {
        "sc": "常见原因：已有实例占着互斥量、Python 缺少依赖、或托盘图标创建失败。",
        "tc": "常見原因：已有實例占用互斥量、Python 缺少依賴、或托盤圖示建立失敗。",
        "en": "Usual causes: another instance holding the mutex, missing dependency, "
              "or the tray icon failed to register.",
    },
    "launch.tray_died_log": {
        "sc": "详细堆栈写在日志里：",
        "tc": "詳細堆疊寫在記錄檔裡：",
        "en": "Full traceback is in the log:",
    },
    "launch.tray_died_debug": {
        "sc": "要看到实时错误，请运行：",
        "tc": "要看到即時錯誤，請執行：",
        "en": "To see errors live, run:",
    },
    "launch.nothing_happened": {
        "sc": "如果托盘图标没出现，请运行 launch_console.bat 查看错误。",
        "tc": "如果托盤圖示沒出現，請執行 launch_console.bat 查看錯誤。",
        "en": "If no tray icon appears, run launch_console.bat to see errors.",
    },

    # ---------- 桥接核心 ----------
    "bridge.backend": {"sc": "手柄后端", "tc": "手把後端", "en": "Gamepad backend"},
    "bridge.backend_xinput": {"sc": "XInput（系统自带）", "tc": "XInput（系統內建）",
                              "en": "XInput (built into Windows)"},
    "bridge.backend_sdl": {"sc": "SDL（独立 DLL）", "tc": "SDL（獨立 DLL）",
                           "en": "SDL (standalone DLL)"},
    "bridge.backend_pygame": {"sc": "SDL（pygame）", "tc": "SDL（pygame）",
                              "en": "SDL (pygame)"},
    "bridge.channel": {"sc": "发送通道", "tc": "傳送通道", "en": "Send channel"},
    "bridge.running": {
        "sc": "运行中，轮询 {hz}Hz。Ctrl+Alt+G 或手柄 Back+Start 暂停，Ctrl+C 退出。",
        "tc": "執行中，輪詢 {hz}Hz。Ctrl+Alt+G 或手把 Back+Start 暫停，Ctrl+C 結束。",
        "en": "Running at {hz}Hz. Ctrl+Alt+G or Back+Start on the pad to pause, Ctrl+C to quit.",
    },
    "bridge.stats": {
        "sc": "已发送敲击 {taps} 次，鼠标移动 {moves} 次，运行 {mins:.1f} 分钟",
        "tc": "已傳送敲擊 {taps} 次，滑鼠移動 {moves} 次，執行 {mins:.1f} 分鐘",
        "en": "{taps} taps, {moves} mouse moves sent, up for {mins:.1f} min",
    },
    "bridge.exit": {"sc": "本次累计敲击 {taps} 次",
                    "tc": "本次累計敲擊 {taps} 次",
                    "en": "{taps} taps this session"},
    "bridge.paused": {"sc": "已暂停", "tc": "已暫停", "en": "Paused"},
    "bridge.resumed": {"sc": "已恢复", "tc": "已恢復", "en": "Resumed"},
    "bridge.paused_pad": {"sc": "已暂停（Back + Start）", "tc": "已暫停（Back + Start）",
                          "en": "Paused (Back + Start)"},
    "bridge.no_sdl": {
        "sc": "找不到 SDL 运行时",
        "tc": "找不到 SDL 執行檔",
        "en": "SDL runtime not found",
    },
    "bridge.hint_sdl": {
        "sc": "想支持 PS / 八位堂等非 Xbox 手柄，请把 SDL2.dll 放进 sdl_runtime\\ 目录。",
        "tc": "想支援 PS / 8BitDo 等非 Xbox 手把，請把 SDL2.dll 放進 sdl_runtime\\ 目錄。",
        "en": "For PS / 8BitDo and other non-Xbox pads, drop SDL2.dll into sdl_runtime\\.",
    },
    "bridge.window_found": {"sc": "已定位到桌宠窗口", "tc": "已定位到桌寵視窗",
                            "en": "Pet window located"},
    "bridge.window_relocated": {
        "sc": "桌宠窗口已重新定位 → 0x{hwnd:X}",
        "tc": "桌寵視窗已重新定位 → 0x{hwnd:X}",
        "en": "Pet window relocated → 0x{hwnd:X}",
    },
    "bridge.window_lost": {
        "sc": "桌宠窗口不见了，等它回来（暂停投递）...",
        "tc": "桌寵視窗不見了，等它回來（暫停傳送）...",
        "en": "Pet window gone, waiting for it (delivery paused)...",
    },
    "bridge.probe_title": {
        "sc": "摇动摇杆、按按键，看下面的数值跳不跳。Ctrl+C 提前结束。",
        "tc": "搖動搖桿、按按鍵，看下面的數值會不會跳動。Ctrl+C 提前結束。",
        "en": "Move the sticks and press buttons - watch the numbers. Ctrl+C to stop early.",
    },
    "bridge.probe_connected": {"sc": "已连接", "tc": "已連線", "en": "Connected"},
    "bridge.probe_disconnected": {
        "sc": "未连接：没读到手柄，插上或换个后端试试",
        "tc": "未連線：讀不到手把，插上或換個後端試試",
        "en": "Not connected: no pad detected, plug it in or try another backend",
    },
    "bridge.probe_no_pad": {
        "sc": "全程没检测到手柄。排查顺序：",
        "tc": "全程沒有偵測到手把。排查順序：",
        "en": "No gamepad detected at all. Check in this order:",
    },
    "bridge.probe_hint1": {
        "sc": "1) 手柄确实插上了？蓝牙手柄建议插线（蓝牙下 HID 报告格式常不同）",
        "tc": "1) 手把確實插上了？藍牙手把建議插線（藍牙下 HID 報告格式常不同）",
        "en": "1) Is the pad actually plugged in? Bluetooth pads often work better wired "
              "(HID reports differ over BT)",
    },
    "bridge.probe_hint2": {
        "sc": "2) 在 joy.cpl（游戏控制器设置）里能看到它吗？",
        "tc": "2) 在 joy.cpl（遊戲控制器設定）裡看得到它嗎？",
        "en": "2) Does it show up in joy.cpl (Game Controllers)?",
    },
    "bridge.probe_hint3": {
        "sc": "3) PS / 八位堂 / Switch 手柄需要 SDL2.dll，见 sdl_runtime\\ 里的说明",
        "tc": "3) PS / 8BitDo / Switch 手把需要 SDL2.dll，詳見 sdl_runtime\\ 裡的說明",
        "en": "3) PS / 8BitDo / Switch pads need SDL2.dll - see the note in sdl_runtime\\",
    },
    "bridge.probe_hint4": {
        "sc": "4) 还是不行就换 XInput 后端（Xbox 系手柄专用，零依赖）",
        "tc": "4) 還是不行就換 XInput 後端（Xbox 系列手把專用，零依賴）",
        "en": "4) Otherwise switch to the XInput backend (Xbox-family pads, zero deps)",
    },
    "bridge.dry_run": {"sc": "空跑模式：不会真的发送任何键鼠事件",
                       "tc": "空跑模式：不會真的傳送任何鍵鼠事件",
                       "en": "Dry run: no input is actually sent"},
    "bridge.dup_instance": {
        "sc": "已经有一个实例在跑了，这次不重复启动。",
        "tc": "已經有一個實例在執行，這次不重複啟動。",
        "en": "An instance is already running - not starting a second one.",
    },
    "bridge.dup_hint": {
        "sc": "要强制再开一个加 --allow-multiple；要停掉旧的请运行 stop.bat",
        "tc": "要強制再開一個請加 --allow-multiple；要停掉舊的請執行 stop.bat",
        "en": "Force another with --allow-multiple; stop the old one via stop.bat",
    },

    # ---------- 托盘 ----------
    "tray.win_only": {
        "sc": "托盘控制器只能在 Windows 上运行。",
        "tc": "托盤程式只能在 Windows 上執行。",
        "en": "The tray app only runs on Windows.",
    },
    "tray.menu.pause": {"sc": "暂停", "tc": "暫停", "en": "Pause"},
    "tray.menu.resume": {"sc": "恢复", "tc": "恢復", "en": "Resume"},
    "tray.menu.channel": {"sc": "发送通道", "tc": "傳送通道", "en": "Send channel"},
    "tray.menu.post": {"sc": "直投桌宠窗口（推荐，最小化也有效）",
                       "tc": "直投桌寵視窗（推薦，最小化也有效）",
                       "en": "Post to pet window (recommended, works while minimized)"},
    "tray.menu.sendinput": {"sc": "系统级 SendInput（需桌宠在前台）",
                            "tc": "系統級 SendInput（需桌寵在前景）",
                            "en": "System SendInput (pet must be focused)"},
    "tray.menu.backend": {"sc": "手柄后端", "tc": "手把後端", "en": "Gamepad backend"},
    "tray.menu.auto": {"sc": "自动（挑最好的）", "tc": "自動（挑最好的）",
                       "en": "Auto (pick the best)"},
    "tray.menu.sdl_dll": {"sc": "独立 SDL.dll", "tc": "獨立 SDL.dll",
                          "en": "Standalone SDL.dll"},
    "tray.menu.pygame": {"sc": "pygame 的 SDL", "tc": "pygame 的 SDL", "en": "pygame's SDL"},
    "tray.menu.xinput": {"sc": "系统 XInput", "tc": "系統 XInput", "en": "System XInput"},
    "tray.menu.probe": {"sc": "探测手柄", "tc": "偵測手把", "en": "Probe gamepad"},
    "tray.menu.reload": {"sc": "重载配置", "tc": "重新載入設定", "en": "Reload config"},
    "tray.menu.relocate": {"sc": "重新定位桌宠窗口", "tc": "重新定位桌寵視窗",
                           "en": "Relocate pet window"},
    "tray.menu.config": {"sc": "打开配置 config.json", "tc": "開啟設定 config.json",
                         "en": "Open config.json"},
    "tray.menu.log": {"sc": "打开日志 bridge.log", "tc": "開啟記錄 bridge.log",
                      "en": "Open bridge.log"},
    "tray.menu.sdl_help": {"sc": "SDL2.dll 去哪下", "tc": "SDL2.dll 去哪下載",
                           "en": "Where to get SDL2.dll"},
    "tray.menu.language": {"sc": "语言 / 語言 / Language", "tc": "语言 / 語言 / Language",
                           "en": "语言 / 語言 / Language"},
    "tray.menu.autorun": {"sc": "开机自启", "tc": "開機自啟", "en": "Start with Windows"},
    "tray.menu.about": {"sc": "关于", "tc": "關於", "en": "About"},
    "tray.menu.exit": {"sc": "退出", "tc": "結束", "en": "Exit"},
    "tray.status.running": {"sc": "运行中", "tc": "執行中", "en": "Running"},
    "tray.status.paused": {"sc": "已暂停", "tc": "已暫停", "en": "Paused"},
    "tray.status.stopped": {"sc": "未启动", "tc": "未啟動", "en": "Not started"},
    "tray.tip": {
        "sc": "Wuwa Tappo 手柄桥接 · {state} · 已敲击 {taps}",
        "tc": "Wuwa Tappo 手把橋接 · {state} · 已敲擊 {taps}",
        "en": "Wuwa Tappo Gamepad Bridge · {state} · {taps} taps",
    },
    "tray.taps_line": {
        "sc": "已敲击 {taps} 次 · 鼠标移动 {moves} 次",
        "tc": "已敲擊 {taps} 次 · 滑鼠移動 {moves} 次",
        "en": "{taps} taps · {moves} mouse moves",
    },
    "tray.err.create_window": {
        "sc": "创建托盘窗口失败",
        "tc": "建立托盤視窗失敗",
        "en": "Failed to create the tray window",
    },
    "tray.err.icon": {
        "sc": "添加托盘图标失败",
        "tc": "新增托盤圖示失敗",
        "en": "Failed to add the tray icon",
    },
    "tray.headless1": {
        "sc": "托盘图标建不出来，改为无界面模式运行。",
        "tc": "托盤圖示建不出來，改為無介面模式執行。",
        "en": "Tray icon unavailable - running headless instead.",
    },
    "tray.headless2": {
        "sc": "手柄功能完全正常，只是没有托盘菜单。",
        "tc": "手把功能完全正常，只是沒有托盤選單。",
        "en": "Gamepad support works fully - just no tray menu.",
    },
    "tray.headless3": {
        "sc": "暂停仍可用（手柄 Back+Start 或 Ctrl+Alt+G），退出请按 Ctrl+C 或运行 stop.bat。",
        "tc": "暫停仍可使用（手把 Back+Start 或 Ctrl+Alt+G），結束請按 Ctrl+C 或執行 stop.bat。",
        "en": "Pause still works (Back+Start on the pad, or Ctrl+Alt+G). "
              "To quit: Ctrl+C or run stop.bat.",
    },
    "tray.window_fallback": {
        "sc": "已改用隐藏窗口（功能不受影响）",
        "tc": "已改用隱藏視窗（功能不受影響）",
        "en": "Fell back to a hidden window (functionality unaffected)",
    },
    "tray.err.no_window": {"sc": "没找到桌宠窗口", "tc": "找不到桌寵視窗",
                           "en": "Pet window not found"},
    "tray.err.backend": {"sc": "后端启动失败：{err}", "tc": "後端啟動失敗：{err}",
                         "en": "Backend failed: {err}"},
    "tray.started": {"sc": "托盘已启动。左键双击=暂停/恢复，右键=菜单。",
                     "tc": "托盤已啟動。左鍵雙擊=暫停/恢復，右鍵=選單。",
                     "en": "Tray started. Left double-click = pause/resume, right-click = menu."},
    "tray.dup": {
        "sc": "已经有一个实例在托盘里了。\n\n先退出旧的（右键托盘图标 → 退出），再启动。",
        "tc": "已經有一個實例在托盤裡了。\n\n請先結束舊的（右鍵托盤圖示 → 結束），再啟動。",
        "en": "An instance is already in the tray.\n\nExit the old one first "
              "(right-click the icon → Exit), then start again.",
    },
    "tray.about": {
        "sc": "Wuwa Tappo 手柄桥接  v{version}\n"
              "作者：{author}\n"
              "许可：{license}\n\n"
              "左键双击托盘图标 = 暂停 / 恢复\n"
              "右键 = 菜单\n\n"
              "手柄 Back+Start 长按 1 秒也能暂停，Ctrl+Alt+G 同样有效。\n"
              "后台运行，关掉启动窗口不会停止它。",
        "tc": "Wuwa Tappo 手把橋接  v{version}\n"
              "作者：{author}\n"
              "授權：{license}\n\n"
              "左鍵雙擊托盤圖示 = 暫停 / 恢復\n"
              "右鍵 = 選單\n\n"
              "手把 Back+Start 長按 1 秒也能暫停，Ctrl+Alt+G 同樣有效。\n"
              "背景執行，關閉啟動視窗不會停止它。",
        "en": "Wuwa Tappo Gamepad Bridge  v{version}\n"
              "Author: {author}\n"
              "License: {license}\n\n"
              "Left double-click the tray icon = pause / resume\n"
              "Right-click = menu\n\n"
              "Back+Start on the pad for 1s also pauses, as does Ctrl+Alt+G.\n"
              "Runs in the background - closing the launcher window "
              "does not stop it.",
    },
    "tray.author_unset": {
        "sc": "作者和仓库地址还是占位符，请编辑 src\\project.py 填成你自己的。",
        "tc": "作者與倉庫網址仍是佔位符，請編輯 src\\project.py 填成你自己的。",
        "en": "Author and repo URL are still placeholders - "
              "edit src\\project.py and fill in your own.",
    },
    "tray.about_url": {
        "sc": "项目主页（菜单里点击可直接打开）：",
        "tc": "專案首頁（選單中點擊可直接開啟）：",
        "en": "Project home (click the menu item to open):",
    },
    "tray.menu.repo": {
        "sc": "项目主页（打开 GitHub）",
        "tc": "專案首頁（開啟 GitHub）",
        "en": "Project home (open GitHub)",
    },
    "tray.menu.notice": {
        "sc": "开源许可与第三方组件",
        "tc": "開源授權與第三方元件",
        "en": "Licenses & third-party components",
    },
    "tray.repo_unset": {
        "sc": "还没填仓库地址。\n\n"
              "请编辑 src\\project.py 里的 GITHUB_URL，改成你自己的地址。",
        "tc": "尚未填寫倉庫網址。\n\n"
              "請編輯 src\\project.py 裡的 GITHUB_URL，改成你自己的網址。",
        "en": "Repository URL is not set.\n\n"
              "Edit GITHUB_URL in src\\project.py and put your own address.",
    },
    "tray.repo_unset_short": {
        "sc": "（未填写 —— 请在 src\\project.py 里设置 GITHUB_URL）",
        "tc": "（未填寫 —— 請在 src\\project.py 裡設定 GITHUB_URL）",
        "en": "(not set - configure GITHUB_URL in src\\project.py)",
    },
    "tray.repo_open_failed": {
        "sc": "打不开浏览器，请手动复制地址：",
        "tc": "無法開啟瀏覽器，請手動複製網址：",
        "en": "Could not open a browser. Copy the address manually:",
    },
    "tray.autorun_on": {"sc": "开机自启：已开启", "tc": "開機自啟：已開啟",
                        "en": "Auto-start: enabled"},
    "tray.autorun_off": {"sc": "开机自启：已关闭", "tc": "開機自啟：已關閉",
                         "en": "Auto-start: disabled"},
    "tray.restart_needed": {
        "sc": "语言已切换，需重启本程序生效。",
        "tc": "語言已切換，需重新啟動本程式才會生效。",
        "en": "Language switched. Restart the app for it to take effect.",
    },
    "tray.sdl_help": {
        "sc": "本仓库不附带任何 DLL。请自行下载 SDL2.dll：\n\n"
              "  https://github.com/libsdl-org/SDL/releases\n\n"
              "取最新版的 SDL2-2.xx.x-win32-x64.zip（VC，64 位），\n"
              "解压出 SDL2.dll，放进 sdl_runtime\\ 或仓库根目录。\n\n"
              "不放也能用（Xbox 手柄走系统 XInput），\n"
              "但 PS / Switch / 八位堂手柄需要它。",
        "tc": "本專案不附帶任何 DLL。請自行下載 SDL2.dll：\n\n"
              "  https://github.com/libsdl-org/SDL/releases\n\n"
              "下載最新版的 SDL2-2.xx.x-win32-x64.zip（VC，64 位元），\n"
              "解壓出 SDL2.dll，放進 sdl_runtime\\ 或專案根目錄。\n\n"
              "不放也能用（Xbox 手把走系統 XInput），\n"
              "但 PS / Switch / 8BitDo 手把需要它。",
        "en": "This repo ships no DLLs. Get SDL2.dll yourself:\n\n"
              "  https://github.com/libsdl-org/SDL/releases\n\n"
              "Take the latest SDL2-2.xx.x-win32-x64.zip (VC, 64-bit),\n"
              "extract SDL2.dll, put it in sdl_runtime\\ or the repo root.\n\n"
              "Optional - Xbox pads work without it via system XInput,\n"
              "but PS / Switch / 8BitDo need it.",
    },

    # ---------- 诊断 ----------
    "diag.unity": {
        "sc": "窗口类名是 UnityWndClass → 确认是 Unity standalone。\n"
              "    Unity 的 Input 系统在窗口失焦时会停止接收，\n"
              "    这是「最小化就失效」最常见的成因。",
        "tc": "視窗類別名稱是 UnityWndClass → 確認是 Unity standalone。\n"
              "    Unity 的 Input 系統在視窗失焦時會停止接收，\n"
              "    這是「最小化就失效」最常見的成因。",
        "en": "Window class is UnityWndClass -> confirmed Unity standalone.\n"
              "    Unity's Input system stops receiving when unfocused,\n"
              "    the usual cause of \"stops working when minimized\".",
    },
    "diag.win_only": {
        "sc": "这个脚本只能在 Windows 上运行。",
        "tc": "這個腳本只能在 Windows 上執行。",
        "en": "This script only runs on Windows.",
    },
    "diag.title": {"sc": "Wuwa Tappo 输入诊断", "tc": "Wuwa Tappo 輸入診斷",
                   "en": "Wuwa Tappo Input Diagnostics"},
    "diag.no_proc": {
        "sc": "没找到。请先启动 Wuwa Tappo 再运行本脚本。",
        "tc": "找不到。請先啟動 Wuwa Tappo 再執行本腳本。",
        "en": "Not found. Start Wuwa Tappo first, then run this.",
    },
    "diag.no_window": {
        "sc": "这个进程没有顶层窗口（可能纯托盘运行）。",
        "tc": "這個行程沒有最上層視窗（可能純托盤執行）。",
        "en": "This process has no top-level window (tray-only).",
    },
    "diag.no_window_hint": {
        "sc": "这种情况下直投通道用不了，只能靠 SendInput。",
        "tc": "這種情況下直投通道無法使用，只能靠 SendInput。",
        "en": "In that case the post channel is unavailable - SendInput only.",
    },
    "diag.verdict_post": {
        "sc": "用直投模式跑桥接，不受最小化和焦点影响：",
        "tc": "用直投模式執行橋接，不受最小化與焦點影響：",
        "en": "Use post mode - immune to minimization and focus loss:",
    },
    "diag.verdict_sendinput": {
        "sc": "保持默认 SendInput，但桌宠窗口必须保持焦点：",
        "tc": "維持預設 SendInput，但桌寵視窗必須保持焦點：",
        "en": "Keep SendInput, but the pet window must stay focused:",
    },
    "diag.verdict_both": {
        "sc": "两条通道都通，用 both 更稳：",
        "tc": "兩條通道都通，用 both 更穩：",
        "en": "Both channels work - 'both' is the safest:",
    },
    "diag.test_hint": {
        "sc": "跑 diagnose.bat 实测哪条通道有效。",
        "tc": "請執行 diagnose.bat 實測哪條通道有效。",
        "en": "Run diagnose.bat to test which channel actually works.",
    },
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def set_lang(code: str) -> None:
    if code in LANGS:
        _current["code"] = code


def get_lang() -> str:
    return _current["code"]


def t(key: str, **kw) -> str:
    """取当前语言的文案。找不到就返回 key 本身，保证不炸。"""
    entry = S.get(key)
    if not entry:
        return f"[{key}]" + (f" {kw}" if kw else "")
    s = entry.get(_current["code"]) or entry.get("en") or next(iter(entry.values()))
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def save_lang(code: str) -> None:
    try:
        with open(LANG_FILE, "w", encoding="utf-8") as f:
            f.write(code)
    except Exception:
        pass


def load_lang() -> str | None:
    try:
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip().lower()
        return v if v in LANGS else None
    except Exception:
        return None


def init_lang(force_ask: bool = False) -> str:
    """启动时调用：读已保存的语言，没有就问一次。"""
    saved = load_lang()
    if saved and not force_ask:
        set_lang(saved)
        return saved

    fix_console_encoding()
    print()
    print("=" * 60)
    print(t("lang.title"))
    print("=" * 60)
    for i, code in enumerate(LANGS, 1):
        print(f"  [{i}] {LANG_NAMES[code]}")
    print()
    print(t("lang.prompt"))

    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        raw = ""

    code = None
    if raw in ("1", "2", "3"):
        code = LANGS[int(raw) - 1]
    elif raw.lower() in LANGS:
        code = raw.lower()
    if code is None:
        code = "sc"
    set_lang(code)
    save_lang(code)
    print()
    print(t("lang.saved"))
    print()
    return code
