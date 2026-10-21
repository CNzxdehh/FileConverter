# 转换文件格式 —— Windows 右键菜单扩展

在 Windows 资源管理器的**右键菜单**里加一个【转换文件格式】的级联菜单，选中文件（可多选）后直接
转 PDF / Word / TXT / 图片 / MP3 / MP4。转换时弹一个小黑窗口看进度，结束后弹结果提示框。
**无后台服务、不常驻内存**，只在右键点击那一刻运行。

> **English TL;DR** — A lightweight Windows context-menu converter: right-click any file(s) →
> *转换文件格式* → pick a conversion (PDF↔Word, PDF→TXT, images↔png/jpg/webp, image→PDF,
> audio→mp3/wav, video→mp4/gif, merge PDFs/images, compress images…). Single-file Python source,
> no background service, output lands next to the source file as `name_转换后.ext`.
> Requires Python 3.9+ and ffmpeg (for audio/video). Build a single exe with `打包exe.bat`.

---

## 一、支持哪些转换


| 分类 | 菜单项 | 输入格式 | 输出格式 | 依赖 |
|---|---|---|---|---|
| 文档 | PDF 转 Word (.docx) | .pdf | .docx | pdf2docx + PyMuPDF |
| 文档 | Word 转 PDF | .docx | .pdf | 三级方案：① Word COM ② LibreOffice ③ Edge/Chrome 无头打印（都不装才失败） |
| 文档 | PDF 转 TXT | .pdf | .txt | PyMuPDF |
| 文档 | Word 转 TXT | .docx | .txt | python-docx |
| 文档 | PDF 逐页转 PNG | .pdf | 原名_转换后_1.png … | PyMuPDF（150 dpi） |
| 文档（额外） | 多 PDF 合并 → 一个 PDF | .pdf | 合并_时间戳.pdf | PyMuPDF |
| 图片 | 图片 → PNG | png/jpg/webp/bmp/tif | .png | Pillow |
| 图片 | 图片 → JPG | 同上 | .jpg | Pillow |
| 图片 | 图片 → WEBP | 同上 | .webp | Pillow |
| 图片 | 图片 → PDF | 同上 | .pdf | Pillow |
| 图片（额外） | 多图合并 → 一个 PDF | 同上 | 合并_时间戳.pdf | Pillow |
| 图片（额外） | 图片压缩（保原格式） | png/jpg/webp | 原名_压缩后.同格式 | Pillow（质量 80） |
| 音频 | 音频 → MP3 | wav/flac/m4a/ogg/aac/wma/opus/aiff | .mp3 | **ffmpeg** |
| 音频 | 音频 → WAV | 同上 | .wav | **ffmpeg** |
| 视频 | 视频提取音频 → MP3 | mov/mkv/avi/flv/wmv/m4v/webm… | .mp3 | **ffmpeg** |
| 视频 | 视频 → MP4 | 同上 | .mp4 | **ffmpeg**（H.264 + AAC） |
| 视频 | 视频 → GIF | 同上 | .gif | **ffmpeg**（12fps / 宽 480） |

菜单底部的额外项：

- **自定义输出文件夹…** —— 弹文件夹选择框，指定转换后文件统一存放的位置
- **恢复输出到原目录** —— 回到默认的"原文件同目录"
- **检查运行环境** —— 列出 ffmpeg / Pillow / PyMuPDF / pdf2docx / Word 是否可用
- **ffmpeg 下载指引** —— 没装 ffmpeg 时从这里下载
- **关于本工具**

---

## 二、目录结构

```
FileConverter/
├─ src/                    源码
│  ├─ converter.py         入口（CLI：run / util / install / uninstall / check）
│  └─ core/
│     ├─ config.py         配置读写（%APPDATA%\FileConverter\config.json）
│     ├─ winui.py          控制台 / 消息框 / 文件夹选择框（纯 ctypes + WinForms）
│     ├─ ffmpegtool.py     ffmpeg 定位、下载指引、带进度的执行
│     ├─ tasks.py          转换能力矩阵（动词 ↔ 输入格式 ↔ 目标格式）
│     ├─ collector.py      多选合并器（并发实例选举主进程）
│     └─ registry.py       右键菜单注册表读写（HKCU）
├─ tools/make_icon.py      生成 exe 图标
├─ samples/                自检用的样本文件（可删）
├─ app.ico                 程序图标
├─ build.spec              PyInstaller 打包配置
├─ requirements.txt        依赖清单
├─ install.bat             一键安装右键菜单
├─ uninstall.bat           一键卸载（无残留）
├─ 打包exe.bat             打包成单个 exe
└─ README.md               本文档
```

