# Wuwa Tappo · 手柄桥接

> [!WARNING]
> **本仓库已停止维护（DEPRECATED / ARCHIVED）**
>
> **Wuwa Tappo 官方已原生支持手柄**，不再需要这个桥接工具。
> 请直接使用官方功能，卸载并删除本项目。
>
> 代码保留仅作归档，不再修复问题、不再适配新版客户端，也不再接受功能建议。
> 继续使用可能在新版本客户端上失效，请自行承担风险。

> [!WARNING]
> **This repository is deprecated and no longer maintained.**
>
> **Wuwa Tappo now supports gamepads natively** - this bridge is no
> longer needed. Please use the official feature instead, and remove
> this project.
>
> Kept for archival purposes only. No fixes, no compatibility updates
> for newer client versions, no feature requests. If you keep using it,
> it may break after a client update - at your own risk.

---

> **English / 繁體中文** — 支持三种界面语言，首次启动时会让你选，之后记住。

本项目诞生于 Wuwa Tappo **尚不支持手柄**的时期：把手柄输入翻译成键鼠事件喂给它，
让桌宠跟着手柄一起拍桌子。**不修改、不注入、不读取 Wuwa Tappo 的任何文件或内存。**

**现在官方已原生支持手柄，这个工具的使命已经结束。**

---

## 为什么停用

官方在后续版本中**原生加入了手柄支持**。既然官方已经做好了，
这个第三方桥接就没有存在意义了 —— 官方实现更稳定、更贴合客户端、
也不会有任何合规风险。

感谢每一位用过它的朋友。

## 建议

- **新用户**：直接用官方的手柄功能，不需要下载本仓库。
- **老用户**：卸载并删除本项目（`stop.bat` 停止运行后删掉整个文件夹即可）。
  记得把开机自启关掉（`toggle_autorun.bat`）。

---

# 以下为历史归档内容（不建议使用）

> [!NOTE]
> 从这一段往下都是**归档内容**，仅用于说明这个工具当年是怎么做的。
> **请不要再照着它安装使用。** 官方手柄支持已经覆盖了这些需求。

## 三步开始

### 1. 下载 SDL2.dll（可选）

> **本仓库不附带任何 DLL，也不提供自动下载。** 官方下载速度因人而异，所以地址给你，自己下。

<https://github.com/libsdl-org/SDL/releases>

取最新版的 **`SDL2-2.xx.x-win32-x64.zip`**（VC、64 位），解压出 `SDL2.dll`，放进：

```
sdl_runtime/          ← 推荐
```
或
```
仓库根目录/           ← 也认
```

**不放也能用**：自动退回系统 XInput，Xbox 系手柄正常工作。
PS / Switch / 八位堂手柄才需要 SDL。

### 2. 双击 `launch.bat`

首次启动会问语言（简体中文 / 繁體中文 / English），选完存进 `lang.txt`，以后不再问。
想改随时跑 `launch.bat --lang`，或在托盘菜单里改。

然后它会检查 SDL2.dll、检查 Wuwa Tappo 在不在跑，最后启动托盘程序。

### 3. 托盘里操作

- **左键双击**图标 = 暂停 / 恢复
- **右键** = 菜单（切通道、切后端、探测手柄、改语言、改配置……）
- 手柄 **Back + Start 长按 1 秒**，或 **Ctrl+Alt+G**，也能暂停

> Windows 可能把图标折进任务栏的 `∧` 里，去那里拖出来。

---

## 文件

| 文件 | 作用 | 关窗口会停吗 |
|---|---|---|
| `launch.bat` | **日常用这个**，真正后台运行 | **不会** |
| `debug.bat` | 托盘不出图标时排错，错误实时显示 | 会（设计如此） |
| `viewlog.bat` | 查看后台日志 `bridge.log` | — |
| `USAGE.txt` | **使用说明**（三语）：使用、DLL 地址、后果与禁止事项 | — |
| `NOTICE.txt` | **开源许可与第三方组件** | — |
| `launch_console.bat` | 控制台跑桥接（不进托盘） | 会 |
| `check.bat` | 只检查环境，不启动 | — |
| `stop.bat` | 彻底停掉所有实例 | — |
| `toggle_autorun.bat` | 开关登录自启 | — |
| `diagnose.bat` | 排查「最小化就失效」 | — |
| `tray_launcher.vbs` | 无窗口启动器，开机自启指向它 | 不会 |

### 三种启动方式的区别

| 方式 | 进程 | 关掉窗口 |
|---|---|---|
| `launch.bat` | 独立进程（`pythonw.exe`，无控制台） | **继续运行** |
| `debug.bat` | 挂在 cmd 窗口下的子进程 | 跟着停止 |

**`debug.bat` 关窗口就停是设计如此** —— 它的存在就是为了让你能看见错误，
所以特意带控制台。排完错日常请回到 `launch.bat`。

