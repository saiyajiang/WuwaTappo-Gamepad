# -*- coding: utf-8 -*-
"""
Wuwa Tappo - Gamepad Bridge
===========================

把游戏手柄的输入翻译成真实键盘 / 鼠标事件，喂给闭源的 Wuwa Tappo，
从而让桌宠跟着手柄一起「啪嗒啪嗒」拍桌子。

设计参考了开源版 BongoCat 的手柄实现（src-tauri/src/core/gamepad.rs）：
后端用 XInput 手柄抽象层轮询手柄状态 -> 归一化成 按钮 / 摇杆 / 扳机 事件 ->
前端映射到模型动作。这里我们把「映射到 Live2D 参数」换成
「通过 SendInput 合成键鼠事件」，因为 Wuwa Tappo 只吃键鼠输入。

用法：
    python gamepad_bridge.py --probe      # 查看手柄是否被识别 + 实时按键/摇杆数值
    python gamepad_bridge.py              # 正常运行
    python gamepad_bridge.py --backend sdl  # 用 SDL/pygame 后端（支持 DS4/DualSense 等非 XInput 手柄）

依赖：
    XInput 后端：零依赖（Python 自带 ctypes）
    SDL 后端  ：需要 SDL2.dll，由用户自行从官方下载放进 sdl_runtime\
                官方地址 https://github.com/libsdl-org/SDL/releases
                本脚本不下载任何东西。

暂停 / 恢复：Ctrl + Alt + G（或手柄 Back + Start 同时按住 1 秒）
退出：Ctrl + C
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes

import i18n
from i18n import t, fix_console_encoding, load_lang, set_lang

# 语言由 launcher 选定并存盘；这里只读取，不重复弹选择菜单。
_cached = load_lang()
if _cached:
    set_lang(_cached)

# 脚本放在 src/ 下，根目录是仓库根。先算出来，后面配路径都用它。
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE) if os.path.basename(_HERE).lower() == "src" else _HERE
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Windows 控制台默认 GBK，Python 3 默认按 UTF-8 输出会直接崩。
fix_console_encoding()

# pythonw.exe 启动（后台无窗口模式）时 sys.stdout 是 None，
# print() 会静默丢弃。这里兜底开一个日志文件，保证后台模式下也留得下记录。
if sys.stdout is None:  # pragma: no cover
    try:
        _logp = os.path.join(_ROOT, "bridge.log")
        sys.stdout = sys.stderr = open(_logp, "a", encoding="utf-8", errors="replace")
    except Exception:
        sys.stdout = sys.stderr = open(os.devnull, "w")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CONFIG_NAME = "config.json"
LOG_NAME = "bridge.log"


def app_root() -> str:
    """仓库根目录。脚本在 src/ 下，配置和日志都放根目录，方便用户找。"""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here) if os.path.basename(here).lower() == "src" else here


def ensure_single_instance() -> bool:
    """防止重复启动。两个实例同时在跑 = 每个按键发两遍，桌宠会疯狂乱拍。

    用内核命名互斥量，进程一崩系统自动回收，不存在遗留状态。
    """
    if not sys.platform.startswith("win"):
        return True
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k32.CreateMutexW.restype = wintypes.HANDLE
        handle = k32.CreateMutexW(None, False, "Global\\WuwaTappoGamepadBridge_Mutex")
        # 已存在时 GetLastError 返回 ERROR_ALREADY_EXISTS (183)
        return ctypes.get_last_error() != 183
    except Exception:
        return True


class _Tee:
    """同时写控制台和日志文件。"""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


def enable_file_log(path: str) -> None:
    try:
        f = open(path, "a", encoding="utf-8", errors="replace")
        sys.stdout = _Tee(sys.stdout, f)
        sys.stderr = _Tee(sys.stderr, f)
    except Exception:
        pass

# XInput 按钮位掩码
XINPUT_BUTTONS = {
    "dpad_up": 0x0001,
    "dpad_down": 0x0002,
    "dpad_left": 0x0004,
    "dpad_right": 0x0008,
    "start": 0x0010,
    "back": 0x0020,
    "left_stick": 0x0040,
    "right_stick": 0x0080,
    "lb": 0x0100,
    "rb": 0x0200,
    "a": 0x1000,
    "b": 0x2000,
    "x": 0x4000,
    "y": 0x8000,
}

# 功能键虚拟键码（F13~F24 在绝大多数软件里没有任何绑定，
# 因此按下不会往你的文档里插字符，但桌宠依然能收到 keydown 并拍桌）
VK_NAMES = {
    "F13": 0x7C, "F14": 0x7D, "F15": 0x7E, "F16": 0x7F,
    "F17": 0x80, "F18": 0x81, "F19": 0x82, "F20": 0x83,
    "F21": 0x84, "F22": 0x85, "F23": 0x86, "F24": 0x87,
    "SPACE": 0x20, "ENTER": 0x0D, "TAB": 0x09, "ESC": 0x1B,
    "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
    "LSHIFT": 0xA0, "RSHIFT": 0xA1, "LCTRL": 0xA2, "RCTRL": 0xA3,
    "VOLUME_UP": 0xAF, "VOLUME_DOWN": 0xAE, "VOLUME_MUTE": 0xAD,
    "MEDIA_NEXT": 0xB0, "MEDIA_PREV": 0xB1, "MEDIA_PLAY": 0xB3,
}

MOUSE_BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL = 0x0800

# PostMessage 直投通道用的消息号
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WM_CHAR = 0x0102

# ---------------------------------------------------------------------------
# Windows SendInput 封装
# ---------------------------------------------------------------------------

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUTUNION)]


class InputSender:
    """合成键鼠事件。

    两条通道，可单用也可同时用（send_mode）：

      sendinput —— 系统级。进全局输入队列，投递给「当前前台窗口」。
                   优点：跟真人操作完全等价，桌宠只要用全局钩子 / Raw Input 就一定收得到。
                   缺点：桌宠失焦、或者它只在窗口有焦点时才处理输入，就收不到。

      post      —— 直投。PostMessage 到桌宠自己的窗口句柄。
                   优点：不需要焦点，窗口最小化也照样收得到。
                   缺点：拿不到窗口句柄就用不了；对纯 Raw Input 的实现无效
                        （Raw Input 来自驱动层，伪造不了 WM_INPUT）。

      both      —— 两条都发。桌宠收到两份会拍两下，所以一般只在排查时开。
    """

    def __init__(self, enabled: bool = True, send_mode: str = "sendinput",
                 target_hwnd: int | None = None):
        self.enabled = enabled
        self.user32 = ctypes.windll.user32
        self.taps = 0          # 累计「敲击」次数（按键 + 点击）
        self.mouse_moves = 0
        self.send_mode = (send_mode or "sendinput").lower()
        self.hwnd = target_hwnd
        if self.hwnd and not self.user32.IsWindow(self.hwnd):
            print(f"[{t('common.error')}] 0x{self.hwnd:X} {t('tray.err.no_window')}")
            self.hwnd = None
        if self.send_mode in ("post", "both") and not self.hwnd:
            print(f"[{t('common.error')}] {t('tray.err.no_window')}")
            self.send_mode = "sendinput"

    # ---- 底层 ----
    def _send(self, *inputs: INPUT) -> int:
        if not self.enabled:
            return len(inputs)
        arr = (INPUT * len(inputs))(*inputs)
        return self.user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))

    def _post(self, msg: int, wparam: int, lparam: int) -> None:
        if not self.enabled or not self.hwnd:
            return
        self.user32.PostMessageW(self.hwnd, msg, wparam, lparam)

    def ensure_target(self) -> None:
        """句柄自愈：桌宠重启 / 窗口重建后旧句柄会失效，
        定期复查，失效就重新定位，这样桥接不用跟着重启。"""
        if self.send_mode not in ("post", "both"):
            return
        if self.hwnd and self.user32.IsWindow(self.hwnd):
            return
        new = find_tappo_hwnd()
        if new:
            self.hwnd = new
            print(f"[{t('bridge.window_found')}] {t('bridge.window_relocated', hwnd=new)}")
        elif self.hwnd:
            print(f"[{t('common.warn')}] {t('bridge.window_lost')}")
            self.hwnd = None

    # ---- 底层 ----
    @staticmethod
    def _kbd(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp.union.ki.wVk = vk
        inp.union.ki.wScan = scan
        inp.union.ki.dwFlags = flags
        return inp

    @staticmethod
    def _mouse(dx: int = 0, dy: int = 0, data: int = 0, flags: int = 0) -> INPUT:
        inp = INPUT()
        inp.type = INPUT_MOUSE
        inp.union.mi.dx = dx
        inp.union.mi.dy = dy
        inp.union.mi.mouseData = data
        inp.union.mi.dwFlags = flags
        return inp

    # ---- 语义层 ----
    @property
    def _use_si(self) -> bool:
        return self.send_mode in ("sendinput", "both")

    @property
    def _use_post(self) -> bool:
        return self.send_mode in ("post", "both")

    def _scan_lparam(self, vk: int, up: bool) -> int:
        sc = self.user32.MapVirtualKeyW(vk, 0) & 0xFF
        lp = 1 | (sc << 16)
        if up:
            lp |= (1 << 30) | (1 << 31)
        return lp

    def tap_key(self, vk: int | None = None, char: str | None = None, hold_ms: int = 35) -> None:
        """敲一下键盘。vk 与 char 二选一，char 走 Unicode 注入（会计入字符数）。"""
        hold = max(0, hold_ms) / 1000.0

        if self._use_si:
            if char:
                code = ord(char)
                self._send(self._kbd(0, code, KEYEVENTF_UNICODE))
                time.sleep(hold)
                self._send(self._kbd(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
            else:
                self._send(self._kbd(vk or 0, 0, 0))
                time.sleep(hold)
                self._send(self._kbd(vk or 0, 0, KEYEVENTF_KEYUP))
        self.taps += 1

        if self._use_post:
            if char:
                code = ord(char)
                self._post(WM_CHAR, code, 1)
            else:
                v = vk or 0
                self._post(WM_KEYDOWN, v, self._scan_lparam(v, False))
                time.sleep(hold)
                self._post(WM_KEYUP, v, self._scan_lparam(v, True))

    def click(self, button: str = "left", hold_ms: int = 30) -> None:
        hold = max(0, hold_ms) / 1000.0
        msgs = {"left": (WM_LBUTTONDOWN, WM_LBUTTONUP, 0x0001),
                "right": (WM_RBUTTONDOWN, WM_RBUTTONUP, 0x0002),
                "middle": (WM_MBUTTONDOWN, WM_MBUTTONUP, 0x0010)}
        down_m, up_m, mk = msgs.get(button, msgs["left"])

        if self._use_si:
            down_f, up_f = MOUSE_BUTTONS.get(button, MOUSE_BUTTONS["left"])
            self._send(self._mouse(0, 0, 0, down_f))
            time.sleep(hold)
            self._send(self._mouse(0, 0, 0, up_f))
        if self._use_post:
            self._post(down_m, mk, 0)
            time.sleep(hold)
            self._post(up_m, 0, 0)
        self.taps += 1

    def move_mouse(self, dx: int, dy: int) -> None:
        if dx == 0 and dy == 0:
            return
        if self._use_si:
            self._send(self._mouse(dx, dy, 0, MOUSEEVENTF_MOVE))
        if self._use_post:
            self._post(WM_MOUSEMOVE, 0, (dy & 0xFFFF) << 16 | (dx & 0xFFFF))
        self.mouse_moves += 1

    def wheel(self, delta: int) -> None:
        if self._use_si:
            self._send(self._mouse(0, 0, delta, MOUSEEVENTF_WHEEL))
        if self._use_post:
            self._post(WM_MOUSEWHEEL, (delta & 0xFFFF) << 16, 0)


# ---------------------------------------------------------------------------
# 手柄后端：统一产出 ControllerState
# ---------------------------------------------------------------------------

class ControllerState:
    """归一化后的手柄状态：按钮按下集合 + 摇杆 -1.0~1.0 + 扳机 0.0~1.0"""

    __slots__ = ("buttons", "axes", "triggers", "connected")

    def __init__(self):
        self.buttons: dict[str, bool] = {k: False for k in XINPUT_BUTTONS}
        self.axes: dict[str, tuple[float, float]] = {"left": (0.0, 0.0), "right": (0.0, 0.0)}
        self.triggers: dict[str, float] = {"lt": 0.0, "rt": 0.0}
        self.connected = False

    def as_line(self) -> str:
        on = ",".join(sorted(k for k, v in self.buttons.items() if v)) or "-"
        lx, ly = self.axes["left"]
        rx, ry = self.axes["right"]
        return (f"btn[{on}] L({lx:+.2f},{ly:+.2f}) R({rx:+.2f},{ry:+.2f}) "
                f"LT {self.triggers['lt']:.2f} RT {self.triggers['rt']:.2f}")


class XInputBackend:
    """零依赖：直接 ctypes 调 xinput1_4.dll。仅支持 XInput 设备（Xbox 手柄及兼容设备）。"""

    def __init__(self, index: int = 0):
        self.index = index
        self.dll = None
        for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
            try:
                self.dll = ctypes.WinDLL(name)
                break
            except OSError:
                continue
        if self.dll is None:
            raise RuntimeError("未找到 XInput 运行库，请改用 --backend sdl")

        class XINPUT_GAMEPAD(ctypes.Structure):
            _fields_ = [
                ("wButtons", wintypes.WORD),
                ("bLeftTrigger", wintypes.BYTE),
                ("bRightTrigger", wintypes.BYTE),
                ("sThumbLX", wintypes.SHORT),
                ("sThumbLY", wintypes.SHORT),
                ("sThumbRX", wintypes.SHORT),
                ("sThumbRY", wintypes.SHORT),
            ]

        class XINPUT_STATE(ctypes.Structure):
            _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]

        self._state = XINPUT_STATE()
        self.dll.XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
        self.dll.XInputGetState.restype = wintypes.DWORD

    @staticmethod
    def _norm_thumb(v: int) -> float:
        v = max(-32768, min(32767, v))
        return v / 32767.0 if v >= 0 else v / 32768.0

    def poll(self) -> ControllerState:
        st = ControllerState()
        res = self.dll.XInputGetState(self.index, ctypes.byref(self._state))
        if res != 0:               # 1167 = 设备未连接
            return st
        g = self._state.Gamepad
        st.connected = True
        for name, mask in XINPUT_BUTTONS.items():
            st.buttons[name] = bool(g.wButtons & mask)
        st.triggers["lt"] = g.bLeftTrigger / 255.0
        st.triggers["rt"] = g.bRightTrigger / 255.0
        st.axes["left"] = (self._norm_thumb(g.sThumbLX), -self._norm_thumb(g.sThumbLY))
        st.axes["right"] = (self._norm_thumb(g.sThumbRX), -self._norm_thumb(g.sThumbRY))
        return st

    def close(self) -> None:
        pass


class SDLBackend:
    """可选后端：pygame/SDL，支持 DualShock / DualSense / 国产 DirectInput 手柄。"""

    # SDL 的按钮顺序（Xbox 布局）
    BTN_ORDER = ["a", "b", "x", "y", "lb", "rb", "back", "start", "guide", "left_stick", "right_stick"]

    def __init__(self, index: int = 0, trigger_axes: tuple[int, int] | None = None):
        import pygame  # noqa: PLC0415
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() == 0:
            raise RuntimeError("SDL 未检测到任何手柄")
        self.js = pygame.joystick.Joystick(index)
        self.js.init()
        self.n_axes = self.js.get_numaxes()
        if trigger_axes:
            self.lt_axis, self.rt_axis = trigger_axes
        elif self.n_axes >= 6:
            self.lt_axis, self.rt_axis = 4, 5
        else:
            self.lt_axis, self.rt_axis = 2, 2   # DInput 常见：单轴合并两个扳机
        print(f"[SDL] 手柄: {self.js.get_name()}  轴数={self.n_axes} "
              f"扳机轴=({self.lt_axis},{self.rt_axis})")

    def poll(self) -> ControllerState:
        import pygame  # noqa: PLC0415
        pygame.event.pump()
        st = ControllerState()
        st.connected = True
        for name in st.buttons:
            st.buttons[name] = False
        for i, name in enumerate(self.BTN_ORDER):
            if i < self.js.get_numbuttons():
                st.buttons[name] = bool(self.js.get_button(i))
        # 帽子开关 -> 方向键
        if self.js.get_numhats() > 0:
            hx, hy = self.js.get_hat(0)
            st.buttons["dpad_left"] = hx < 0
            st.buttons["dpad_right"] = hx > 0
            st.buttons["dpad_down"] = hy < 0
            st.buttons["dpad_up"] = hy > 0
        a = lambda i: self.js.get_axis(i) if i < self.n_axes else 0.0  # noqa: E731
        st.axes["left"] = (a(0), -a(1))
        st.axes["right"] = (a(2), -a(3)) if self.n_axes >= 4 else (0.0, 0.0)
        if self.lt_axis == self.rt_axis:
            v = a(self.lt_axis)
            st.triggers["lt"] = max(0.0, -v)
            st.triggers["rt"] = max(0.0, v)
        else:
            st.triggers["lt"] = (a(self.lt_axis) + 1) / 2
            st.triggers["rt"] = (a(self.rt_axis) + 1) / 2
        return st

    def close(self) -> None:
        try:
            import pygame  # noqa: PLC0415
            pygame.joystick.quit()
            pygame.quit()
        except Exception:
            pass


class SDLNativeBackend:
    """直接 LoadLibrary 一个 SDL2/SDL3 动态库，用它自带的 GameController/Gamepad API 读手柄。

    为什么值得这么干：Wuwa Tappo 的「开源组件声明」里大概率就挂着 SDL
    （Steam 版 Bongo Cat 的 middleware 明确写着 Input = SDL）。也就是说
    「读得懂所有手柄」的那套代码已经躺在它的安装目录里了，只是它自己没用。
    我们在这里把自己进程里的 SDL.dll 加载起来，就能白嫖到：
      * XInput / DirectInput / PS / Switch / 八位堂 全协议覆盖
      * SDL 官方 gamecontrollerdb 的几千条手柄映射（不用自己猜键位）
      * 摇杆死区、扳机归一化等已经调好的手感参数
    全程在自己进程内，跟 Wuwa Tappo 的进程不共享任何状态，安全无副作用。
    """

    # SDL_GameControllerButton / SDL_GamepadButton（SDL2 与 SDL3 编号一致）
    BTN = ["a", "b", "x", "y", "back", "guide", "start",
           "left_stick", "right_stick", "lb", "rb",
           "dpad_up", "dpad_down", "dpad_left", "dpad_right"]
    # SDL_GameControllerAxis / SDL_GamepadAxis
    AX_LEFTX, AX_LEFTY, AX_RIGHTX, AX_RIGHTY, AX_LT, AX_RT = range(6)

    def __init__(self, dll_path: str, index: int = 0, mapping_file: str | None = None,
                 extra_mappings: list[str] | None = None):
        self.dll = ctypes.CDLL(dll_path)
        self.is_sdl3 = hasattr(self.dll, "SDL_OpenGamepad")
        ver = "SDL3" if self.is_sdl3 else "SDL2"
        print(f"[SDL] 已加载 {dll_path}（识别为 {ver}）")

        # --- 函数原型 ---
        self._init_fn("SDL_Init", ctypes.c_int, [ctypes.c_uint32])
        self._init_fn("SDL_PumpEvents", None, [])
        self._init_fn("SDL_SetHint", ctypes.c_int, [ctypes.c_char_p, ctypes.c_char_p])
        self._init_fn("SDL_GetError", ctypes.c_char_p, [])

        if self.is_sdl3:
            self._init_fn("SDL_GetGamepads", ctypes.POINTER(ctypes.c_uint32), [ctypes.POINTER(ctypes.c_int)])
            self._init_fn("SDL_OpenGamepad", ctypes.c_void_p, [ctypes.c_uint32])
            self._init_fn("SDL_GetGamepadNameForID", ctypes.c_char_p, [ctypes.c_uint32])
            self._init_fn("SDL_GetGamepadButton", ctypes.c_bool, [ctypes.c_void_p, ctypes.c_int])
            self._init_fn("SDL_GetGamepadAxis", ctypes.c_int16, [ctypes.c_void_p, ctypes.c_int])
            self._init_fn("SDL_AddGamepadMapping", ctypes.c_int, [ctypes.c_char_p])
            self._init_fn("SDL_UpdateGamepads", None, [], required=False)
            self.INIT_FLAG = 0x00000020  # SDL_INIT_GAMEPAD
        else:
            self._init_fn("SDL_NumJoysticks", ctypes.c_int, [])
            self._init_fn("SDL_IsGameController", ctypes.c_int, [ctypes.c_int])
            self._init_fn("SDL_GameControllerOpen", ctypes.c_void_p, [ctypes.c_int])
            self._init_fn("SDL_GameControllerNameForIndex", ctypes.c_char_p, [ctypes.c_int])
            self._init_fn("SDL_GameControllerGetButton", ctypes.c_uint8, [ctypes.c_void_p, ctypes.c_int])
            self._init_fn("SDL_GameControllerGetAxis", ctypes.c_int16, [ctypes.c_void_p, ctypes.c_int])
            self._init_fn("SDL_GameControllerAddMapping", ctypes.c_int, [ctypes.c_char_p])
            self.INIT_FLAG = 0x00002000  # SDL_INIT_GAMECONTROLLER

        # --- 可选提示项：把不常见的手柄（8BitDo DInput 等）也纳入识别 ---
        for hint, val in ((b"SDL_GAMECONTROLLER_ALLOW_STEAM_VIRTUAL_GAMEPADS", b"0"),
                          (b"SDL_JOYSTICK_HIDAPI_PS4_RUMBLE", b"0")):
            try:
                self.dll.SDL_SetHint(hint, val)
            except Exception:
                pass

        if self.dll.SDL_Init(self.INIT_FLAG) != 0:
            raise RuntimeError(f"SDL_Init 失败: {self._err()}")
        self._pump()

        # --- 加载控制器映射数据库 ---
        loaded = 0
        for line in (extra_mappings or []):
            self._add_mapping(line)
            loaded += 1
        if mapping_file and os.path.exists(mapping_file):
            with open(mapping_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        self._add_mapping(line)
                        loaded += 1
        if loaded:
            print(f"[SDL] 载入 {loaded} 条手柄映射")

        # --- 打开设备 ---
        self.pad = None
        names = self._list_names()
        if not names:
            raise RuntimeError("SDL 没找到任何手柄，插上再试（蓝牙手柄建议插线）")
        if index >= len(names):
            index = 0
        self.index = index
        self.pad = self._open(index)
        if not self.pad:
            raise RuntimeError(f"打开手柄失败: {self._err()}")
        print(f"[SDL] 已打开 [{index}] {names[index]}"
              + (f"  （共检测到 {len(names)} 个：{', '.join(names)}）" if len(names) > 1 else ""))

    # ---- 辅助 ----
    def _init_fn(self, name: str, restype, argtypes, required: bool = True) -> None:
        fn = getattr(self.dll, name, None)
        if fn is None:
            if required:
                raise RuntimeError(f"{name} 不在这份 SDL 里，可能不是完整版 SDL")
            self.__dict__[f"_{name}"] = None
            return
        fn.restype = restype
        fn.argtypes = argtypes

    def _err(self) -> str:
        try:
            return self.dll.SDL_GetError().decode("utf-8", "ignore")
        except Exception:
            return "(未知)"

    def _pump(self) -> None:
        if self.is_sdl3:
            fn = getattr(self.dll, "SDL_UpdateGamepads", None)
            try:
                if fn is not None:
                    fn()
                else:
                    self.dll.SDL_PumpEvents()
            except Exception:
                self.dll.SDL_PumpEvents()
        else:
            self.dll.SDL_PumpEvents()

    def _add_mapping(self, line: str) -> None:
        fn = self.dll.SDL_AddGamepadMapping if self.is_sdl3 else self.dll.SDL_GameControllerAddMapping
        try:
            fn(line.rstrip("\r\n").encode("utf-8"))
        except Exception:
            pass

    def _list_names(self) -> list[str]:
        out = []
        if self.is_sdl3:
            n = ctypes.c_int(0)
            arr = self.dll.SDL_GetGamepads(ctypes.byref(n))
            for i in range(n.value):
                nm = self.dll.SDL_GetGamepadNameForID(arr[i])
                out.append(nm.decode("utf-8", "ignore") if nm else f"Gamepad#{arr[i]}")
        else:
            for i in range(self.dll.SDL_NumJoysticks()):
                if self.dll.SDL_IsGameController(i):
                    nm = self.dll.SDL_GameControllerNameForIndex(i)
                    out.append(nm.decode("utf-8", "ignore") if nm else f"Controller#{i}")
        return out

    def _open(self, index: int):
        if self.is_sdl3:
            n = ctypes.c_int(0)
            arr = self.dll.SDL_GetGamepads(ctypes.byref(n))
            if index >= n.value:
                return None
            return self.dll.SDL_OpenGamepad(arr[index])
        return self.dll.SDL_GameControllerOpen(index)

    # ---- 轮询 ----
    def poll(self) -> ControllerState:
        st = ControllerState()
        if not self.pad:
            return st
        self._pump()
        st.connected = True
        if self.is_sdl3:
            get_btn = self.dll.SDL_GetGamepadButton
            get_axis = self.dll.SDL_GetGamepadAxis
        else:
            get_btn = self.dll.SDL_GameControllerGetButton
            get_axis = self.dll.SDL_GameControllerGetAxis
        for i, name in enumerate(self.BTN):
            st.buttons[name] = bool(get_btn(self.pad, i))
        ax = lambda i: get_axis(self.pad, i)  # noqa: E731
        st.axes["left"] = (ax(self.AX_LEFTX) / 32767.0, -ax(self.AX_LEFTY) / 32767.0)
        st.axes["right"] = (ax(self.AX_RIGHTX) / 32767.0, -ax(self.AX_RIGHTY) / 32767.0)
        # SDL 的扳机是 0..32767，跟摇杆的 -32768..32767 不一样，别混着归一化
        st.triggers["lt"] = max(0.0, ax(self.AX_LT)) / 32767.0
        st.triggers["rt"] = max(0.0, ax(self.AX_RT)) / 32767.0
        return st

    def close(self) -> None:
        pass


def find_sdl_dll(search_dirs: list[str] | None = None) -> str | None:
    """找一份 SDL 运行时。单文件版没有散落的 dll，所以按这个顺序找：
       1. 显式指定的目录 / 配置文件里写的
       2. 本目录、当前目录、dumped_dll（inspect_exe.py 抠出来的）
       3. Python 包装的：pygame、pysdl2-dll
       4. PATH
    """
    sdl_names = ("SDL3.dll", "SDL2.dll")

    def _in(d: str) -> str | None:
        if d and os.path.isdir(d):
            for name in sdl_names:
                p = os.path.join(d, name)
                if os.path.exists(p):
                    return p
        return None

    root = app_root()
    dirs = [d for d in (search_dirs or []) if d]
    # 用户手动放 DLL 的地方：sdl_runtime/ 和仓库根目录
    dirs += [os.path.join(root, "sdl_runtime"), root,
             _HERE, os.path.join(root, "dumped_dll"), os.getcwd()]
    for env in ("WUWATAPPO_DIR", "SDL_DLL_DIR"):
        if os.environ.get(env):
            dirs.append(os.environ[env])
    for d in dirs:
        hit = _in(d)
        if hit:
            return hit

    # Python 包里自带的
    try:
        import site
        for sp in site.getsitepackages():
            for sub in ("pygame", "pysdl2_dll", "sdl2dll", "sdl2"):
                hit = _in(os.path.join(sp, sub))
                if hit:
                    return hit
    except Exception:
        pass
    try:
        import pygame
        hit = _in(os.path.dirname(os.path.dirname(pygame.__file__)))
        if hit:
            return hit
    except Exception:
        pass

    # PATH
    for d in os.environ.get("PATH", "").split(os.pathsep):
        hit = _in(d)
        if hit:
            return hit

    # 兜底：整盘扫（只扫两层，别太慢）
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for root, _sub, files in os.walk(d):
            for name in sdl_names:
                if name in files:
                    return os.path.join(root, name)
    return None


# ---------------------------------------------------------------------------
# 桥接核心
# ---------------------------------------------------------------------------

class GamepadBridge:
    def __init__(self, backend, sender: InputSender, cfg: dict):
        self.backend = backend
        self.sender = sender
        self.cfg = cfg
        self.prev = ControllerState()
        self.prev.triggers = {"lt": 0.0, "rt": 0.0}
        self.repeat_at: dict[str, float] = {}
        self.paused = False
        self.combo_hold_start: float | None = None
        self.started_at = time.time()
        self._stop = False          # 托盘 / 外部调用者置 True 让 run() 退出

        self.deadzone = float(cfg.get("deadzone", 0.25))
        self.trigger_threshold = float(cfg.get("trigger_threshold", 0.5))
        self.stick_sens = float(cfg.get("stick_mouse_sensitivity", 10))
        self.bindings = cfg.get("bindings", {})
        self.stick_mode = cfg.get("sticks", {})
        self.verbose = bool(cfg.get("verbose", True))

    # ---- 工具 ----
    @staticmethod
    def _vk_of(spec: str) -> int | None:
        return VK_NAMES.get(str(spec).upper())

    def _fire(self, name: str, action: dict) -> None:
        kind = action.get("kind", "none")
        if kind == "key":
            vk = self._vk_of(action.get("vk", ""))
            char = action.get("char")
            if vk is None and not char:
                return
            self.sender.tap_key(vk=vk, char=char, hold_ms=int(action.get("hold_ms", 35)))
        elif kind == "mouse_click":
            self.sender.click(action.get("button", "left"), int(action.get("hold_ms", 30)))
        elif kind == "wheel":
            self.sender.wheel(int(action.get("delta", 120)))
        if self.verbose and kind != "none":
            print(f"  -> {name}: {kind} {action.get('vk') or action.get('char') or action.get('button','')}")

    def _is_pressed(self, name: str, st: ControllerState) -> bool:
        if name in ("lt", "rt"):
            return st.triggers[name] >= self.trigger_threshold
        return st.buttons.get(name, False)

    def _hotkey_pause(self) -> None:
        """Ctrl + Alt + G 暂停 / 恢复"""
        u32 = getattr(self.sender, "user32", None)
        if u32 is None:
            return
        ctrl = u32.GetAsyncKeyState(0xA2) & 0x8000
        alt = u32.GetAsyncKeyState(0xA4) & 0x8000
        g = u32.GetAsyncKeyState(0x47) & 0x8000
        if ctrl and alt and g:
            self.paused = not self.paused
            print(f"[{t('bridge.paused') if self.paused else t('bridge.resumed')}]")
            time.sleep(0.6)

    # ---- 主循环 ----
    def step(self) -> None:
        self._hotkey_pause()
        # 手柄 Back + Start 组合：切换暂停
        st = self.backend.poll()
        if not st.connected:
            return
        if self.paused:
            self.prev = st
            return

        # 组合键：Back + Start 长按 1 秒切换暂停
        if st.buttons.get("back") and st.buttons.get("start"):
            if self.combo_hold_start is None:
                self.combo_hold_start = time.time()
            elif time.time() - self.combo_hold_start > 1.0:
                self.paused = True
                self.combo_hold_start = None
                print(t("bridge.paused_pad"))
                time.sleep(0.5)
                return
        else:
            self.combo_hold_start = None

        # 按钮 / 扳机：上升沿触发一次；按住按 repeat_hz 连发
        for name, action in self.bindings.items():
            if not action or action.get("kind", "none") == "none":
                continue
            now_pressed = self._is_pressed(name, st)
            was_pressed = self._is_pressed(name, self.prev)
            if now_pressed and not was_pressed:
                self._fire(name, action)
                self.repeat_at[name] = time.time()
            elif now_pressed:
                hz = float(action.get("repeat_hz", 0))
                if hz > 0:
                    interval = 1.0 / hz
                    if time.time() - self.repeat_at.get(name, 0) >= interval:
                        self._fire(name, action)
                        self.repeat_at[name] = time.time()
            else:
                self.repeat_at.pop(name, None)

        # 摇杆
        for side in ("left", "right"):
            conf = self.stick_mode.get(side, {})
            kind = conf.get("kind", "none")
            if kind == "none":
                continue
            x, y = st.axes[side]
            mag = (x * x + y * y) ** 0.5
            if mag < self.deadzone:
                continue
            if kind == "mouse_move":
                sens = float(conf.get("sensitivity", self.stick_sens))
                dx = int(x * mag * sens)
                dy = int(-y * mag * sens)
                self.sender.move_mouse(dx, dy)

        self.prev = st

    def run(self, hz: int = 120) -> None:
        print(t("bridge.running", hz=hz))
        interval = 1.0 / hz
        last_report = time.time()
        last_hwnd_check = time.time()
        try:
            self._stop = False
            while not self._stop:
                t0 = time.time()
                self.step()
                # 桌宠可能被重启，句柄失效后要重新定位（每 5 秒查一次）
                if time.time() - last_hwnd_check > 5:
                    self.sender.ensure_target()
                    last_hwnd_check = time.time()
                if self.verbose and time.time() - last_report > 30:
                    elapsed = time.time() - self.started_at
                    print(t("bridge.stats", taps=self.sender.taps,
                            moves=self.sender.mouse_moves, mins=elapsed/60))
                    last_report = time.time()
                dt = interval - (time.time() - t0)
                if dt > 0:
                    time.sleep(dt)
        except KeyboardInterrupt:
            pass
        print("\n" + t("bridge.exit", taps=self.sender.taps))

    def stop(self) -> None:
        """给托盘 / 外部调用者用：让 run() 的循环退出。"""
        self._stop = True


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "_comment": "Wuwa Tappo 手柄桥接配置。kind 支持 key / mouse_click / wheel / none；"
                "backend 填 auto 会自动挑可用的（独立SDL > pygame > XInput）；"
                "send_mode 填 post 可绕开焦点/最小化问题（需要桌宠窗口存在）",
    "backend": "auto",
    "send_mode": "post",
    "controller_index": 0,
    "poll_hz": 120,
    "deadzone": 0.25,
    "trigger_threshold": 0.5,
    "stick_mouse_sensitivity": 10,
    "verbose": True,
    "bindings": {
        "a":     {"kind": "key", "vk": "F13", "hold_ms": 35, "repeat_hz": 0},
        "b":     {"kind": "key", "vk": "F14", "hold_ms": 35, "repeat_hz": 0},
        "x":     {"kind": "key", "vk": "F15", "hold_ms": 35, "repeat_hz": 0},
        "y":     {"kind": "key", "vk": "F16", "hold_ms": 35, "repeat_hz": 0},
        "lb":    {"kind": "key", "vk": "F17", "hold_ms": 35, "repeat_hz": 0},
        "rb":    {"kind": "key", "vk": "F18", "hold_ms": 35, "repeat_hz": 0},
        "dpad_up":    {"kind": "key", "vk": "F19", "hold_ms": 35, "repeat_hz": 0},
        "dpad_down":  {"kind": "key", "vk": "F20", "hold_ms": 35, "repeat_hz": 0},
        "dpad_left":  {"kind": "key", "vk": "F21", "hold_ms": 35, "repeat_hz": 0},
        "dpad_right": {"kind": "key", "vk": "F22", "hold_ms": 35, "repeat_hz": 0},
        "lt":    {"kind": "mouse_click", "button": "left", "hold_ms": 30, "repeat_hz": 0},
        "rt":    {"kind": "mouse_click", "button": "right", "hold_ms": 30, "repeat_hz": 0},
        "back":  {"kind": "none"},
        "start": {"kind": "none"},
        "left_stick":  {"kind": "none"},
        "right_stick": {"kind": "none"},
    },
    "sticks": {
        "left":  {"kind": "mouse_move", "sensitivity": 12},
        "right": {"kind": "none"},
    },
}


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        print(f"[{t('common.ok')}] {path}")
        return dict(DEFAULT_CONFIG)
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg)
    merged["bindings"] = dict(DEFAULT_CONFIG["bindings"])
    merged["bindings"].update(cfg.get("bindings", {}))
    merged["sticks"] = dict(DEFAULT_CONFIG["sticks"])
    merged["sticks"].update(cfg.get("sticks", {}))
    return merged


def _try_backend(kind: str, cfg: dict, idx: int, sdl_dll: str | None):
    """返回 (backend, 人类可读描述)；失败抛异常。"""
    if kind == "sdl":
        return SDLBackend(idx), "SDL（pygame）"
    if kind == "sdl-dll":
        path = sdl_dll or cfg.get("sdl_dll_path") or find_sdl_dll([cfg.get("wuwa_tappo_dir", "")])
        if not path:
            raise RuntimeError("找不到 SDL 运行时")
        return (SDLNativeBackend(path, idx,
                                 mapping_file=cfg.get("gamecontrollerdb_path"),
                                 extra_mappings=cfg.get("extra_mappings")),
                f"SDL（独立 DLL：{os.path.basename(path)}）")
    return XInputBackend(idx), "XInput（系统自带）"


def build_backend(cfg: dict, backend_name: str, index: int, sdl_dll: str | None = None):
    """带自动降级的后端构建。

    auto（默认）顺序：独立 SDL.dll -> pygame 的 SDL -> 系统 XInput。
    明确指定某个后端时，失败了也会降级，不会直接退出。
    """
    idx = index if index is not None else int(cfg.get("controller_index", 0))

    if backend_name == "auto":
        chain = ["sdl-dll", "sdl", "xinput"]
    else:
        chain = [backend_name] + [b for b in ("sdl-dll", "sdl", "xinput") if b != backend_name]

    errs = []
    for kind in chain:
        try:
            be, desc = _try_backend(kind, cfg, idx, sdl_dll)
            print(f"{t('bridge.backend')}: {desc}")
            return be
        except Exception as e:  # noqa: BLE001
            errs.append(f"    · {kind}: {e}")
    raise RuntimeError("所有后端都失败了：\n" + "\n".join(errs))


def find_tappo_hwnd() -> int | None:
    """按进程名找到 Wuwa Tappo 的顶层窗口句柄（post 模式要用）。"""
    if not sys.platform.startswith("win"):
        return None

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-Process -Name '*tappo*','*wuwa*','*wuwu*' -ErrorAction SilentlyContinue "
             "| Select-Object -ExpandProperty Id) -join ' '"],
            capture_output=True, text=True, timeout=25, encoding="utf-8", errors="ignore")
        pids = {int(x) for x in re.findall(r"\d+", out.stdout or "")}
    except Exception:
        pids = set()
    if not pids:
        return None

    u32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, ctypes.c_void_p)
    def cb(hwnd, _l):
        pid = wintypes.DWORD(0)
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            found.append(hwnd)
        return True

    u32.EnumWindows(cb, 0)
    return found[0] if found else None


def probe(backend, seconds: int = 15) -> None:
    print(t("bridge.probe_title"))
    end = time.time() + seconds
    seen_any = False
    try:
        while time.time() < end:
            st = backend.poll()
            if st.connected:
                seen_any = True
            tag = t('bridge.probe_connected') if st.connected else t('bridge.probe_disconnected')
            print(f"\r[{tag}] {st.as_line()}    ", end="", flush=True)
            time.sleep(0.08)
    except KeyboardInterrupt:
        pass
    print()
    if not seen_any:
        print("\n" + t("bridge.probe_no_pad"))
        for k in ("bridge.probe_hint1", "bridge.probe_hint2",
                  "bridge.probe_hint3", "bridge.probe_hint4"):
            print("  " + t(k))


def main() -> int:
    base = app_root()
    cfg_path = os.path.join(base, CONFIG_NAME)

    ap = argparse.ArgumentParser(description="Wuwa Tappo 手柄桥接工具")
    ap.add_argument("--backend", choices=["auto", "xinput", "sdl", "sdl-dll"], default="auto",
                    help="auto=自动挑最好的（默认）；xinput=系统自带(仅Xbox系)；"
                         "sdl=pygame；sdl-dll=直接用 SDL.dll（覆盖手柄最广）")
    ap.add_argument("--sdl-dll", default=None, help="SDL2.dll / SDL3.dll 的路径")
    ap.add_argument("--index", type=int, default=None, help="手柄序号")
    ap.add_argument("--probe", action="store_true", help="只探测手柄状态，不发送输入")
    ap.add_argument("--probe-seconds", type=int, default=15)
    ap.add_argument("--dry-run", action="store_true", help="解析映射但真的不发送键鼠事件")
    ap.add_argument("--log", nargs="?", const=LOG_NAME, default=None,
                    help="同时把输出写进日志文件（后台运行时强烈建议开）")
    ap.add_argument("--allow-multiple", action="store_true",
                    help="允许同时跑多个实例（默认禁止，避免按键发两遍）")
    ap.add_argument("--send-mode", choices=["sendinput", "post", "both"], default=None,
                    help="sendinput=系统级(默认，受焦点影响)；post=直投桌宠窗口(不受最小化和焦点影响)；both=两条都发")
    ap.add_argument("--hwnd", type=lambda x: int(x, 0), default=None,
                    help="post 模式的目标窗口句柄，0x 开头。不给就自动找")
    args = ap.parse_args()

    if args.log:
        enable_file_log(os.path.join(base, args.log) if not os.path.isabs(args.log) else args.log)

    if not args.allow_multiple and not ensure_single_instance():
        print(t("bridge.dup_instance"))
        print("       " + t("bridge.dup_hint"))
        return 0

    cfg = load_config(cfg_path)
    backend_name = args.backend or cfg.get("backend", "auto")
    if backend_name not in ("auto", "xinput", "sdl", "sdl-dll"):
        backend_name = "auto"

    try:
        backend = build_backend(cfg, backend_name, args.index, args.sdl_dll)
    except Exception as e:  # noqa: BLE001
        print(f"[{t('common.error')}] {e}")
        print("       " + t("bridge.hint_sdl"))
        return 1

    if args.probe:
        probe(backend, args.probe_seconds)
        backend.close()
        return 0

    send_mode = args.send_mode or cfg.get("send_mode", "post")
    hwnd = args.hwnd
    if send_mode in ("post", "both") and hwnd is None:
        hwnd = find_tappo_hwnd()
        if hwnd:
            print(f"[{t('bridge.window_found')}] 0x{hwnd:X}")
    if hwnd:
        cfg["hwnd"] = hwnd

    sender = InputSender(enabled=not args.dry_run, send_mode=send_mode, target_hwnd=hwnd)
    print(f"{t('bridge.channel')}: {sender.send_mode}"
          + (f" → 0x{sender.hwnd:X}" if sender.hwnd else ""))
    bridge = GamepadBridge(backend, sender, cfg)
    if args.dry_run:
        print(t("bridge.dry_run"))
    bridge.run(hz=int(cfg.get("poll_hz", 120)))
    backend.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        # 后台模式（pythonw / 托盘）看不到控制台，异常必须落到日志
        import traceback
        tb = traceback.format_exc()
        try:
            with open(os.path.join(app_root(), "bridge.log"), "a", encoding="utf-8") as f:
                f.write("\n==== crash ====\n" + tb + "\n")
        except Exception:
            pass
        print(tb)
        sys.exit(1)