---

## 三、安装（三选一）

> **本机已经装好了**：程序在 `%LOCALAPPDATA%\Programs\FileConverter\FileConverter.exe`，
> 右键菜单已注册（当前用户，指向该路径）。要卸载就双击那个目录下的 `uninstall.bat`。

### 方式 A：用打包好的 exe（推荐）

1. 把 `dist\FileConverter.exe` 放到一个固定目录（例如 `D:\Tools\FileConverter\`），**路径里不能有中文之外的问题，但装好后不要随便挪位置**；
2. 双击 **`install.bat`**；
3. 弹窗提示"右键菜单已安装"即完成。**不需要管理员权限**，只写当前用户的注册表。

### 方式 B：用 Python 源码

```bat
pip install -r requirements.txt
install.bat
```

脚本会自动判断：有 exe 用 exe，没有就用 Python 源码模式注册。

### 方式 C：命令行

```bat
FileConverter.exe install          :: 安装
FileConverter.exe check            :: 查看是否已安装
FileConverter.exe uninstall        :: 卸载
FileConverter.exe uninstall --purge:: 连配置一起删
```

### 菜单长什么样

右键文件 → 菜单里出现 **`转换文件格式 ▶`**，鼠标移上去（或点开）展开 17 个转换项 ——
和 Bandizip / 7-Zip 那种级联菜单完全一样。支持多选，一次选 10 个文件点一下全转。

```
   5. Bandizip (B)      ▶
  10. 7-Zip             ▶
  12. 转换文件格式        ▶    ← 本工具
      ├─ PDF 转 Word (.docx)
      ├─ Word 转 PDF
      ├─ PDF 转 TXT
      └─ …… 共 17 项
