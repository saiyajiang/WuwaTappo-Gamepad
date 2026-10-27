# -*- coding: utf-8 -*-
"""
Wuwa Tappo · 托盘控制器
=======================

把之前分开的几件事整合进一个托盘图标：
  · 桥接的启停、暂停/恢复
  · 通道切换（SendInput / Post，post 不受最小化和焦点影响）
  · 手柄后端切换（自动 / 独立SDL / pygame / XInput）
  · 探测手柄、重载配置、打开配置与日志
  · 开机自启开关、重新定位桌宠窗口

启动后没有控制台窗口，安静待在托盘里。左键双击 = 暂停/恢复，右键 = 菜单。

    python tray_app.py            # 有控制台（调试用）
    pythonw tray_app.py           # 无控制台，正式用法
    双击 tray_launcher.vbs         # 推荐，自动用 pythonw

托盘图标颜色：绿=运行中，橙=已暂停，红=出错/没找到手柄。
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SRC = os.path.dirname(os.path.abspath(__file__))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# 仓库根目录：配置和日志放这里，方便用户找
HERE = os.path.dirname(SRC) if os.path.basename(SRC).lower() == "src" else SRC

# pythonw 下 sys.stdout 是 None，print 会静默丢弃，开个日志文件兜底
if sys.stdout is None:
    try:
        sys.stdout = sys.stderr = open(os.path.join(HERE, "bridge.log"), "a",
                                       encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = sys.stderr = open(os.devnull, "w")

import project  # noqa: E402
from gamepad_bridge import (  # noqa: E402
    CONFIG_NAME, GamepadBridge, InputSender, build_backend, find_tappo_hwnd,
    load_config, ensure_single_instance, enable_file_log, LOG_NAME, app_root,
)
import i18n  # noqa: E402
from i18n import t, fix_console_encoding, load_lang, set_lang, save_lang, LANGS, LANG_NAMES  # noqa: E402

fix_console_encoding()

_lang = load_lang()
if _lang:
    set_lang(_lang)
HERE = app_root()

if sys.platform != "win32":
    print(t("tray.win_only"))
    sys.exit(2)

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
g32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32


# ---------------------------------------------------------------------------
# Win32 函数原型
#
# 这一段是必须的：64 位 Python 下 ctypes 默认把返回值当 32 位 int，
# HWND / HICON 这类指针会被截断（高 32 位丢失），表现为 CreateWindow
# "成功却返回 NULL"。逐个显式声明 argtypes / restype 才能正确传递。
# ---------------------------------------------------------------------------

def _bind() -> None:
    """给 Win32 函数显式声明 argtypes / restype。

    必须声明的原因：64 位 Python 下 ctypes 默认把返回值当 32 位 int，
    HWND / HICON 这类指针会被截断（高 32 位丢失），
    表现为 CreateWindowExW "其实成功了却返回 NULL"。

    每条都过 _b：单个原型声明失败只警告，不让程序在启动阶段崩掉。
    """
    def _b(name, fn, argtypes=None, restype=None):
        try:
            if argtypes is not None:
                fn.argtypes = argtypes
            if restype is not None:
                fn.restype = restype
        except Exception as e:  # noqa: BLE001
            print(f"[bind warn] {name}: {e}")

    k32.GetLastError.restype = wintypes.DWORD

    u32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u32.RegisterClassExW.restype = wintypes.ATOM

    u32.CreateWindowExW.argtypes = [
        wintypes.DWORD,      # dwExStyle
        wintypes.LPCWSTR,    # lpClassName
        wintypes.LPCWSTR,    # lpWindowName
        wintypes.DWORD,      # dwStyle
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,  # x,y,w,h
        wintypes.HWND,       # hWndParent
        wintypes.HMENU,      # hMenu
        wintypes.HINSTANCE,  # hInstance
        wintypes.LPVOID,     # lpParam
    ]
    u32.CreateWindowExW.restype = wintypes.HWND

    u32.DestroyWindow.argtypes = [wintypes.HWND]
    u32.DestroyWindow.restype = wintypes.BOOL

    u32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   wintypes.WPARAM, wintypes.LPARAM]
    u32.DefWindowProcW.restype = ctypes.c_long

    u32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND,
                                wintypes.UINT, wintypes.UINT]
    u32.GetMessageW.restype = wintypes.BOOL

    u32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    u32.TranslateMessage.restype = wintypes.BOOL

    u32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    u32.DispatchMessageW.restype = ctypes.c_long

    u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM]
    u32.PostMessageW.restype = wintypes.BOOL

    u32.PostQuitMessage.argtypes = [ctypes.c_int]

    u32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    u32.GetCursorPos.restype = wintypes.BOOL

    u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    u32.SetForegroundWindow.restype = wintypes.BOOL

    u32.CreatePopupMenu.restype = wintypes.HMENU
    u32.DestroyMenu.argtypes = [wintypes.HMENU]
    u32.DestroyMenu.restype = wintypes.BOOL
    u32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                ctypes.c_void_p, wintypes.LPCWSTR]
    u32.AppendMenuW.restype = wintypes.BOOL
    u32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                   ctypes.POINTER(wintypes.RECT)]
    u32.TrackPopupMenu.restype = wintypes.BOOL

    u32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p]
    u32.SetTimer.restype = ctypes.c_void_p
    u32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_void_p]
    u32.KillTimer.restype = wintypes.BOOL

    u32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    u32.MessageBoxW.restype = ctypes.c_int

    u32.IsWindow.argtypes = [wintypes.HWND]
    u32.IsWindow.restype = wintypes.BOOL

    u32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
    u32.EnumWindows.restype = wintypes.BOOL

    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    u32.GetWindowThreadProcessId.restype = wintypes.DWORD

    u32.GetDC.argtypes = [wintypes.HWND]
    u32.GetDC.restype = wintypes.HDC
    u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u32.ReleaseDC.restype = ctypes.c_int

    u32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                               ctypes.c_int, ctypes.c_int, wintypes.UINT]
    u32.LoadImageW.restype = wintypes.HANDLE

    g32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                     ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                     wintypes.DWORD]
    g32.CreateDIBSection.restype = wintypes.HBITMAP

    g32.CreateBitmap.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.UINT,
                                 wintypes.UINT, wintypes.LPVOID]
    g32.CreateBitmap.restype = wintypes.HBITMAP

    u32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
    u32.CreateIconIndirect.restype = wintypes.HICON

    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL

    _b("CreateIconFromResourceEx",
       u32.CreateIconFromResourceEx,
       [ctypes.c_char_p, wintypes.UINT, wintypes.BOOL, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, wintypes.UINT],
       wintypes.HICON)

    _b("ShellExecuteW",
       shell32.ShellExecuteW,
       [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int],
       wintypes.HINSTANCE)

# ---------------------------------------------------------------------------
# Win32 常量
# ---------------------------------------------------------------------------
WM_USER = 0x0400
WM_TRAY = WM_USER + 1
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_TIMER = 0x0113
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203
WM_LBUTTONUP = 0x0202

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x01, 0x02, 0x04

MF_STRING, MF_SEPARATOR, MF_GRAYED, MF_CHECKED = 0x00, 0x0800, 0x0001, 0x0008
TPM_LEFTALIGN, TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0000, 0x0002, 0x0100

HWND_MESSAGE = -3
COLOR_WINDOW = 5
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_DEFAULTSIZE = 0x0040

# 菜单命令 ID
ID_STATUS = 1000
ID_PAUSE = 1001
ID_MODE_SI, ID_MODE_POST = 1010, 1011
ID_BK_AUTO, ID_BK_SDLDLL, ID_BK_SDL, ID_BK_XINPUT = 1020, 1021, 1022, 1023
ID_PROBE, ID_RELOAD, ID_CONFIG, ID_LOG = 1030, 1031, 1032, 1033
ID_SDL_HELP, ID_LANG = 1034, 1035
ID_REPO, ID_NOTICE = 1036, 1037
ID_RELOCATE, ID_AUTORUN, ID_ABOUT, ID_EXIT = 1040, 1041, 1042, 1099

# 图标状态：run=黑 W / pause=灰 W / err=灰 W + 红点
ST_RUN, ST_PAUSE, ST_ERR = "run", "pause", "err"


# ---------------------------------------------------------------------------
# 结构
# ---------------------------------------------------------------------------

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HANDLE),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", POINT)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


# 结构体都定义完了，现在才绑定函数原型
try:
    _bind()
except Exception as e:  # noqa: BLE001
    print(f"[bind fatal] {e}")


# ---------------------------------------------------------------------------
# 图标绘制（纯 ctypes 画一个黑白的 W，不依赖 Pillow）
# ---------------------------------------------------------------------------

# W 由四段折线组成：\ / \ /  （起笔 -> 谷 -> 峰 -> 谷 -> 收笔）
_W_POINTS = ((6.0, 7.0), (11.0, 24.0), (16.0, 13.0), (21.0, 24.0), (26.0, 7.0))
_W_SEGS = [(_W_POINTS[i], _W_POINTS[i + 1]) for i in range(4)]

# 主体色 / 描边色 / 状态点（BGRA 顺序在写缓冲时再处理）
_ICON_INK = {"run": (16, 16, 16), "pause": (128, 128, 128)}
_ICON_EDGE = (250, 250, 250)       # 白描边，深浅任务栏都看得清
_ICON_DOT = {"err": (70, 70, 214)}  # 出错时右下角一点红（BGR）


def _dist_to_segs(x: float, y: float) -> float:
    """点到 W 四段折线的最短距离。"""
    best = 1e9
    for (ax, ay), (bx, by) in _W_SEGS:
        dx, dy = bx - ax, by - ay
        len2 = dx * dx + dy * dy
        t = 0.0 if len2 == 0 else ((x - ax) * dx + (y - ay) * dy) / len2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        px, py = ax + t * dx, ay + t * dy
        d = (x - px) ** 2 + (y - py) ** 2
        if d < best:
            best = d
    return best ** 0.5


def _dib_bytes(size: int, state: str) -> bytes:
    """生成单个尺寸的 ICONIMAGE（BITMAPINFOHEADER + BGRA 像素 + AND mask）。

    32bpp 图标靠 alpha 通道透明，所以 AND mask 填全 0 即可。
    """
    import struct

    ink = _ICON_INK.get(state, _ICON_INK["run"])
    dot = _ICON_DOT.get(state)

    # 线宽按尺寸缩放，但给小尺寸留个下限 —— 否则 16x16 会细到断线。
    # 白色描边给足宽度：黑色 W 在深色任务栏上全靠这圈白边才看得出来。
    k = size / 32.0
    body_w = max(1.05, 1.7 * k)
    edge_w = body_w + max(1.8, 2.0 * k)
    dot_c = (size - 7.5 * k, size - 7.5 * k)
    dot_r = 4.2 * k

    # biHeight 要写 2 倍高（图像 + AND mask）
    hdr = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)

    pix = bytearray()
    for y in range(size - 1, -1, -1):          # DIB 自下而上
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            d = _dist_to_segs(px * 32.0 / size, py * 32.0 / size) * k

            r = g = b = a = 0
            if d <= body_w:
                r, g, b = ink
                a = 255
            elif d <= edge_w:
                r, g, b = _ICON_EDGE
                a = 255

            if dot:
                dd2 = (px - dot_c[0]) ** 2 + (py - dot_c[1]) ** 2
                if dd2 <= dot_r ** 2:
                    r, g, b = dot
                    a = 255
                elif dd2 <= (dot_r + 1.1 * k) ** 2:
                    r, g, b = _ICON_EDGE
                    a = 255

            pix += bytes((b, g, r, a))         # BGRA

    row = ((size + 31) // 32) * 4              # AND mask 每行 4 字节对齐
    return hdr + bytes(pix) + bytes(row * size)


def make_icon(state: str = "run", size: int = 32) -> int:
    """画一个黑白的 W，返回 HICON。

    一次生成 16/20/24/32/48/64 多个尺寸打包成真正的 .ico，
    这样无论任务栏缩放是 100% 还是 200%，系统都能挑到原生尺寸，
    不会把 32x32 拉成 16x16 糊成一团。

    state: run=黑 W / pause=灰 W / err=灰 W + 右下角红点
    """
    import struct

    sizes = (16, 20, 24, 32, 48, 64)
    imgs = [(s, _dib_bytes(s, state)) for s in sizes]

    blob = bytearray()
    blob += struct.pack("<HHH", 0, 1, len(imgs))
    offset = 6 + 16 * len(imgs)
    for s, data in imgs:
        blob += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0,
                            1, 32, len(data), offset)
        offset += len(data)
    for _s, data in imgs:
        blob += data

    try:
        buf = (ctypes.c_char * len(blob)).from_buffer_copy(bytes(blob))
        icon = u32.CreateIconFromResourceEx(buf, len(blob), True, 0x00030000,
                                            0, 0, 0x0000)  # LR_DEFAULTCOLOR
        if icon:
            return icon
    except Exception as e:  # noqa: BLE001
        print(f"[icon warn] multi-size failed: {e}")

    # 兜底：单尺寸，用 CreateIconIndirect
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    bits = ctypes.c_void_p()
    hdc = u32.GetDC(0)
    hbm = g32.CreateDIBSection(hdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    u32.ReleaseDC(0, hdc)
    if not hbm or not bits.value:
        return u32.LoadImageW(0, IDI_APPLICATION, IMAGE_ICON, 0, 0, LR_DEFAULTSIZE)

    raw = _dib_bytes(size, state)
    body = raw[40:40 + size * size * 4]
    buf2 = (ctypes.c_ubyte * (size * size * 4)).from_address(bits.value)
    # _dib_bytes 是自下而上，这里改成自上而下（biHeight 为负）
    for y in range(size):
        src = (size - 1 - y) * size * 4
        dst = y * size * 4
        buf2[dst:dst + size * 4] = body[src:src + size * 4]

    mask = g32.CreateBitmap(size, size, 1, 1, None)
    info = ICONINFO()
    info.fIcon = True
    info.hbmMask = mask
    info.hbmColor = hbm
    icon = u32.CreateIconIndirect(ctypes.byref(info))
    return icon or u32.LoadImageW(0, IDI_APPLICATION, IMAGE_ICON, 0, 0, LR_DEFAULTSIZE)


# ---------------------------------------------------------------------------
# 托盘应用
# ---------------------------------------------------------------------------

class TrayApp:
    def __init__(self):
        self.hwnd = None
        self.icons = {}
        self.mutex_ok = True
        self.cfg = load_config(os.path.join(HERE, CONFIG_NAME))
        self.backend_name = self.cfg.get("backend", "auto") or "auto"
        if self.backend_name not in ("auto", "xinput", "sdl", "sdl-dll"):
            self.backend_name = "auto"
        self.send_mode = self.cfg.get("send_mode", "post") or "post"
        self.bridge: GamepadBridge | None = None
        self.thread: threading.Thread | None = None
        self.err: str | None = None
        self.last_taps = 0

        enable_file_log(os.path.join(HERE, LOG_NAME))

    # ---- 桥接线程 ----
    def start_bridge(self) -> None:
        self.stop_bridge()
        self.err = None
        try:
            backend = build_backend(self.cfg, self.backend_name, None, None)
        except Exception as e:  # noqa: BLE001
            self.err = f"后端启动失败：{e}"
            print(f"[{t('common.error')}] {self.err}")
            self._set_icon(ST_ERR)
            return

        hwnd = find_tappo_hwnd() if self.send_mode in ("post", "both") else None
        sender = InputSender(enabled=True, send_mode=self.send_mode, target_hwnd=hwnd)
        if self.send_mode in ("post", "both") and not sender.hwnd:
            self.err = "没找到桌宠窗口"
            print(f"[{t('common.warn')}] {t('tray.err.no_window')}")
            self._set_icon(ST_ERR)
            return

        print(f"{t('bridge.backend')}={self.backend_name} "
              f"{t('bridge.channel')}={sender.send_mode}"
              + (f" 0x{sender.hwnd:X}" if sender.hwnd else ""))
        self.bridge = GamepadBridge(backend, sender, self.cfg)
        self.thread = threading.Thread(target=self.bridge.run,
                                       kwargs={"hz": int(self.cfg.get("poll_hz", 120))},
                                       daemon=True)
        self.thread.start()
        self._set_icon(ST_RUN)

    def stop_bridge(self) -> None:
        if self.bridge:
            self.bridge.stop()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        self.bridge = None
        self.thread = None

    def toggle_pause(self) -> None:
        if not self.bridge:
            return
        self.bridge.paused = not self.bridge.paused
        print(t('bridge.paused') if self.bridge.paused else t('bridge.resumed'))
        self._set_icon(ST_PAUSE if self.bridge.paused else ST_RUN)

    def reload_config(self) -> None:
        self.cfg = load_config(os.path.join(HERE, CONFIG_NAME))
        self.send_mode = self.cfg.get("send_mode", "post") or "post"
        self.start_bridge()

    def relocate(self) -> None:
        if self.bridge and self.bridge.sender:
            self.bridge.sender.hwnd = None
            self.bridge.sender.ensure_target()
        else:
            h = find_tappo_hwnd()
            print(("0x%X" % h) if h else t("tray.err.no_window"))

    # ---- 图标 / 提示 ----
    @staticmethod
    def _lasterr() -> str:
        try:
            return f"(GetLastError={k32.GetLastError()})"
        except Exception:
            return ""

    def _set_icon(self, state: str) -> None:
        key = state
        if key not in self.icons:
            self.icons[key] = make_icon(state)
        hicon = self.icons[key]
        nid = NOTIFYICONDATAW()
        nid.cbSize = type(nid).szTip.offset + ctypes.sizeof(wintypes.WCHAR) * 128
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_ICON
        nid.hIcon = hicon
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def update_tip(self) -> None:
        if not self.hwnd:
            return
        if self.err:
            state = self.err
        elif not self.bridge:
            state = t("tray.status.stopped")
        elif self.bridge.paused:
            state = t("tray.status.paused")
        else:
            state = t("tray.status.running")
        taps = self.bridge.sender.taps if self.bridge else 0
        tip = t("tray.tip", state=state, taps=taps)
        nid = NOTIFYICONDATAW()
        nid.cbSize = type(nid).szTip.offset + ctypes.sizeof(wintypes.WCHAR) * 128
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_TIP
        nid.szTip = tip[:127]
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # ---- 菜单 ----
    def build_menu(self):
        menu = u32.CreatePopupMenu()
        if not menu:
            return None

        def add(mid, text, checked=False, grayed=False, sep=False):
            if sep:
                u32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                return
            flags = MF_STRING
            if grayed:
                flags |= MF_GRAYED
            if checked:
                flags |= MF_CHECKED
            u32.AppendMenuW(menu, flags, mid, text)

        # 状态行
        if self.err:
            status = f"{t('common.error')}：{self.err}"
        elif not self.bridge:
            status = t("tray.status.stopped")
        elif self.bridge.paused:
            status = t("tray.status.paused")
        else:
            hwnd = self.bridge.sender.hwnd
            status = (f"{t('tray.status.running')} · {self.backend_name} · {self.send_mode}"
                      + (f" · 0x{hwnd:X}" if hwnd else ""))
        add(ID_STATUS, status, grayed=True)
        taps = self.bridge.sender.taps if self.bridge else 0
        moves = self.bridge.sender.mouse_moves if self.bridge else 0
        add(ID_STATUS, t("tray.taps_line", taps=taps, moves=moves), grayed=True)
        add(0, "", sep=True)

        add(ID_PAUSE, t("tray.menu.resume") if (self.bridge and self.bridge.paused)
            else t("tray.menu.pause"))
        add(0, "", sep=True)

        add(ID_MODE_POST, t("tray.menu.post"), checked=(self.send_mode == "post"))
        add(ID_MODE_SI, t("tray.menu.sendinput"), checked=(self.send_mode == "sendinput"))
        add(0, "", sep=True)

        add(ID_BK_AUTO, f"{t('tray.menu.backend')}：{t('tray.menu.auto')}",
            checked=(self.backend_name == "auto"))
        add(ID_BK_SDLDLL, f"{t('tray.menu.backend')}：{t('tray.menu.sdl_dll')}",
            checked=(self.backend_name == "sdl-dll"))
        add(ID_BK_SDL, f"{t('tray.menu.backend')}：{t('tray.menu.pygame')}",
            checked=(self.backend_name == "sdl"))
        add(ID_BK_XINPUT, f"{t('tray.menu.backend')}：{t('tray.menu.xinput')}",
            checked=(self.backend_name == "xinput"))
        add(0, "", sep=True)

        add(ID_PROBE, t("tray.menu.probe"))
        add(ID_RELOAD, t("tray.menu.reload"))
        add(ID_RELOCATE, t("tray.menu.relocate"))
        add(ID_CONFIG, t("tray.menu.config"))
        add(ID_LOG, t("tray.menu.log"))
        add(ID_SDL_HELP, t("tray.menu.sdl_help"))
        add(ID_LANG, t("tray.menu.language"))
        add(ID_REPO, t("tray.menu.repo"))
        add(ID_NOTICE, t("tray.menu.notice"))
        add(0, "", sep=True)

        add(ID_AUTORUN, t("tray.menu.autorun"), checked=self._autorun_enabled())
        add(ID_ABOUT, t("tray.menu.about"))
        add(0, "", sep=True)
        add(ID_EXIT, t("tray.menu.exit"))
        return menu

    def show_menu(self) -> None:
        menu = self.build_menu()
        if not menu:
            return
        pt = POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self.hwnd)
        cmd = u32.TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                 pt.x, pt.y, 0, self.hwnd, None)
        u32.PostMessageW(self.hwnd, 0, 0, 0)     # 让菜单彻底关掉
        u32.DestroyMenu(menu)
        if cmd:
            self.on_command(cmd)

    # ---- 命令 ----
    def on_command(self, cmd: int) -> None:
        if cmd == ID_EXIT:
            self.stop_bridge()
            u32.DestroyWindow(self.hwnd)
            return
        if cmd == ID_PAUSE:
            self.toggle_pause()
        elif cmd == ID_MODE_SI:
            self.send_mode = "sendinput"
            self._persist("send_mode", self.send_mode)
            self.start_bridge()
        elif cmd == ID_MODE_POST:
            self.send_mode = "post"
            self._persist("send_mode", self.send_mode)
            self.start_bridge()
        elif cmd in (ID_BK_AUTO, ID_BK_SDLDLL, ID_BK_SDL, ID_BK_XINPUT):
            self.backend_name = {ID_BK_AUTO: "auto", ID_BK_SDLDLL: "sdl-dll",
                                 ID_BK_SDL: "sdl", ID_BK_XINPUT: "xinput"}[cmd]
            self._persist("backend", self.backend_name)
            self.start_bridge()
        elif cmd == ID_PROBE:
            self.run_probe()
        elif cmd == ID_RELOAD:
            self.reload_config()
        elif cmd == ID_RELOCATE:
            self.relocate()
        elif cmd == ID_CONFIG:
            self.open_file(os.path.join(HERE, CONFIG_NAME))
        elif cmd == ID_LOG:
            self.open_file(os.path.join(HERE, LOG_NAME))
        elif cmd == ID_SDL_HELP:
            self.show_sdl_help()
        elif cmd == ID_REPO:
            self.open_repo()
        elif cmd == ID_NOTICE:
            self.open_file(os.path.join(HERE, "NOTICE.txt"))
        elif cmd == ID_LANG:
            self.choose_language()
        elif cmd == ID_AUTORUN:
            self.toggle_autorun()
        elif cmd == ID_ABOUT:
            self.show_about()
        self.update_tip()

    def show_sdl_help(self) -> None:
        u32.MessageBoxW(0, t("tray.sdl_help"), t("tray.menu.sdl_help"), 0x40)

    @staticmethod
    def open_repo() -> None:
        """用默认浏览器打开仓库地址。"""
        url = getattr(project, "GITHUB_URL", "")
        if not url or "your-name" in url:
            u32.MessageBoxW(0, t("tray.repo_unset"), t("tray.menu.repo"), 0x30)
            return
        try:
            rc = shell32.ShellExecuteW(None, "open", url, None, None, 5)  # SW_SHOW
            if int(rc) <= 32:
                raise OSError(f"ShellExecuteW returned {rc}")
        except Exception as e:  # noqa: BLE001
            print(f"[{t('common.error')}] {e}")
            u32.MessageBoxW(0, f"{t('tray.repo_open_failed')}\n\n{url}",
                            t("tray.menu.repo"), 0x10)

    def choose_language(self) -> None:
        """托盘里切语言。切完提示重启——菜单是动态构建的，
        但已启动的桥接提示和 tooltip 需要重启才完全一致。"""
        cur = i18n.get_lang()
        order = [c for c in LANGS if c != cur]
        opts = [cur] + order
        msg = t("lang.title") + "\n\n"
        for i, c in enumerate(opts, 1):
            msg += f"  [{i}] {LANG_NAMES[c]}\n"
        msg += "\n" + t("lang.prompt")
        # 简化：用 MessageBox 的按钮不够，直接用控制台不可见，
        # 所以这里弹出三个按钮对应三种语言（Yes/No/Cancel）
        res = u32.MessageBoxW(0, msg, t("tray.menu.language"),
                              0x03 | 0x40)     # YesNoCancel + 信息图标
        mapping = {6: opts[0], 7: opts[1], 2: opts[2]}   # IDYES/IDNO/IDCANCEL
        new = mapping.get(res)
        if new and new != cur:
            set_lang(new)
            save_lang(new)
            u32.MessageBoxW(0, t("tray.restart_needed"), t("tray.menu.language"), 0x40)

    def _persist(self, key: str, value) -> None:
        """把菜单里的改动写回 config.json，下次启动还生效。"""
        import json
        path = os.path.join(HERE, CONFIG_NAME)
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
        cfg[key] = value
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            print(f"[{t('common.warn')}] {e}")
        self.cfg[key] = value

    @staticmethod
    def _python_exe() -> str:
        exe = sys.executable
        if exe.lower().endswith("pythonw.exe"):
            cand = exe[: -len("pythonw.exe")] + "python.exe"
            if os.path.exists(cand):
                return cand
        return exe

    def run_probe(self) -> None:
        try:
            subprocess.Popen([self._python_exe(), os.path.join(SRC, "gamepad_bridge.py"),
                              "--backend", self.backend_name, "--probe", "--probe-seconds", "30"],
                             cwd=HERE, creationflags=subprocess.CREATE_NEW_CONSOLE)
        except Exception as e:  # noqa: BLE001
            print(f"[{t('common.error')}] {e}")

    @staticmethod
    def open_file(path: str) -> None:
        try:
            if not os.path.exists(path):
                open(path, "w", encoding="utf-8").close()
            os.startfile(path)
        except Exception as e:  # noqa: BLE001
            print(f"[{t('common.error')}] {path}: {e}")

    @staticmethod
    def _autorun_link() -> str:
        startup = os.path.join(os.environ.get("APPDATA", ""),
                               r"Microsoft\Windows\Start Menu\Programs\Startup")
        return os.path.join(startup, "WuwaTappoGamepadBridge.lnk")

    def _autorun_enabled(self) -> bool:
        return os.path.exists(self._autorun_link())

    def toggle_autorun(self) -> None:
        link = self._autorun_link()
        if os.path.exists(link):
            try:
                os.remove(link)
                print(t("tray.autorun_off"))
            except Exception as e:  # noqa: BLE001
                print(f"[错误] {e}")
            return
        target = os.path.join(HERE, "tray_launcher.vbs")
        if not os.path.exists(target):
            print(f"[{t('common.error')}] tray_launcher.vbs")
            return
        ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
              f"$s.TargetPath='{target}';$s.WorkingDirectory='{HERE}';"
              f"$s.Description='Wuwa Tappo gamepad bridge';$s.Save()")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, timeout=30)
            print(t("tray.autorun_on"))
        except Exception as e:  # noqa: BLE001
            print(f"[错误] {e}")

    @staticmethod
    def show_about() -> None:
        """关于。MessageBox 不支持超链接，所以地址以纯文本显示，
        真正能点开的是菜单里的「项目主页」项。"""
        url = getattr(project, "GITHUB_URL", "")
        unset = (not url) or ("your-name" in url)
        url_line = f"\n{t('tray.about_url')}\n  " + (
            t("tray.repo_unset_short") if unset else url)
        u32.MessageBoxW(0,
                        t("tray.about",
                          author=getattr(project, "AUTHOR", "-"),
                          version=getattr(project, "VERSION", ""),
                          license=getattr(project, "LICENSE_NAME", ""))
                        + url_line,
                        t("tray.menu.about"), 0x40)

    # ---- 窗口过程 ----
    def wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            if lparam in (WM_RBUTTONUP, WM_LBUTTONUP):
                # WM_LBUTTONUP 也弹菜单，某些环境下右键消息会丢
                if lparam == WM_LBUTTONUP:
                    return 0
                self.update_tip()
                self.show_menu()
            elif lparam == WM_LBUTTONDBLCLK:
                self.toggle_pause()
                self.update_tip()
            return 0
        if msg == WM_COMMAND:
            self.on_command(wparam & 0xFFFF)
            return 0
        if msg == WM_TIMER:
            self.update_tip()
            return 0
        if msg == WM_DESTROY:
            nid = NOTIFYICONDATAW()
            nid.cbSize = type(nid).szTip.offset + ctypes.sizeof(wintypes.WCHAR) * 128
            nid.hWnd = hwnd
            nid.uID = 1
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            u32.PostQuitMessage(0)
            return 0
        return u32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ---- 主循环 ----
    def run(self) -> int:
        if not ensure_single_instance():
            u32.MessageBoxW(0, t("tray.dup"), t("app.title"), 0x30)
            return 0

        WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                                     wintypes.WPARAM, wintypes.LPARAM)
        self._wndproc = WNDPROC(self.wnd_proc)

        hinst = k32.GetModuleHandleW(None)
        cls = WNDCLASSEXW()
        cls.cbSize = ctypes.sizeof(WNDCLASSEXW)
        cls.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p)
        cls.hInstance = hinst
        cls.lpszClassName = "WuwaTappoGamepadBridgeTray"
        cls.hIcon = make_icon(ST_RUN)
        cls.hIconSm = cls.hIcon
        if not u32.RegisterClassExW(ctypes.byref(cls)):
            print(f"[{t('common.error')}] RegisterClassEx: {self._lasterr()}")
            return 1

        # 首选 message-only 窗口（不可见、不进任务栏）。
        # 万一被环境拒绝，降级为普通隐藏窗口，功能完全一样。
        for parent, tag in ((HWND_MESSAGE, "message-only"), (None, "hidden")):
            self.hwnd = u32.CreateWindowExW(
                0, "WuwaTappoGamepadBridgeTray", "Wuwa Tappo Gamepad Bridge",
                0, 0, 0, 0, 0, parent, None, hinst, None)
            if self.hwnd:
                if tag != "message-only":
                    print(f"[{t('common.warn')}] {t('tray.window_fallback')}")
                break
            print(f"[{t('common.warn')}] CreateWindow({tag}) {self._lasterr()}")

        if not self.hwnd:
            print(f"[{t('common.error')}] {t('tray.err.create_window')}")
            return 1

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = make_icon(ST_RUN)
        nid.szTip = t("app.title")
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
            print(f"[{t('common.error')}] {t('tray.err.icon')} {self._lasterr()}")
            # 图标建不出来不要整个退出 —— 手柄功能照样能用，
            # 只是没有托盘界面。用 Ctrl+C / stop.bat 结束。
            return self._run_headless()

        print(t("tray.started"))
        if project.is_placeholder():
            print(f"[{t('common.warn')}] {t('tray.author_unset')}")
        print(f"[{t('bridge.backend')}] {self.backend_name}  "
              f"[{t('bridge.channel')}] {self.send_mode}")
        self.start_bridge()
        self.update_tip()
        u32.SetTimer(self.hwnd, 1, 3000, None)

        msg = MSG()
        try:
            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
        finally:
            u32.KillTimer(self.hwnd, 1)
            self.stop_bridge()
        return 0

    def _run_headless(self) -> int:
        """托盘图标建不出来时的兜底：桥接照常跑，只是没有界面。

        手柄 Back+Start 和 Ctrl+Alt+G 暂停依然有效（靠轮询，不需要窗口）。
        退出只能靠 Ctrl+C 或 stop.bat。
        """
        print()
        print(f"[{t('common.warn')}] {t('tray.headless1')}")
        print(f"        {t('tray.headless2')}")
        print(f"        {t('tray.headless3')}")
        print()
        self.start_bridge()
        try:
            while True:
                time.sleep(1.0)
        except (KeyboardInterrupt, SystemExit):
            pass
        self.stop_bridge()
        return 0


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Wuwa Tappo 托盘控制器")
    ap.add_argument("--no-autostart", action="store_true", help="启动后不自动开始桥接")
    ap.add_argument("--no-tray-only-check", action="store_true",
                    help="只做初始化检查（不建托盘图标），用于排错")
    args = ap.parse_args()

    app = TrayApp()
    if args.no_autostart:
        app.start_bridge = lambda: None
    if args.no_tray_only_check:
        print("[check] backend=" + app.backend_name + "  mode=" + app.send_mode)
        be = build_backend(app.cfg, app.backend_name, None, None)
        print("[check] backend OK: " + type(be).__name__)
        print("[check] pet window: " +
              (("0x%X" % find_tappo_hwnd()) if find_tappo_hwnd() else "not found"))
        return 0
    return app.run()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        # pythonw 没有控制台，异常必须落到日志 + 弹窗，否则用户完全看不到
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(HERE, "bridge.log"), "a", encoding="utf-8") as f:
                f.write("\n==== crash ====\n" + tb + "\n")
        except Exception:
            pass
        print(tb)
        try:
            ctypes.windll.user32.MessageBoxW(0, tb[-1800:], "Tray app crashed", 0x10)
        except Exception:
            pass
        sys.exit(1)
