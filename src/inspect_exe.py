# -*- coding: utf-8 -*-
"""
Wuwa Tappo · 单文件版技术栈探针
================================

单文件版把所有 DLL 都嵌进 exe 里了，没法直接 copy SDL2.dll。
这个脚本解决两件事：
  1) 确认它到底是不是 Unity + SDL 壳（决定了后续怎么接手柄）
  2) 如果 SDL 确实被嵌在 exe 资源里，直接把它 dump 出来给 gamepad_bridge.py 用

只读操作：不启动、不修改、不注入 Wuwa Tappo。

用法：
    python inspect_exe.py                 # 自动找 exe 并扫描
    python inspect_exe.py --exe D:\\Game\\WuwaTappo\\WuwaTappo.exe
    python inspect_exe.py --dump          # 把资源里疑似 DLL 的东西导出来
    python inspect_exe.py --dump --out ./sdl_from_wuwa

输出里的「结论」部分直接贴给别人看就行。
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import subprocess
import sys
from ctypes import wintypes

# Windows 控制台默认 GBK，Python 3 默认 UTF-8 输出会崩。强制 UTF-8 + 替换坏字符。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

IS_WIN = sys.platform.startswith("win")

# ---------------------------------------------------------------------------
# 特征串：命中即说明对应技术存在
# ---------------------------------------------------------------------------

SIGNATURES = {
    "Unity 引擎": [b"UnityPlayer.dll", b"unityplayer", b"UnityEngine", b"MonoBehaviour",
                b"il2cpp", b"mono-2.0-bdwgc", b"UnityCrashHandler"],
    "SDL2":      [b"SDL2.dll", b"SDL_Init", b"SDL_GameControllerOpen", b"gamecontrollerdb",
                b"SDL_PumpEvents", b"SDL_GetError"],
    "SDL3":      [b"SDL3.dll", b"SDL_OpenGamepad", b"SDL_GetGamepads", b"SDL_UpdateGamepads"],
    "XInput":    [b"XInputGetState", b"xinput1_4.dll", b"xinput1_3.dll", b"XInput1_4"],
    "DirectInput": [b"DirectInput8Create", b"dinput8.dll", b"IDirectInputDevice8"],
    "Raw Input": [b"RegisterRawInputDevices", b"WM_INPUT", b"GetRawInputData"],
    "键盘钩子":   [b"SetWindowsHookEx", b"WH_KEYBOARD_LL", b"WH_MOUSE_LL"],
    "轮询按键":   [b"GetAsyncKeyState", b"GetKeyState", b"GetKeyboardState"],
    "Live2D":    [b"Live2D", b"Cubism", b"csmUpdateModel", b"cubismcore"],
    "Electron":  [b"app.asar", b"electron", b"node.dll", b"CHROME_VERSION"],
    "CEF":       [b"libcef.dll", b"cef_string", b"Chromium"],
    "Qt":        [b"Qt5Core.dll", b"Qt6Core.dll", b"qVersion"],
    "Spine":     [b"spine-cpp", b"spSkeleton_update", b"Spine"],
    "Steamworks": [b"Steamworks.NET", b"steam_api64.dll", b"SteamAPI_Init",
                   b"ISteamUserStats", b"SteamUserStats()"],
    # 单文件打包器：认出它才知道依赖藏在哪
    "自解压壳":   [b"This program cannot be run in DOS mode", b"_MEIPASS", b"PYZ-00.pyz",
                b"pyi-windows-manifest-filename", b"NSIS", b"Inno Setup", b"7-Zip SFX"],
    "PyInstaller": [b"_MEIPASS", b"pyi-", b"PYZ-00.pyz", b"pyimod02_importers"],
    "NuitkaOneFile": [b"nuitka", b"__nuitka_"],
}


# ---------------------------------------------------------------------------
# 找 exe
# ---------------------------------------------------------------------------

def _ps(cmd: str, timeout: int = 30) -> list[str]:
    """跑一段 PowerShell，收集输出的每行非空路径。"""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, timeout=timeout,
                             encoding="utf-8", errors="ignore")
        return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except Exception:
        return []


def _ps_process_paths() -> list[str]:
    """拿正在运行的进程路径。多管几路，防止进程名不叫 WuwaTappo。"""
    hits: list[str] = []

    # A. 按名字模糊匹配
    hits += _ps(r"(Get-Process -Name '*tappo*','*wuwa*','*wuwu*' -ErrorAction SilentlyContinue "
               r"| Where-Object {$_.Path} | Select-Object -ExpandProperty Path) -join \"`n\"")
    # B. 所有有窗口标题的进程：标题含「鸣潮」「Wuwa」「Tappo」
    hits += _ps(r"(Get-Process -ErrorAction SilentlyContinue "
               r"| Where-Object {$_.MainWindowTitle -match 'Wuwa|Tappo|鸣潮|桌宠' -and $_.Path} "
               r"| Select-Object -ExpandProperty Path) -join \"`n\"")
    # C. 兜底：列出全部进程路径，本地再过滤（慢但最全）
    allp = _ps(r"(Get-Process -ErrorAction SilentlyContinue "
               r"| Where-Object {$_.Path} "
               r"| Select-Object Name,@{n='P';e={$_.Path}} "
               r"| ForEach-Object { $_.Name + '|' + $_.P }) -join \"`n\"")
    for line in allp:
        if "|" not in line:
            continue
        name, path = line.split("|", 1)
        if re.search(r"tappo|wuw?a|kuro|库洛", name + path, re.I):
            hits.append(path)

    return [p for p in hits if os.path.exists(p)]


def _registry_candidates() -> list[str]:
    """从卸载表 / App Paths 里找安装位置。"""
    hits: list[str] = []
    ps = r"""