```

### 实现方式：`IContextMenu` 外壳扩展

菜单由 `FileConvCtx.dll`（纯 C，约 60 KB）自己画：
`QueryContextMenu` 里 `CreatePopupMenu()` 填 17 项，再 `InsertMenu(MF_POPUP)` 挂到右键菜单上。
注册在 HKCU，**不需要管理员权限**：

```
Software\Classes\CLSID\{B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}\InprocServer32  → FileConvCtx.dll
Software\Classes\{*|Directory}\shellex\ContextMenuHandlers\FileConv           → 上面的 CLSID
```

**为什么不用纯注册表级联**：父键加 `SubCommands=""`、子项加 `MUIVerb` 这套"静态级联"
写法在 Win11 build 26200 上**渲染不出来**（菜单项要么不显示，要么点开是空的）。
所以只能走 shell 扩展自己 `InsertMenu(MF_POPUP)` 的路子 —— 这也是 7-Zip / WinRAR /
TortoiseGit 的标准做法。

### ⚠️ 关于「一级菜单」，微软已经定性

> 上下文菜单扩展必须使用 **IExplorerCommand** 接口来实现。实现 **IContextMenu** 的
> 上下文菜单扩展将显示在**旧的上下文菜单**中。
> —— MS Learn《Windows 应用开发最佳做法》

也就是说：Win11 那个紧凑菜单**只**承载 `IExplorerCommand` + MSIX 包身份；
`IContextMenu` 扩展只会出现在旧版菜单里。本项目实测也证伪了 MSIX 路线：

| 试过的方案 | 结果 |
|---|---|
| MSIX 稀疏包 + `com:InProcessServer` | 注册报 `0xC00CE014 元素为意外元素`（MSIX 只允许 SurrogateServer） |
| MSIX 稀疏包 + `com:SurrogateServer` | dllhost 挂死，Explorer 崩 `0xc0000005` |
| 注册表 `ExplorerCommandHandler` | 只出现在「显示更多选项」里，且曾导致右键直接黑屏 |

**结论**：想要「级联效果」+「右键直接可见」，唯一可靠的组合是
**`IContextMenu` 级联扩展 + 打开经典完整右键菜单**。所以 `install` 会：

1. 注册级联扩展（文件 `*` + 文件夹 `Directory`）
2. 同时打开「经典完整右键菜单」（`classic on`），让级联项直接可见，不用再点「显示更多选项」
3. 顺手清掉历史遗留的 MSIX 包 / `IExplorerCommand` 扩展 / 静态菜单项，避免多套菜单打架

代价是**所有软件**的右键菜单都会变成 Win10 风格。不想要的话 `classic off` 就能还原
（那样本工具的菜单就回到「显示更多选项」里了）。

```bat
FileConverter.exe install          :: 装级联菜单 + 切经典菜单
FileConverter.exe classic on|off   :: 手动切经典完整菜单 / 还原 Win11 默认
FileConverter.exe check            :: 看各项注册状态
```

**安装失败时会自动回退**成「单个菜单项 + 弹窗选单」模式（该模式下右键
【转换文件格式】会弹一个窗口让你挑转换方案），功能不丢，只是没有级联效果。

### 嫌右键菜单太乱？精简它

Windows 上随便一个文件右键，都能挤出二三十项：WPS 的总结全文/视频压缩/提取音频、
夸克网盘上传、QQ 发送、网易邮箱发送、Clipchamp…… 挤得真正要用的东西都看不见了。

```bat
python tools\menu_cleaner.py scan              :: 先看看能禁哪些（只读，不改）
python tools\menu_cleaner.py apply             :: 精简
python tools\menu_cleaner.py restore           :: 一键还原
python tools\menu_cleaner.py msix-scan         :: 列出装了菜单扩展的 MSIX 包
python tools\menu_cleaner.py msix-uninstall    :: 卸载 WPS/QQ 的右键扩展包
```

**三条安全保证**：

1. **全部只写 HKCU**（用户级覆盖系统级），不动 HKLM、不卸载软件、不删文件
2. **每条改动都写进 `menu_backup.json`**，`restore` 原样还原
3. **策略是「白名单优先 + 只禁黑名单」** —— 没命中的一律不动。
   宁可漏禁也不能误伤（漏了下次加一条关键字就行，误伤会影响日常）

保留名单：`7-Zip`、`Bandizip`、Windows Defender 扫描、本工具，以及全部系统常规项。

**两类注册来源要分开处理，这是踩过坑的**：

| 来源 | 长什么样 | 怎么禁 |
|---|---|---|
| COM 外壳扩展 | 注册在 `\shellex\ContextMenuHandlers` 下 | 在**挂载点**加 `LegacyDisable` |
| MSIX 包扩展 | 包 manifest 里 `fileExplorerContextMenus` | **注册表无效**，只能卸载包 |

> ⛔ **切勿在 `HKCU\Software\Classes\CLSID\{...}` 下建「只有 `LegacyDisable`、
> 没有 `InprocServer32`」的键。** HKCU 下这个键只要存在就会**完全顶掉** HKLM 的同名键，
> COM 加载时找不到服务程序 → 整条菜单构建中断。本项目实测就是这么把**本工具自己的
> 菜单项**也一起搞没的。正确做法是在挂载点上标记，完全不碰 CLSID。

MSIX 包（`wpsappext1/2/3`、`QQExtension`）的 COM 类**根本不在注册表里**
（HKCU/HKLM 的 `ActivatableClasses\Package` 和 `CLSID` 下都查不到），
由包系统内部数据库管理，摘注册表无效。但它们本身是**纯右键扩展包**，
卸载掉**不影响 WPS / QQ 主程序**，所以 `msix-uninstall` 直接卸包。
（`Clipchamp` 是应用本体，默认不动，要卸得显式加 `--with-optional`。）

### ffmpeg（音视频转换必需）

程序启动时按顺序找 ffmpeg：

1. `PATH`
2. `%LOCALAPPDATA%\Programs\ffmpeg\bin`
3. `C:\Program Files\ffmpeg\bin` / `C:\ffmpeg\bin`
4. **本程序目录 `\ffmpeg\ffmpeg.exe`**（绿色便携，推荐）

找不到时，右键点音视频转换会弹出下载指引（或直接点菜单里的【ffmpeg 下载指引】）：
下载 https://www.gyan.dev/ffmpeg/builds/ 的 `ffmpeg-release-essentials.zip`，
解压出 `ffmpeg.exe`（可连 `ffprobe.exe` 一起）丢进程序目录的 `ffmpeg\` 子文件夹即可，**不用重启**。
也可以用 `winget install Gyan.FFmpeg`。

---

## 四、使用说明

1. 在资源管理器里选中一个或多个文件（多选：Ctrl / Shift 点选，或框选）；
2. 右键 → 【转换文件格式】→ 悬停展开子菜单 → 点需要的转换方案；
3. 弹出小黑窗口，显示当前文件、进度条（ffmpeg 转换显示百分比 / 速度）、成功或失败原因；
4. 全部结束后弹提示框：成功显示输出位置，失败列出前 6 条失败原因。

**输出规则**

- 默认输出到**原文件所在目录**；
- 命名：`原文件名_转换后.新后缀`，例如 `报告.pdf → 报告_转换后.docx`；
- 同名文件已存在时自动追加序号（`报告_转换后_2.docx`），**不会覆盖原文件**；
- 选了【自定义输出文件夹】后统一存到该目录；该目录被删掉时会自动退回原目录并提示；
- 多图合并是例外：输出为 `合并_年月日_时分秒.pdf` 单个文件。

**批量是怎么做到的**

Windows 的静态右键动词对选中的每个文件各启动一个进程，每个进程只能拿到自己那一个文件。
本工具的做法：

1. 每个进程把拿到的文件写进 `%TEMP%\FileConv\<会话>\<token>.rec`；
2. 等待窗口以"会话里第一条记录的时间"为准（默认 1.5 秒，期间有新记录就顺延）；
3. 到点后**原子抢占** `state` 文件（`O_CREAT|O_EXCL`），抢到的当主进程，收走全部文件一次性转换；
4. 其余进程不弹窗、不干活，主进程每转完一个文件就删掉对应记录，跟随者随即退出；
5. 主进程收尾时补扫一次"迟到"的文件，再删掉会话目录。

主进程每 5 秒刷新一次心跳，它挂了的话跟随者会自动接管，**不会丢文件、也不会重复转**。
整个过程没有常驻服务，全部跑完进程就退出。

副作用：多选后大约有 1.5~2 秒的"收集窗口"，然后才弹黑窗口开始转换——这是正常现象。
嫌慢就把 `%APPDATA%\FileConverter\config.json` 里的 `collect_ms` 调小（比如 800）。

---

## 五、卸载

双击 **`uninstall.bat`**，或者 `FileConverter.exe uninstall`。

会删除：

- `HKCU\Software\Classes\CLSID\{B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}`（级联扩展注册）
- `HKCU\Software\Classes\{*|Directory}\shellex\ContextMenuHandlers\FileConv`（挂载点）
- 历史遗留的 MSIX 包 / `IExplorerCommand` 扩展 / 静态菜单项
- `%TEMP%\FileConv\`（多选合并产生的临时文件）
- 顺带把菜单样式还原成 Windows 11 默认

保留 `%APPDATA%\FileConverter\config.json`（自定义输出目录等设置）。
想连配置一起删：`uninstall.bat /purge`。

程序本身是**单文件 exe**，没有开机自启、没有计划任务、没有服务，删掉 exe 即彻底消失。

### 菜单不显示？按这个顺序查

**第 1 步：看注册状态**

```bat
FileConverter.exe check
```

会打印级联扩展是否注册、是否挂到了 `*` / `Directory` 上、DLL 能不能加载、
经典菜单开没开。哪一项是「未注册」「✘」就说明卡在哪一步。

**第 2 步：隔离验证 DLL 本身**（不写注册表、不碰 Explorer，最安全）

```bat
python tools\test_ctx.py
```

在自己的进程里把 Explorer 会做的事跑一遍：实例化 COM 对象 → 建菜单 → 数 17 个子项
→ 校验文字 → `GetCommandString` 的 A/W 两版 → `InvokeCommand` 两种 ID 解释。
全绿才说明 DLL 没问题。

**第 3 步：真实右键看渲染**

```bat
python tools\test_menu_live.py
```

真的弹出一个资源管理器窗口并右键，然后从 `#32768` 菜单窗口里把菜单项全读出来，
确认 `转换文件格式 ▶` 是带箭头的级联、展开后 17 项文字全对。

