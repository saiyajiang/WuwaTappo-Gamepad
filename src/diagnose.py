# -*- coding: utf-8 -*-
"""
Wuwa Tappo · 输入诊断
=====================

回答一个问题：为什么最小化之后桥接就失效了。

会报告：
  · Wuwa Tappo 的进程与它的窗口（句柄 / 类名 / 标题 / 可见 / 是否最小化）
  · 当前前台窗口是谁
  · Unity 判定（Unity standalone 的窗口类名是 UnityWndClass）
  · 两种发送通道的实际测试，让你用眼睛确认哪条有效

用法：
    python diagnose.py                # 只报告状态
    python diagnose.py --test         # 发送测试按键，观察桌宠有没有反应
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes

_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import i18n  # noqa: E402
from i18n import t, fix_console_encoding, load_lang, set_lang  # noqa: E402

fix_console_encoding()
_l = load_lang()
if _l:
    set_lang(_l)

if sys.platform != "win32":
    print(t("diag.win_only"))
    sys.exit(2)

u = ctypes.windll.user32
k = ctypes.windll.kernel32

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
VK_F13 = 0x7C
GWL_EXSTYLE = -20
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

u.EnumWindows.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u.IsIconic.argtypes = [wintypes.HWND]
u.IsWindowVisible.argtypes = [wintypes.HWND]
u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u.GetForegroundWindow.restype = wintypes.HWND
u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
u.GetWindowLongPtrW.restype = ctypes.c_void_p if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long


# ---------------------------------------------------------------------------
# 进程
# ---------------------------------------------------------------------------

def find_tappo_procs() -> list[tuple[int, str]]:
    ps = ("(Get-Process -Name '*tappo*','*wuwa*','*wuwu*' -ErrorAction SilentlyContinue "
          "| Where-Object {$_.Path} | Select-Object @{n='L';e={$_.Id.ToString() + '|' + $_.Path}} "
          "| Select-Object -ExpandProperty L) -join \"`n\"")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30,
                             encoding="utf-8", errors="ignore")
    except Exception:
        return []
    res = []
    for line in out.stdout.splitlines():
        if "|" not in line:
            continue
        pid, path = line.split("|", 1)
        try:
            res.append((int(pid), path.strip()))
        except ValueError:
            continue
    return res


# ---------------------------------------------------------------------------
# 窗口
# ---------------------------------------------------------------------------

class WinInfo:
    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.pid = 0
        pid = wintypes.DWORD(0)
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        self.pid = pid.value
        n = u.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(hwnd, buf, n + 1)
        self.title = buf.value
        cb = ctypes.create_unicode_buffer(256)
        u.GetClassNameW(hwnd, cb, 256)
        self.cls = cb.value
        self.visible = bool(u.IsWindowVisible(hwnd))
        self.iconic = bool(u.IsIconic(hwnd))
        r = wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        self.rect = (r.left, r.top, r.right - r.left, r.bottom - r.top)
        try:
            ex = u.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            self.topmost = bool(int(ex) & 0x00000008)          # WS_EX_TOPMOST
            self.toolwindow = bool(int(ex) & 0x00000080)       # WS_EX_TOOLWINDOW
            self.layered = bool(int(ex) & 0x00080000)          # WS_EX_LAYERED
            self.transparent = bool(int(ex) & 0x00000020)      # WS_EX_TRANSPARENT
        except Exception:
            self.topmost = self.toolwindow = self.layered = self.transparent = False


def enum_windows_for(pids: set[int]) -> list[WinInfo]:
    out: list[WinInfo] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_void_p)
    def cb(hwnd, _l):
        w = WinInfo(hwnd)
        if w.pid in pids:
            out.append(w)
        return True

    u.EnumWindows(cb, 0)
    return out


# ---------------------------------------------------------------------------
# 发送测试
# ---------------------------------------------------------------------------

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_ulonglong)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]


def send_via_sendinput(vk: int, hold: float = 0.04) -> None:
    """系统级：进全局输入队列，投递给当前前台窗口。"""
    def mk(flags):
        i = INPUT()
        i.type = INPUT_KEYBOARD
        i.ki.wVk = vk
        i.ki.dwFlags = flags
        return i
    arr = (INPUT * 1)(mk(0))
    u.SendInput(1, ctypes.byref(arr), ctypes.sizeof(INPUT))
    time.sleep(hold)
    arr = (INPUT * 1)(mk(KEYEVENTF_KEYUP))
    u.SendInput(1, ctypes.byref(arr), ctypes.sizeof(INPUT))


def send_via_postmessage(hwnd: int, vk: int, hold: float = 0.04) -> None:
    """直接投到目标窗口的消息队列。不需要焦点，窗口最小化也收得到。"""
    sc = u.MapVirtualKeyW(vk, 0) if hasattr(u, "MapVirtualKeyW") else (vk & 0xFF)
    down_l = 1 | (sc << 16)
    up_l = 1 | (sc << 16) | (1 << 30) | (1 << 31)
    u.PostMessageW(hwnd, WM_KEYDOWN, vk, down_l)
    time.sleep(hold)
    u.PostMessageW(hwnd, WM_KEYUP, vk, up_l)


# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Wuwa Tappo 输入诊断")
    ap.add_argument("--test", action="store_true", help="发送测试按键，观察桌宠反应")
    ap.add_argument("--hwnd", type=lambda x: int(x, 0), default=None, help="手动指定窗口句柄")
    args = ap.parse_args()

    print("=" * 68)
    print(t("diag.title"))
    print("=" * 68)

    # ---- 1. 进程 ----
    print("\n[1] 进程")
    procs = find_tappo_procs()
    if not procs:
        print("  " + t("diag.no_proc"))
        return 1
    for pid, path in procs:
        print(f"  PID {pid:<8} {path}")
    pids = {p for p, _ in procs}

    # ---- 2. 窗口 ----
    print("\n[2] 窗口")
    wins = enum_windows_for(pids)
    if not wins:
        print("  " + t("diag.no_window"))
        print("  " + t("diag.no_window_hint"))

    unity = False
    for w in wins:
        print(f"\n  hwnd=0x{w.hwnd:X}  pid={w.pid}")
        print(f"    类名 : {w.cls}")
        print(f"    标题 : {w.title or '(空)'}")
        print(f"    可见 : {'是' if w.visible else '否'}"
              f"   最小化: {'是' if w.iconic else '否'}")
        print(f"    位置 : {w.rect}  (left, top, w, h)")
        flags = [n for n, v in (("置顶", w.topmost), ("工具窗口(不在任务栏)", w.toolwindow),
                                ("分层/半透明", w.layered), ("鼠标穿透", w.transparent)) if v]
        print(f"    样式 : {'、'.join(flags) or '常规'}")
        if w.cls == "UnityWndClass":
            unity = True

    if unity:
        print()
        print("  " + t("diag.unity"))

    # ---- 3. 前台窗口 ----
    print("\n[3] 当前前台窗口（SendInput 的按键会投递到这里）")
    fg = u.GetForegroundWindow()
    w = WinInfo(fg)
    print(f"  hwnd=0x{w.hwnd:X}  类名={w.cls}")
    print(f"  标题={w.title[:70]}")
    fg_is_tappo = w.pid in pids
    print(f"  属于 Wuwa Tappo 吗：{'是' if fg_is_tappo else '否'}")
    if not fg_is_tappo:
        print("  → SendInput 的按键此刻是发给上面这个窗口的，不是发给桌宠。")
        print("    桌宠只有在用全局钩子 / Raw Input 监听时才能收到。")

    # ---- 4. 测试 ----
    target = args.hwnd or (wins[0].hwnd if wins else None)
    if args.test:
        print("\n[4] 发送测试（观察桌宠有没有拍一下）")
        if target:
            for i in (3, 2, 1):
                print(f"    {i} 秒后用 PostMessage(直接投给桌宠窗口) 发 F13 ...", end="\r")
                time.sleep(1)
            print("    → 已发 PostMessage，看桌宠动没动？" + " " * 20)
            send_via_postmessage(target, VK_F13)
            time.sleep(1.2)
            ans = input("    桌宠动了吗 (y/N)：").strip().lower()
            post_ok = ans.startswith("y")
        else:
            post_ok = False
            print("    没有可用窗口句柄，跳过 PostMessage 测试。")

        for i in (3, 2, 1):
            print(f"    {i} 秒后用 SendInput(系统级) 发 F13 ...", end="\r")
            time.sleep(1)
        print("    → 已发 SendInput，看桌宠动没动？" + " " * 22)
        send_via_sendinput(VK_F13)
        time.sleep(1.2)
        ans = input("    桌宠动了吗 (y/N)：").strip().lower()
        si_ok = ans.startswith("y")

        print("\n  结论：")
        print(f"    PostMessage(直投窗口)：{'有效' if post_ok else '无效'}")
        print(f"    SendInput(系统级)    ：{'有效' if si_ok else '无效'}")
        if post_ok and not si_ok:
            print("\n  " + t("diag.verdict_post"))
            print(f"    python gamepad_bridge.py --send-mode post --hwnd 0x{target:X}")
        elif si_ok and not post_ok:
            print("\n  " + t("diag.verdict_sendinput"))
            print("    python gamepad_bridge.py")
        elif post_ok and si_ok:
            print("\n  " + t("diag.verdict_both"))
            print(f"    python gamepad_bridge.py --send-mode both --hwnd 0x{target:X}")
        else:
            print("\n  → 两条都不通。多半是它自己被最小化/隐藏了，")
            print("    或者设置里开了「游戏模式」。先把桌宠窗口恢复可见再测。")
        return 0

    # ---- 建议 ----
    print("\n[4] 建议")
    if wins and wins[0].iconic:
        print("  · 桌宠窗口当前是最小化状态。BongoCat 系桌宠在最小化时普遍会暂停动画，")
        print("    先把它恢复显示再测。")
    if unity and not fg_is_tappo:
        print("  · 它是 Unity 且当前不是前台窗口 → 高度怀疑「失焦即停止接收」。")
        print(f"    跑 python diagnose.py --test 实测哪条通道有效。")
    if not wins:
        print("  · 没有窗口句柄可用，PostMessage 通道不可用，只能靠 SendInput。")
        print("    这时请确保桌宠本身是可见的（不能被最小化或一键隐藏）。")
    if target:
        print(f"\n  想直接用直投模式：")
        print(f"    python gamepad_bridge.py --send-mode post --hwnd 0x{target:X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