$out = @()
$keys = @(
  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
foreach ($k in $keys) {
  Get-ItemProperty $k -ErrorAction SilentlyContinue | ForEach-Object {
    $txt = ($_.DisplayName, $_.DisplayIcon, $_.InstallLocation, $_.UninstallString) -join ' '
    if ($txt -match 'tappo|wuw?a|鸣潮|库洛') {
      if ($_.InstallLocation) { $out += $_.InstallLocation }
      if ($_.DisplayIcon) { $out += ($_.DisplayIcon -replace '^"|".*$','') }
      if ($_.UninstallString) { $out += (Split-Path ($_.UninstallString -replace '^"|".*$','')) }
    }
  }
}
Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\*' -ErrorAction SilentlyContinue |
  Where-Object { $_.'(default)' -match 'tappo|wuw?a' } | ForEach-Object { $out += ($_.'(default)' -replace '^"|".*$','') }
$out -join "`n"
"""
    for line in _ps(ps):
        p = line.strip().strip('"')
        if os.path.isdir(p):
            for root, _d, files in os.walk(p):
                for f in files:
                    if f.lower().endswith(".exe") and re.search(r"tappo|wuw?a", f, re.I):
                        hits.append(os.path.join(root, f))
                break
        elif os.path.isfile(p) and p.lower().endswith(".exe"):
            hits.append(p)
    return hits


def _shortcut_candidates() -> list[str]:
    """解开始菜单 / 桌面快捷方式。"""
    ps = r"""
$sh = New-Object -ComObject WScript.Shell
$dirs = @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
          "$env:ProgramData\Microsoft\Windows\Start Menu\Programs",
          "$env:USERPROFILE\Desktop", "$env:PUBLIC\Desktop")