> ⚠️ **别用 `FolderItem.Verbs()` 验证级联菜单** —— 它只枚举带命令 ID 的菜单项，
> `MF_POPUP` 级联项没有命令 ID，**必然被跳过**，会给出"菜单里没有"的假阴性。
> 这个坑我踩过，白白排查了半天。
>
> 另外：改完注册表或换 DLL 后，必须**重启资源管理器**才生效：
> ```powershell
> Stop-Process -Name explorer -Force     # 会自动重启，不用担心
> ```

---

## 六、自己打包成 exe

```bat
py -m pip install -r requirements.txt
打包exe.bat
```

等价于：

```bat
python tools\make_icon.py
python -m PyInstaller --noconfirm --clean build.spec
```

> ⚠️ **打包环境必须装齐 `python-docx` 和 `pdf2docx`**，否则会打出一个**只有 51 MB 的
> 残废 exe**（缺了 docx，一碰 Word 转换就崩）。正确的成品约 **158 MB**。
> **exe 体积就是依赖完整性的信号：≈158 MB 正常，≈51 MB 就是缺依赖。**
>
> 打包前确认一下：
> ```bat
> python -c "import docx, pdf2docx, PIL, pymupdf, PyInstaller; print('依赖齐全')"
> ```
> 另外 `FileConvCtx.dll` 要和 exe **放在同一个目录**（扩展靠 `GetModuleFileName`
> 定位同级 exe），`打包exe.bat` 已经处理好了。

