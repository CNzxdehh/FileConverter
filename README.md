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

> **Windows 11 注意**：系统默认把第三方右键项收进"显示更多选项"（经典菜单）里。
> 在文件上右键 → 点最下面的**显示更多选项** → 就能看到【转换文件格式】。
> 这是 Windows 11 对静态菜单项的限制，只有 COM 外壳扩展才能进一级菜单。

### 一级菜单（Windows 11 现代右键菜单）

结论先说：**Windows 11 的现代紧凑菜单，只接受 MSIX 包里声明的菜单扩展**，
纯注册表（包括 `ExplorerCommandHandler`）只会出现在「显示更多选项」的旧菜单里。
QQ、WPS、Bandizip 在现代菜单里的项，全部来自 MSIX 稀疏包（sparse package）。

本工具的做法（三层，逐级回退）：

| 层级 | 方式 | 效果 |
|---|---|---|
| 1 | **MSIX 稀疏包** + `windows.fileExplorerContextMenus` + COM 扩展 | 文件/文件夹右键**一级菜单**直接可见，Win11 默认样式不变 |
| 2 | COM 扩展（`ExplorerCommandHandler`）+ 经典完整菜单 | 一级可见，但菜单样式会变成 Windows 10 风格 |
| 3 | 纯注册表级联菜单 | 只出现在「显示更多选项」里 |

`install` 会自动选能用的最高层级，并做自检；失败自动往下降。

- 第 1 层需要系统开启**开发者模式**（免签名注册稀疏包）：`Add-AppxPackage -Register`.
  检查：`设置 → 系统 → 开发者选项`。
- 组件：`FileConvMenu.dll`（57 KB，纯 C 写的 IExplorerCommand）+ `AppxManifest.xml` + `Assets\`。
- 卸载会同时移除 MSIX 包、注销 COM、删除注册表项，并还原 Win11 默认菜单样式。

```bat
FileConverter.exe install              :: 装（自动选最佳方案）
FileConverter.exe install --cascade    :: 强制用经典级联菜单
FileConverter.exe classic on|off       :: 手动切经典完整菜单 / 还原
python tools\test_com.py               :: 验证 COM 对象（标题/图标/17 个子项）
```

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

- `HKCU\Software\Classes\*\shell\FileConv`（父菜单，含兼容写法子项）
- `HKCU\Software\...\Explorer\CommandStore\shell\FileConv.*`（全部子菜单项）
- `%TEMP%\FileConv\`（多选合并产生的临时文件）

保留 `%APPDATA%\FileConverter\config.json`（自定义输出目录等设置）。
想连配置一起删：`uninstall.bat /purge`。

程序本身是**单文件 exe**，没有开机自启、没有计划任务、没有服务，删掉 exe 即彻底消失。

### 菜单不显示？先用这个查

注册表写对了 ≠ 菜单会出现。Windows 对级联菜单的写法挑得很，用这个脚本按 Explorer 的视角枚举：

```bat
pip install pywin32
python tools\check_menu.py            :: 输出里能看到【转换文件格式】才算真的生效
python tools\check_menu.py D:\a\b.png :: 也可以指定文件
```

> **踩过的坑（重要）**：父键上**绝对不能写 `SubCommands`**。
> - 写成 `SubCommands="A;B;C"`：Explorer 会去 **HKLM** 的 `CommandStore` 找这几个名字，
>   HKCU 下写的找不到 → **整个菜单项直接消失**（这就是第一版"右键没反应"的原因）；
> - 写成 `SubCommands=""`（空串）：官方文档里的"静态级联"写法，但在 Win11 build 26200 上**同样不显示**；
> - 正确做法：父键只写 `MUIVerb` + `Icon`，子项挂在 `shell\<动词>\command` 下，Explorer 自动渲染成级联。
>
> 这三种写法我在本机逐一实验过（`ZZAEmptySub` / `ZZBNoSub` / `ZZCSemicolon` 对照），
> 只有第三种能出现在右键菜单里。`src/selftest.py` 现在也带了这个回归用例。

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