后台运行时所有输出都写进 `bridge.log`，用 `viewlog.bat` 查看。

源码都在 `src/`：

| 文件 | 作用 |
|---|---|
| `launcher.py` | 统一入口：语言选择 + 环境检查 + 启动托盘 |
| `i18n.py` | 三语文案表 |
| `tray_app.py` | 托盘控制器，整合全部功能 |
| `gamepad_bridge.py` | 桥接核心：读手柄 + 合成键鼠事件 |
| `diagnose.py` | 输入通道诊断 |
| `inspect_exe.py` | 技术栈探针（可选，纯研究用） |

运行时生成：`config.json`、`bridge.log`、`lang.txt`。

## 语言

三种：**简体中文** / **繁體中文** / **English**。

- 首次启动选择，存进 `lang.txt`
- 改语言：`launch.bat --lang`，或托盘菜单 →「语言 / 語言 / Language」
- 也可以直接编辑 `lang.txt` 填 `sc` / `tc` / `en`

控制台输出会自动切成 UTF-8 代码页，中文和繁体都不会乱码。


## 默认键位

| 手柄 | 动作 |
|---|---|
| A / B / X / Y、LB / RB、方向键 | 各映射一个 F13~F24（软件里无默认绑定，不会往文档插字符，但会触发拍桌） |
| LT / RT | 鼠标左键 / 右键 |
| 左摇杆 | 移动鼠标 |
| Back + Start（长按 1 秒） | 暂停 |
| Ctrl + Alt + G | 暂停 |

想让按键真的敲出字符来攒「字符数」，改 `config.json` 里对应项的 `char` 即可。

## 托盘图标没出现？按这个顺序查

1. **先杀干净**：跑 `stop.bat`。旧实例会占着互斥量，导致新实例启动后立刻退出。
2. **跑 `debug.bat`**：它用带控制台的 Python 启动托盘程序，所有错误直接打印在窗口里。
   托盘图标照样会出现——只是错误不再被隐藏。
3. **看 `bridge.log`**：后台模式的异常都追加到这里。
4. **图标可能被折叠了**：Windows 默认把不活跃图标收进任务栏的 `∧`。
   去那里把图标拖回任务栏，或在「任务栏设置 → 选择哪些图标显示在任务栏上」里打开它。
5. **确认 Python 装对了**：`python --version` 要有输出，且安装时勾了 "Add python.exe to PATH"。

`launch.bat` 检测到托盘程序启动后 3 秒内退出时，会明确告诉你去看 `debug.bat` 和 `bridge.log`。

## 常见问题

**最小化窗口就没效果了**
焦点问题。默认已是 **post 模式**（直投桌宠窗口），不需要焦点，最小化也照常。
万一失效，跑 `diagnose.bat` 实测哪条通道有效。

**手柄没反应**
托盘菜单 →「探测手柄」，看数值跳不跳。PS / 八位堂需要 SDL2.dll。

**SDL 下载慢**
所以本仓库不代劳——地址给你，挑个快的方式下完放进去就行，脚本只负责识别。

**桌宠重启后没效果**
桥接每 5 秒自动重新定位桌宠窗口。菜单里也有「重新定位桌宠窗口」。

**`launch.bat` 一闪而过**
跑 `launch_console.bat`，错误会显示在窗口里。

## 它是怎么工作的

```
手柄 ──► SDL / XInput 轮询 ──► 归一化按钮·摇杆·扳机
                                      │
                                      ▼
                        合成键鼠事件（SendInput）
                        或直投窗口（PostMessage）
                                      │
                                      ▼
                              Wuwa Tappo（完全不知情）
```

全程只在**自己的进程**里跑。不碰 Wuwa Tappo 的进程、文件、内存和网络。
`SendInput` 是系统公开的输入合成接口，效果等同于真人敲键盘；
`PostMessage` 只是往它窗口的消息队列塞消息。

**不会做的事**：不逆向联机协议、不伪造封包、不注入、不自建私服、不自动化刷奖励。

## 环境要求

- Windows 10 / 11
- Python 3.10+（安装时勾选 "Add python.exe to PATH"）
- 可选：SDL2.dll（zlib 许可，用户自行从官方获取）

零第三方依赖即可运行（Xbox 手柄）。

## 说明

- **使用前请读完 `USAGE.txt`**：第四节讲使用后果，第五节列绝对不要做的事。
- 请遵守 Wuwa Tappo 的用户协议。别用 `repeat_hz` 拉满去刷宝箱。
- 那是第三方辅助工具的通用原则，不是官方手册原文；
  实际条款以官方最新公布的用户协议为准。
- 本项目是非官方的第三方工具，与 Kuro Games 及 Wuwa Tappo 官方没有任何关联。
- 代码 MIT 许可，详见 [LICENSE](LICENSE)。
  SDL2 本身是 zlib 许可，不随本仓库分发。