级联扩展 DLL 需要重新编译时（MinGW gcc）：

```bat
python native\gen_verbs.py            :: 先从 SPECS 重新生成 native\verbs_gen.h
gcc -shared -O2 -o native\FileConvCtx.dll native\FileConvCtx.c ^
    -lole32 -lshell32 -lshlwapi -luuid
```

> MinGW 的 `ld` 不吃中文路径，源码要拷到纯 ASCII 目录（如 `C:\mgw\work`），
> 并把 `TMP` / `TEMP` 也指到 ASCII 路径再编译。

产物：`dist\FileConverter.exe`（单文件，本机实测 **150 MB**，其中 PyMuPDF 的 mupdf 引擎占大头）。

单文件版每次启动要把 ~150 MB 解到临时目录，本机实测**从点击到开始转换约 2 秒**
（其中 1.5 秒是收集多选用）。如果你经常批量转换，建议改成文件夹版
（把 `build.spec` 末尾注释里的 onedir 写法打开），启动能快一个数量级。

打包参数是** windows 子系统**（`console=False`），所以转换前不会闪黑窗口；
真正开始转换时由代码调用 `AllocConsole()` 弹出那一个黑窗口。
如果你想让每个进程一启动就有黑窗口（调试时方便），把 `build.spec` 里的 `console=False` 改成 `True` 重新打包。

---

## 七、自检

```bat
python src\selftest.py
```

会自动生成样本文件（docx / pdf / png / jpg / webp / wav / flac / m4a / ogg / mov / mkv / avi / flv），
逐条跑完所有转换、验证批量多选合并、验证自定义输出目录、验证注册表安装与卸载无残留，
最后打印 `通过 X 失败 Y`。想直接测打包好的 exe：

```bat
set FC_EXE=dist\FileConverter.exe
python src\selftest.py
```

**本机实测结果**（Windows 11 build 26200 + ffmpeg 9.0.2）：对部署好的 exe 跑 **41/41 通过**，
含"菜单真的出现在右键菜单里（Explorer 动词枚举）""多选合并""runm 直传"等回归用例。
安装 → 注册表写入 → 卸载 → 无残留，全部验证过。

---

## 八、依赖清单

**Python 包**（`requirements.txt`）

| 包 | 用途 |
|---|---|
| Pillow | 图片互转、图片转 PDF |
| pdf2docx | PDF → Word |
| PyMuPDF | PDF → TXT、页数识别 |
| python-docx | Word 文档读写 |
| PyInstaller | 仅打包时需要 |

**外部程序**

- **ffmpeg / ffprobe**：音频转 MP3、视频转 MP4（必需）
- **Word 转 PDF** 会自动按序尝试：
  1. Microsoft Word（COM，排版最准）
  2. LibreOffice `soffice --convert-to pdf`（没装 Word 时的首选替代）
  3. Edge / Chrome 无头打印：docx → HTML → PDF（只用 python-docx 解析正文、标题、表格、加粗斜体，
     **不装任何 Office 也能用**，排版是"网页打印级"，不是 Word 原样）
  三者都不可用时才报错，并逐条列出原因。

---

## 九、已知限制

- **Word 转 PDF**：有 Word / LibreOffice 时排版最准；两者都没有时走 Edge/Chrome 打印，
  能保留正文、标题层级、表格、加粗斜体，但**页眉页脚、复杂分栏、艺术字、图片环绕**这类会丢失。
  想要 100% 还原请装 Word 或 LibreOffice。
- **扫描件 PDF**（全是图片没有文字层）转 Word / TXT 会得到空文档，需要先 OCR。
- **PDF → Word** 是"重排版"式转换，复杂表格/公式可能有偏差。
- **Windows 11** 需要在"显示更多选项"里找菜单（系统限制）。
- 注册表写在 HKCU，**只对当前 Windows 用户生效**；换账号需要再跑一次 install。
- 一次批量建议不超过几十个文件（每个文件都要启一个短命进程做登记，单文件 exe 尤其明显）。
- Word 转 PDF 走浏览器打印时，会在 `%TEMP%\FileConvPrint\` 留一个 Edge 用户配置目录（几 MB，可删）。
- 高清视频转 MP4 用的是 `libx264 veryfast crf23` 重编码；想更快可以改 `config.json` 的 `mp4_crf`。