$out = @()
foreach ($d in $dirs) {
  if (Test-Path $d) {
    Get-ChildItem $d -Recurse -Filter *.lnk -ErrorAction SilentlyContinue | ForEach-Object {
      $t = $sh.CreateShortcut($_.FullName).TargetPath
      if ($t -match 'tappo|wuw?a') { $out += $t }
    }
  }
}
$out -join "`n"
"""
    return [p for p in _ps(ps) if os.path.exists(p) and p.lower().endswith(".exe")]


def _glob_candidates(deep: bool = False) -> list[str]:
    """文件系统扫描。deep=True 会扫固定磁盘前几层，慢但全。"""
    roots: list[str] = []
    for var in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "USERPROFILE",
                "APPDATA", "PUBLIC", "ALLUSERSPROFILE"):
        v = os.environ.get(var)
        if v and os.path.isdir(v):
            roots.append(v)

    if IS_WIN:
        try:
            import string
            drives = [f"{c}:\\" for c in string.ascii_uppercase if os.path.isdir(f"{c}:\\")]
        except Exception:
            drives = []
        for d in drives:
            roots.append(d)
            for sub in ("Program Files", "Program Files (x86)", "Game", "Games",
                        "Software", "software", "Soft", "Tools", "Apps",
                        "Kuro Games", "库洛", "Wuthering Waves", "鸣潮"):
                # 大小写不同的同名目录都算上
                for cand in {sub, sub.lower(), sub.capitalize()}:
                    p = os.path.join(d, cand)
                    if os.path.isdir(p):
                        roots.append(p)

    hits: list[str] = []
    seen_dirs: set[str] = set()
    max_depth = 6 if deep else 4
    for r in roots:
        try:
            for root, dirs, files in os.walk(r):
                depth = root.rstrip("\\/").count(os.sep)
                if depth > max_depth:
                    dirs[:] = []
                    continue
                # 目录名带关键字就进去，否则只在浅层找
                if depth > 2 and not re.search(r"tappo|wuw?a|kuro|库洛|鸣潮", root, re.I):
                    dirs[:] = []
                if root in seen_dirs:
                    continue
                seen_dirs.add(root)
                for f in files:
                    if f.lower().endswith(".exe") and re.search(r"tappo|wuw?a", f, re.I):
                        hits.append(os.path.join(root, f))
        except Exception:
            continue
    return hits


def locate_exe(explicit: str | None = None, deep: bool = False) -> tuple[str | None, list[str]]:
    if explicit:
        p = explicit.strip().strip('"')
        return (p if os.path.exists(p) else None), []

    print("[搜索] 正在运行的进程 ...")
    cands = _ps_process_paths()
    if not cands:
        print("[搜索] 卸载表 / App Paths ...")
        cands = _registry_candidates()
    if not cands:
        print("[搜索] 开始菜单与桌面快捷方式 ...")
        cands = _shortcut_candidates()
    if not cands:
        print(f"[搜索] 文件系统（deep={deep}，加 --deep-scan 扫得更全但慢）...")
        cands = _glob_candidates(deep=deep)

    uniq, seen = [], set()
    for p in cands:
        p = os.path.abspath(p)
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return (uniq[0] if uniq else None), uniq


# ---------------------------------------------------------------------------
# 二进制特征扫描
# ---------------------------------------------------------------------------

def scan_bytes(blob: bytes, size_mb: float) -> dict[str, list[tuple[str, int]]]:
    """返回 {技术名: [(命中串, 命中次数)]}。大文件只扫头部和尾部，够用了。"""
    head = blob[: 40 << 20]
    tail = blob[-20 << 20:] if len(blob) > 60 << 20 else b""
    hay = head + tail
    res: dict[str, list[tuple[str, int]]] = {}
    for tech, pats in SIGNATURES.items():
        hits = []
        for p in pats:
            n = hay.count(p)
            if n:
                hits.append((p.decode("ascii", "ignore"), n))
        if hits:
            res[tech] = sorted(hits, key=lambda x: -x[1])
    return res


# ---------------------------------------------------------------------------
# 资源枚举 + dump（Windows 原生 API，只读）
# ---------------------------------------------------------------------------

RT_RCDATA = 10
LOAD_LIBRARY_AS_IMAGE_RESOURCE = 0x00000020
LOAD_LIBRARY_AS_DATAFILE = 0x00000002


def _is_int_resource(p) -> bool:
    return p is not None and (int(p) >> 16) == 0


def enum_resources(path: str) -> list[tuple[int | str, int | str, int]]:
    """列出 exe 里所有资源项 -> [(type, name, size)]。"""
    if not IS_WIN:
        return []
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    hmod = k32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_IMAGE_RESOURCE)
    if not hmod:
        hmod = k32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_DATAFILE)
    if not hmod:
        return []

    k32.EnumResourceTypesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p]
    k32.EnumResourceNamesW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
    k32.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    k32.FindResourceW.restype = wintypes.HANDLE
    k32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    k32.SizeofResource.restype = wintypes.DWORD

    types: list[int | str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p, ctypes.c_void_p)
    def _type_cb(_h, lpszType, _lp):
        if _is_int_resource(lpszType):
            types.append(int(lpszType))
        else:
            types.append(ctypes.wstring_at(lpszType))
        return True

    k32.EnumResourceTypesW(hmod, _type_cb, 0)

    items: list[tuple[int | str, int | str, int]] = []

    def _size_of(rtype, rname) -> int:
        t = wintypes.LPCWSTR(rtype) if isinstance(rtype, int) else rtype
        n = wintypes.LPCWSTR(rname) if isinstance(rname, int) else rname
        hrs = k32.FindResourceW(hmod, n, t)
        if not hrs:
            return 0
        return k32.SizeofResource(hmod, hrs)

    for rtype in types:
        names: list[int | str] = []

        def _mk(rt):
            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
                                ctypes.c_void_p, ctypes.c_void_p)
            def _name_cb(_h, _t, lpszName, _lp):
                if _is_int_resource(lpszName):
                    names.append(int(lpszName))
                else:
                    names.append(ctypes.wstring_at(lpszName))
                return True
            return _name_cb

        t_arg = wintypes.LPCWSTR(rtype) if isinstance(rtype, int) else rtype
        k32.EnumResourceNamesW(hmod, t_arg, _mk(rtype), 0)
        for rname in names:
            items.append((rtype, rname, _size_of(rtype, rname)))

    k32.FreeLibrary.argtypes = [wintypes.HMODULE]
    k32.FreeLibrary(hmod)
    return items


def dump_resources(path: str, out_dir: str) -> list[tuple[str, int, str]]:
    """把资源里以 MZ 开头（PE 文件）的 blob 写成 dll。返回 [(文件名, 大小, 备注)]。"""
    if not IS_WIN:
        return []
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
    k32.LoadLibraryExW.restype = wintypes.HMODULE
    k32.FindResourceW.argtypes = [wintypes.HMODULE, wintypes.LPCWSTR, wintypes.LPCWSTR]
    k32.FindResourceW.restype = wintypes.HANDLE
    k32.LoadResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    k32.LoadResource.restype = wintypes.HANDLE
    k32.LockResource.argtypes = [wintypes.HANDLE]
    k32.LockResource.restype = ctypes.c_void_p
    k32.SizeofResource.argtypes = [wintypes.HMODULE, wintypes.HANDLE]
    k32.SizeofResource.restype = wintypes.DWORD

    hmod = k32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_IMAGE_RESOURCE) or \
        k32.LoadLibraryExW(path, None, LOAD_LIBRARY_AS_DATAFILE)
    if not hmod:
        return []

    os.makedirs(out_dir, exist_ok=True)
    dumped: list[tuple[str, int, str]] = []
    for rtype, rname, size in enum_resources(path):
        if size < 20_000:          # SDL2.dll 至少几百 KB，小资源直接跳过
            continue
        t = wintypes.LPCWSTR(rtype) if isinstance(rtype, int) else rtype
        n = wintypes.LPCWSTR(rname) if isinstance(rname, int) else rname
        hrs = k32.FindResourceW(hmod, n, t)
        if not hrs:
            continue
        hglob = k32.LoadResource(hmod, hrs)
        if not hglob:
            continue
        ptr = k32.LockResource(hglob)
        if not ptr:
            continue
        blob = ctypes.string_at(ptr, size)
        if blob[:2] != b"MZ":
            continue
        # 凭内部特征猜它是谁
        tag = []
        if b"SDL_GameController" in blob or b"SDL_Init" in blob:
            tag.append("SDL2")
        if b"SDL_OpenGamepad" in blob or b"SDL_GetGamepads" in blob:
            tag.append("SDL3")
        if b"UnityPlayer" in blob or b"UnityEngine" in blob:
            tag.append("UnityPlayer")
        stem = "_".join(tag) if tag else "unknown"
        fname = f"{stem}_{rtype}_{rname}.dll"
        with open(os.path.join(out_dir, fname), "wb") as f:
            f.write(blob)
        dumped.append((fname, size, " / ".join(tag) or "未知 DLL"))
    k32.FreeLibrary(hmod)
    return dumped


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

# 已知 Steam AppID -> 游戏名。命中即能反推它的血统。
KNOWN_APPIDS = {
    "3419430": "Bongo Cat（Irox Games，Unity + SDL + SteamworksNET）",
    "480": "Spacewar（Steamworks 测试用默认 AppID，开发者偷懒没改）",
}


def _scan_siblings(path: str) -> dict:
    """扫 exe 同目录：结构判定 + steam_appid.txt 解读。"""
    info: dict = {"dir": os.path.dirname(path), "files": [], "appid": None, "appid_note": None,
                  "data_dir": None, "asar": None}
    d = info["dir"]
    try:
        for e in os.scandir(d):
            if e.is_file():
                info["files"].append((e.name, e.stat().st_size))
            elif e.is_dir():
                if re.search(r"_Data$", e.name, re.I):
                    info["data_dir"] = e.name
                asar = os.path.join(e.path, "app.asar")
                if os.path.exists(asar) or e.name.lower() == "resources":
                    info["asar"] = e.name
    except Exception:
        return info

    for name, _sz in info["files"]:
        if name.lower() == "steam_appid.txt":
            try:
                with open(os.path.join(d, name), "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read().strip().strip('"')
                m = re.search(r"\d{4,}", txt)
                if m:
                    info["appid"] = m.group(0)
                    info["appid_note"] = KNOWN_APPIDS.get(m.group(0))
            except Exception:
                pass
    return info


def render_report(path: str, hits: dict, res_items: list, dumped: list) -> None:
    size_mb = os.path.getsize(path) / (1 << 20)
    sib = _scan_siblings(path)

    print("=" * 66)
    print(f"文件：{path}")
    print(f"大小：{size_mb:.1f} MB")
    print("=" * 66)

    print("\n【零】安装目录结构")
    for name, sz in sorted(sib["files"], key=lambda x: -x[1])[:12]:
        print(f"    {name:<32} {sz/1024:>10.0f} KB")
    if sib["data_dir"]:
        print(f"  · 发现 {sib['data_dir']} → 常规 Unity 构建")
    if sib["asar"]:
        print(f"  · 发现 {sib['asar']} → 常规 Electron 构建")
    if not sib["data_dir"] and not sib["asar"]:
        print("  · 没有 _Data / app.asar → 单文件打包器产物，依赖全在 exe 里")
    if sib["appid"]:
        print(f"  · steam_appid.txt = {sib['appid']}"
              + (f"  → {sib['appid_note']}" if sib["appid_note"] else "（未知 AppID）"))
        if sib["appid"] == "3419430":
            print("    ★ 这是 Bongo Cat 自己的 AppID，血统坐实：Unity + SDL + SteamworksNET")
        elif sib["appid"] == "480":
            print("    ★ Spacewar 是 Steamworks 的测试默认 ID，说明它只是继承了 Steamworks 集成")

    print("\n【一】二进制特征命中")
    if not hits:
        print("  什么都没命中，可能加了壳或压缩。")
    for tech, items in hits.items():
        detail = "，".join(f"{s}×{n}" for s, n in items[:4])
        print(f"  ✔ {tech:<10} {detail}")

    print("\n【二】PE 资源（单文件版会把依赖藏在这）")
    if not res_items:
        print("  没枚举到资源。")
    else:
        big = [x for x in res_items if x[2] >= 20_000]
        print(f"  资源总数 {len(res_items)}，其中 ≥20KB 的 {len(big)} 个（DLL 级）")
        for t, n, s in sorted(big, key=lambda x: -x[2])[:12]:
            print(f"    type={t!s:<8} name={n!s:<10} {s/1024:>8.0f} KB")

    if dumped:
        print("\n【三】已导出的 DLL")
        for fname, size, tag in dumped:
            print(f"    {fname}  {size/1024:.0f} KB  → {tag}")

    # ---- 结论 ----
    print("\n【结论】")
    unity = "Unity 引擎" in hits
    sdl = "SDL2" in hits or "SDL3" in hits
    xinput = "XInput" in hits
    raw = "Raw Input" in hits
    hook = "键盘钩子" in hits
    poll = "轮询按键" in hits

    if unity:
        print("  · 它是 Unity 做的，跟 Steam 版 Bongo Cat 同一个引擎底子。")
    elif "Electron" in hits or "CEF" in hits:
        print("  · 它是 Electron / CEF 壳，不是 Unity；SDL 那条路不适用，"
              "但键鼠事件注入照样有效。")
    else:
        print("  · 引擎特征不明显，可能加壳了。")

    if sdl:
        print("  · ✔ 里面确实有 SDL。Gamepad API 就在它肚子里，只是没启用。")
        if dumped:
            print("  · 上面导出的 DLL 直接给 gamepad_bridge.py 用：")
            print("      python gamepad_bridge.py --backend sdl-dll --sdl-dll <路径> --probe")
        else:
            print("  · 加 --dump 再跑一次就能把 SDL 抠出来；抠不出来也没关系，看下面。")
    else:
        print("  · ✘ 没检测到 SDL。库洛可能是自己重写了输入层，那 SDL 得自己备一份（见下）。")

    print("  · 输入层判定：", end="")
    parts = []
    if raw:
        parts.append("Raw Input（系统原始输入，最可能的方案）")
    if hook:
        parts.append("全局钩子")
    if poll:
        parts.append("GetAsyncKeyState 轮询")
    if xinput:
        parts.append("XInput")
    print("、".join(parts) or "没看出来")
    print("    → 无论哪一种，SendInput 合成的键鼠事件它都收得到，桥接方案成立。")

    print("\n【SDL 从哪来（单文件版必备）】")
    print("  单文件版没有散落的 dll 可拷，任选其一：")
    print("    1. 上面 --dump 抠出来的（如果命中的话）")
    print("    2. 官网下载 https://github.com/libsdl-org/SDL/releases")
    print("       取 SDL2-2.xx.x-win32-x64.zip（VC、64 位），解压出 SDL2.dll")
    print("    3. 放进 sdl_runtime\\ 或仓库根目录")
    print("  拿到后：python gamepad_bridge.py --backend sdl-dll --sdl-dll SDL2.dll --probe")


def main() -> int:
    if not IS_WIN:
        print("这个脚本要在 Windows 上跑（要用 kernel32 的资源 API）。")
        return 2

    ap = argparse.ArgumentParser(description="Wuwa Tappo 单文件版技术栈探针")
    ap.add_argument("--exe", default=None, help="WuwaTappo.exe 的路径，不给就自动找")
    ap.add_argument("--dump", action="store_true", help="把资源里疑似 DLL 的 blob 导出来")
    ap.add_argument("--out", default="./dumped_dll", help="导出目录")
    ap.add_argument("--deep-scan", action="store_true", help="全盘深扫（慢，1~3 分钟）")
    ap.add_argument("--list-procs", action="store_true",
                    help="列出所有运行中进程的路径（找 exe 用，把输出贴回来即可）")
    args = ap.parse_args()

    if args.list_procs:
        rows = _ps(r"(Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.Path} "
                   r"| Select-Object @{n='L';e={$_.Name.PadRight(34) + $_.Path}} "
                   r"| Select-Object -ExpandProperty L) -join \"`n\"", timeout=40)
        hit = [r for r in rows if re.search(r"tappo|wuw?a|kuro", r, re.I)]
        print("== 疑似命中 ==" if hit else "== 没有一眼能认出来的，下面是全部进程 ==")
        for r in (hit or rows):
            print("  " + r)
        if hit:
            print(f"\n上面这几条直接拿去用：--exe \"{hit[0].split(maxsplit=1)[-1].strip()}\"")
        return 0

    path, cands = locate_exe(args.exe, deep=args.deep_scan)
    if not path:
        print("\n没找到 WuwaTappo.exe。最快的两条路：")
        print("  1) 在 Wuwa Tappo 的托盘图标上右键 → 打开文件所在位置，"
              "把地址栏路径复制给我，或直接用 --exe 指定")
        print("  2) 跑这条 PowerShell，把输出贴回来：")
        print(r'     Get-Process | Where-Object {$_.Path} | '
              r'Select-Object Name,Path | Format-List')
        if cands:
            print("\n候选：")
            for c in cands[:10]:
                print("  " + c)
        return 1
    if len(cands) > 1:
        print(f"（找到 {len(cands)} 个候选，用第一个。要换请用 --exe）")

    print("[1/3] 读文件并扫描特征...")
    with open(path, "rb") as f:
        blob = f.read()
    hits = scan_bytes(blob, os.path.getsize(path) / (1 << 20))

    print("[2/3] 枚举 PE 资源...")
    res_items = enum_resources(path)

    dumped: list[tuple[str, int, str]] = []
    if args.dump:
        print(f"[3/3] 导出疑似 DLL 到 {args.out} ...")
        dumped = dump_resources(path, args.out)
    else:
        print("[3/3] 跳过导出（加 --dump 可把 SDL 抠出来）")

    print()
    render_report(path, hits, res_items, dumped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
