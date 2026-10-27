# -*- coding: utf-8 -*-
"""
统一入口
========

双击 launch.bat 就是跑这个。它会：
  1. 语言选择（只问一次，之后记住）
  2. 检查 SDL2.dll —— 找到就报 OK，找不到只给官方地址，不自动下载
  3. 检查 Wuwa Tappo 在不在跑
  4. 启动托盘程序

    python src\\launcher.py              # 正常流程
    python src\\launcher.py --lang       # 重新选语言
    python src\\launcher.py --check      # 只检查环境，不启动
    python src\\launcher.py --console    # 控制台模式跑桥接（不进托盘）
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import i18n  # noqa: E402
from i18n import ROOT, t, fix_console_encoding, init_lang  # noqa: E402

# SDL 只提供地址，不在脚本里下载 —— 官方下载速度因人而异，交给用户自己决定
SDL_URL = "https://github.com/libsdl-org/SDL/releases"
SDL_NAMES = ("SDL2.dll", "SDL3.dll")


def find_sdl() -> str | None:
    """用户手动放的两个位置：sdl_runtime\\ 和仓库根目录。"""
    for d in (os.path.join(ROOT, "sdl_runtime"), ROOT):
        for n in SDL_NAMES:
            p = os.path.join(d, n)
            if os.path.exists(p) and os.path.getsize(p) > 100_000:
                return p
    return None


def tappo_running() -> bool:
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process -Name '*tappo*','*wuwa*','*wuwu*' "
             "-ErrorAction SilentlyContinue | Measure-Object).Count"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="ignore")
        return (out.stdout or "").strip().isdigit() and int(out.stdout.strip()) > 0
    except Exception:
        return False


def pythonw() -> tuple[str, int]:
    """返回 (解释器路径, creationflags)。

    后台启动的关键：托盘必须是一个**独立于 cmd 窗口**的进程，
    否则关掉 cmd 会把它一起带走。两条路：

      1. pythonw.exe —— 本来就没有控制台，最干净
      2. python.exe + CREATE_NO_WINDOW —— 也不创建控制台窗口，
         进程独立于父 cmd，关窗口不受影响

    绝不能裸跑 python.exe（那样会挂在 cmd 下，关窗口即终止）。
    """
    CREATE_NO_WINDOW = 0x08000000

    exe = sys.executable
    d = os.path.dirname(exe)

    # 1) 同目录下的 pythonw.exe（绝大多数情况）
    cand = os.path.join(d, "pythonw.exe")
    if os.path.exists(cand):
        return cand, 0

    # 2) PATH 上的 pythonw.exe
    try:
        out = subprocess.run(["where", "pythonw"], capture_output=True,
                             text=True, timeout=15)
        for line in (out.stdout or "").strip().splitlines():
            p = line.strip()
            if p and os.path.exists(p):
                return p, 0
    except Exception:
        pass

    # 3) 只有 python.exe：加 CREATE_NO_WINDOW，照样脱离 cmd
    return exe, CREATE_NO_WINDOW


def section(title: str) -> None:
    print()
    print("-" * 60)
    print(f"  {title}")
    print("-" * 60)


def main() -> int:
    ap = argparse.ArgumentParser(description="Wuwa Tappo Gamepad Bridge launcher")
    ap.add_argument("--lang", action="store_true", help="重新选择语言")
    ap.add_argument("--check", action="store_true", help="只检查环境，不启动")
    ap.add_argument("--console", action="store_true", help="控制台模式跑桥接，不进托盘")
    ap.add_argument("--debug", action="store_true",
                    help="带控制台启动托盘，错误实时可见（排错用）")
    args = ap.parse_args()

    fix_console_encoding()
    init_lang(force_ask=args.lang)

    print()
    print("=" * 60)
    print(f"  {t('app.title')}")
    print("=" * 60)

    # ---- 1. SDL ----
    section("SDL2.dll")
    sdl = find_sdl()
    if sdl:
        print(f"  [{t('common.ok')}] {t('launch.sdl_found', path=sdl)}")
    else:
        print(f"  [{t('common.warn')}] {t('launch.sdl_missing')}")
        print()
        print(f"      {t('launch.sdl_url_title')} {t('launch.sdl_url')}")
        print(f"      {t('launch.sdl_pick')}")
        print()
        print(f"      {t('launch.sdl_where')}")
        print(f"        {os.path.join(ROOT, 'sdl_runtime')}")
        print(f"        {ROOT}")
        print()
        print(f"      {t('launch.sdl_continue')}")

    # ---- 2. Wuwa Tappo ----
    section("Wuwa Tappo")
    if tappo_running():
        print(f"  [{t('common.ok')}] {t('launch.tappo_running')}")
    else:
        print(f"  [{t('common.warn')}] {t('launch.tappo_missing')}")

    if args.check:
        print()
        return 0

    # ---- 3. 启动 ----
    if args.debug:
        # 用带控制台的 python.exe 跑托盘，错误直接打印在这里。
        # 托盘图标照常出现，只是错误不再被隐藏。
        print()
        print("=" * 60)
        print(f"  {t('debug.title')}")
        print("=" * 60)
        print()
        print(f"  {t('debug.intro1')}")
        print(f"  {t('debug.intro2')}")
        print()
        print(f"  {t('debug.hint1')}")
        print(f"  {t('debug.hint2')}")
        print()
        print("-" * 60)
        print()
        rc = subprocess.call([sys.executable, os.path.join(_SRC, "tray_app.py")], cwd=ROOT)
        print()
        print("-" * 60)
        print(f"  {t('debug.exited')}")
        print(f"  {t('debug.log_at')} {os.path.join(ROOT, 'bridge.log')}")
        print("-" * 60)
        print()
        print(f"  {t('debug.is_debug_only')}")
        print(f"  {t('debug.use_launch')}")
        print()
        try:
            input(f"  {t('common.press_enter')} ...")
        except (EOFError, KeyboardInterrupt):
            pass
        return rc

    if args.console:
        section(t("app.title"))
        print(f"  {t('launch.nothing_happened')}")
        print()
        rc = subprocess.call([sys.executable, os.path.join(_SRC, "gamepad_bridge.py"),
                              "--send-mode", "post"], cwd=ROOT)
        return rc

    section(t("launch.starting_tray"))
    print(f"  {t('launch.tray_hint')}")
    print()

    pw, flags = pythonw()
    target = os.path.join(_SRC, "tray_app.py")
    proc = None
    try:
        proc = subprocess.Popen([pw, target], cwd=ROOT, creationflags=flags)
    except Exception as e:  # noqa:BLE001
        print(f"  [{t('common.error')}] {e}")
        return 1
    print(f"  {t('launch.detached')}  ({os.path.basename(pw)})")

    # 托盘是子进程的窗口，它崩了我们这边看不出来。等几秒看它是否还活着。
    import time
    time.sleep(3)
    if proc is not None and proc.poll() is not None:
        print()
        print(f"  [{t('common.error')}] {t('launch.tray_died')}")
        print(f"        {t('launch.tray_died_hint')}")
        print()
        print(f"        {t('launch.tray_died_log')}")
        print(f"          {os.path.join(ROOT, 'bridge.log')}")
        print()
        print(f"        {t('launch.tray_died_debug')}")
        print("          debug.bat")
        print()
        try:
            input(f"  {t('common.press_enter')} ...")
        except (EOFError, KeyboardInterrupt):
            pass
        return 1

    print()
    print("=" * 60)
    print(f"  {t('launch.running_bg')}")
    print("=" * 60)
    print()
    print(f"  {t('launch.can_close')}")
    print(f"  {t('launch.stop_hint')}")
    print(f"  {t('launch.log_hint')}")
    print()
    try:
        input(f"  {t('common.press_enter')} ...")
    except (EOFError, KeyboardInterrupt):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
