# 给 AI 的接入指南（AI_ONBOARDING.md）

> 这份文档是写给**将要接手本项目的 AI 助手**的。
> 目标是让你在 10 分钟内跑通「克隆 → 构建 → 测试 → 改代码」，
> 并且**跳过前人踩过的所有坑**。请先读完第 2 节再动手。

---

## 1. 项目是什么

Windows 资源管理器**右键菜单扩展**：在文件/文件夹右键菜单里加一个
`转换文件格式 ▶` 级联子菜单，支持 PDF/Word/图片/音频/视频共 17 种转换，可多选批量。

- 仓库：https://github.com/CNzxdehh/FileConverter （公开）
- 默认分支：`main`
- 技术栈：**Python 3.13**（主程序，PyInstaller 打包）+ **纯 C**（外壳扩展 DLL，MinGW 编译）
- 目标系统：Windows 11 build 26200

### 核心文件

| 路径 | 作用 |
|---|---|
| `native/FileConvCtx.c` | **右键级联菜单的外壳扩展**（IContextMenu + IContextMenu2/3 + IShellExtInit） |
| `native/FileConvCtx.dll` | 上面那个编译产物（约 63 KB，跟着 exe 一起分发） |
| `native/verbs_gen.h` | 17 个转换方案的 id + 菜单文字，由 `native/gen_verbs.py` 生成 |
| `src/converter.py` | 主程序入口（install / uninstall / check / runm / selftest 等子命令） |
| `src/core/registry.py` | 注册表读写（CLSID 注册、挂载、经典菜单开关） |
| `src/core/tasks.py` | 各转换动作的实现 |
| `src/selftest.py` | 完整自检（45 项，见第 6 节） |
| `tools/menu_cleaner.py` | 右键菜单精简器（禁第三方菜单项） |
| `打包exe.bat` | 一键打包成单文件 exe |

---

## 2. ⛔ 先读这一节：本机环境的坑（不读必踩）

### 2.1 git 连不上 GitHub（SSL 证书链错误）

**症状**（按出现顺序）：

```
curl  → HTTP=000, exit 35（SSL connect error）
git   → schannel: next InitializeSecurityContext failed: CRYPT_E_NO_REVOCATION_CHECK (0x80092012)
git   → SSL certificate OpenSSL verify result: unable to get local issuer certificate (20)
```

**根因**：机器上装了代理/加速器，对 TLS 做**中间人拦截**，git 看不到它的 CA。

**解法**（一次性配置，已写进仓库 `.git/config`，但换机器要重做）：

```bash
# 1. 把 Windows 证书库里的根证书导成 PEM（152 张 / 307 KB）
#    PowerShell：
Get-ChildItem Cert:\LocalMachine\Root, Cert:\CurrentUser\Root,
              Cert:\LocalMachine\CA,  Cert:\CurrentUser\CA | ForEach-Object {
  "-----BEGIN CERTIFICATE-----"
  [Convert]::ToBase64String($_.RawData)
  "-----END CERTIFICATE-----"
}
#    再用 [System.IO.File]::WriteAllLines("C:\mgtmp\roots.pem", $out) 落盘
#    （别用 Out-File，它会加 BOM）

# 2. 让 git 用这份证书
git config --local http.sslBackend openssl
git config --local http.sslCAInfo "C:/mgtmp/roots.pem"
```

> 💡 **Python 的 `urllib` 走系统证书库，直接就能连 GitHub**（申请 device code 就是它通的）。
> 所以 `curl` 不通时改用 Python 发 API 请求，别死磕 curl。
> 但 **`winreg.HKEY_CLASSES_ROOT` 在 Python 里给出的结果不可信**，
> 查注册表一律用 PowerShell `Registry::HKEY_CLASSES_ROOT` 交叉验证。

### 2.2 PowerShell 里 `*` 是通配符

```powershell
Test-Path "HKCU:\Software\Classes\*\shellex\..."   # ❌ 会去扫整棵注册表，命令卡住不动
Test-Path -LiteralPath "HKCU:\Software\Classes\*\shellex\..."   # ✅ 必须加 -LiteralPath
```

> 本机 Python 环境在 `C:\Users\徐颢朗\.workbuddy\binaries\python\envs\default`，
> 已装齐 pyinstaller / Pillow / pdf2docx / PyMuPDF / python-docx / pywin32。
> **别用系统 Python**（`Desktop\VS code\python`，缺 python-docx 和 pdf2docx，
> 打出来的 exe 只有 51 MB，一碰 Word 转换就崩）。

### 2.3 MinGW 不吃中文路径

编译 `FileConvCtx.dll` 前，必须把源码拷到纯 ASCII 目录，且 `TMP`/`TEMP` 也指到 ASCII 路径：

```bash
cp native/FileConvCtx.c /c/mgw/work/          # 中文路径会让 ld 直接报错
cd /c/mgw/work
export TMP=C:/mgtmp TEMP=C:/mgtmp
/c/mgw/bin/gcc.exe -shared -O2 -Wall -o FileConvCtx.dll FileConvCtx.c \
    -lole32 -lshell32 -lshlwapi -luuid
```

编译完要同步到**三个位置**（漏一个就会出现"源码跑、dist 跑、安装版跑的是三个不同东西"）：

```
native/FileConvCtx.dll
dist/FileConvCtx.dll
%LOCALAPPDATA%\Programs\FileConverter\FileConvCtx.dll
```

### 2.4 exe 体积是依赖完整性的信号

| 体积 | 含义 |
|---|---|
| **≈158 MB** | ✅ 正常 |
| **≈51 MB** | ❌ 缺 `python-docx` / `pdf2docx`，Word 转换会崩 |

### 2.5 换 DLL 必须先停 Explorer

`FileConvCtx.dll` 被 Explorer 加载时，`cp` 会报 `Device or resource busy`。
先 `Stop-Process -Name explorer -Force`，拷完再启动。

---

## 3. 克隆与配置

```bash
git clone https://github.com/CNzxdehh/FileConverter.git
cd FileConverter

# 如果在本机（有代理）且遇到 SSL 错，按 2.1 配置
git config --local http.sslBackend openssl
git config --local http.sslCAInfo "C:/mgtmp/roots.pem"

# 持久化凭证（可选，免得每次推送都输 token）
git config --global credential.helper manager
```

> **推送用 token**：GitHub 网页已登录 ≠ 命令行有凭证，两者不互通。
> 生成：https://github.com/settings/tokens/new?scopes=repo,workflow
> （选 **classic**，不要 fine-grained；Expiration 建议 **No expiration**）
> 一次性推送：`GIT_TERMINAL_PROMPT=0 git push https://<token>@github.com/u/r.git main`
>
> ⚠️ `GIT_TERMINAL_PROMPT=0` 必须加，否则 credential helper 弹窗会卡住几分钟。
> 推完记得 `git remote set-url origin https://github.com/u/r.git` 把 token 从 `.git/config` 清掉。

---

## 4. 构建

```bat
py -m pip install -r requirements.txt
打包exe.bat
```

产物：`dist\FileConverter.exe`（单文件，约 158 MB）。

> `build/` 和 `dist/` 已在 `.gitignore` 里（GitHub 单文件超 100 MB 会被拒），
> **不进仓库**。仓库里只进源码 + `native/*.dll`（都 < 100 KB）。

安装：

```bat
dist\FileConverter.exe install
```

会做四件事：注册级联扩展 CLSID → 挂到 `*` 和 `Directory` → 打开「经典完整右键菜单」 →
清掉历史遗留的 MSIX 包 / IExplorerCommand 扩展 / 静态菜单项。

卸载：`dist\FileConverter.exe uninstall`（或双击 `uninstall.bat`）

---

## 5. 运行机制（改代码前必须理解）

### 5.1 菜单是怎么来的

```
右键文件
  → Explorer 实例化 CLSID {B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}
  → IShellExtInit::Initialize  ← 从 IDataObject 拿 CF_HDROP，收集所有选中文件路径
  → IContextMenu::QueryContextMenu
        ├─ 按扩展名判断文件类型（CatOf）
        ├─ 算出该显示的动词集合（智能筛选）
        ├─ CreatePopupMenu + AppendMenuW（ID 从 idCmdFirst 连续编号！）
        └─ InsertMenuW(hmenu, index, MF_POPUP|MF_STRING, sub, L"转换视频")
  → 【Explorer QueryInterface 拿 IContextMenu2/3】  ← 见 5.3，极易漏
  → 用户点击子项
  → IContextMenu::InvokeCommand  ← lpVerb 低 16 位，绝对 ID 或相对偏移都可能
  → Launch() → GetModuleFileName 定位同级 exe → runm <动词> "文件1" "文件2"...
```

### 5.2 智能筛选（`CatKind`）

| 扩展名 | 菜单标题 | 显示的转换 |
|---|---|---|
| `.pdf` | 转换 PDF | PDF→Word / PDF→TXT / PDF逐页转PNG / 多PDF合并 |
| `.docx` `.doc` | 转换 Word | Word→PDF / Word→TXT |
| 图片 | 转换图片 | →PNG/JPG/WEBP/PDF、多图合并、压缩 |
| 音频 | 转换音频 | →MP3 / →WAV |
| 视频 | 转换视频 | 提取音频 / →MP4 / →GIF |
| **未知类型** | 转换文件格式 | **全部 17 项**（刻意兜底，别让菜单变空） |
| 混合多选 | 按第一个文件命名 | 各类**并集** |

### 5.3 ⛔ 三个"静默失效"的坑（都表现为「右键有菜单但点了没反应」）

| # | 坑 | 现象 | 正确做法 |
|---|---|---|---|
| 1 | 漏实现 `IContextMenu2` / `IContextMenu3` | `HandleMenuMsg` 永不被调用 | vtable 用 `IContextMenu3Vtbl`，QI 放行这两个 IID |
| 2 | 菜单项 ID 用了 `idCmdFirst + 原索引` | `InvokeCommand` 永不被调用 | **必须从 idCmdFirst 连续编号**，原索引另存 `o->show[]`，`MapId()` 换算 |
| 3 | `InvokeCommand` 只认一种 ID 语义 | 某些宿主下点了没反应 | 绝对 ID 和相对偏移**两种都接受** |

> **为什么自检 45 项全绿也发现不了**：隔离测试是「自己造 IDataObject → 直接调 vtable」，
> **完全绕过了 Explorer 的真实消息路径**（QI 协商 + 连续 ID 契约）。
> 所以 `tools/test_ids.py`（连续 ID + 绝对/相对 + 越界）和 `tools/test_qi.py`（QI + HandleMenuMsg）
> **一个都不能少**。

### 5.4 在 `HKCU\...\CLSID\{X}` 下建键的禁忌

⛔ **绝不要建「只有 `LegacyDisable`、没有 `InprocServer32`」的半截键。**
HKCU 下这个键只要存在就**完全顶掉** HKLM 的同名键，COM 加载时找不到服务程序
→ 整条菜单构建中断（本工具自己的菜单项也会被连带搞没）。

✅ 要禁第三方外壳扩展：**先把整个 CLSID 完整克隆到 HKCU，再加 `LegacyDisable`**
（见 `tools/menu_cleaner.py` 的 `clone_and_disable()`）。

---

## 6. 测试

```bash
PY="C:/Users/徐颢朗/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

# 完整自检（45 项：21 种转换 + 批量合并 + 注册表 + 安装/卸载）
FC_EXE="dist\\FileConverter.exe" $PY src/selftest.py

# 级联扩展隔离验证（建菜单/17 项文字/GetCommandString A+W/InvokeCommand）
$PY tools/test_ctx.py

# 智能判断：逐类型验证标题和子项、未知类型全列、混合取并集
$PY tools/test_smart.py

# IContextMenu2/3 能否 QI 到、HandleMenuMsg 能否调
$PY tools/test_qi.py

# ⭐ 连续 ID 映射（唯一能抓住坑 #2 的测试）
$PY tools/test_ids.py

# 安装版 exe 真实转换 + 菜单精简状态 + 保留项未被误伤
$PY tools/test_final.py
```

> ⚠️ **跑完 `selftest.py` 必须用安装版 exe 再 `install` 一次** ——
> selftest 收尾会用 `dist\FileConverter.exe` 重装，把 `InprocServer32` 指向
> **开发目录**的 DLL。用户一旦挪掉项目目录菜单就废了。
> `tools/test_final.py` 有断言专门盯这项。

> ⚠️ 自动化测试设 `FILECONV_SILENT=1` 和 `FILECONV_NO_CONSOLE=1`，
> 否则 MessageBox 会卡死。

### 6.1 真实右键菜单的验证（可选，本机当前不可用）

`tools/test_menu_live.py` 会真的弹出资源管理器窗口并右键，然后从 `#32768`
菜单窗口把菜单项全读出来。**本机目前跑不通**（反复重启 Explorer 后，
测试进程的输入注入被系统限制），但它在 2026-10-21 成功过一次，
当时确认了 `转换文件格式 ▶` 在第 12 项、紧邻 Bandizip 和 7-Zip、子项 17/17 全对。

调试日志：`C:\mgtmp\fileconv_ctx.log`（由 DLL 里的 `FCCTX_DEBUG` 控制，默认开）。
**这个日志是区分"菜单没显示"和"点击没触发"的唯一手段** ——
前者只有 `QueryContextMenu` 记录，后者两者都有/都没有。

---

## 7. 已知限制

1. **Win11 紧凑菜单里看不到本工具**。微软已定性：
   > 上下文菜单扩展必须使用 IExplorerCommand 来实现。实现 IContextMenu 的扩展
   > 将显示在旧的上下文菜单中。（MS Learn《Windows 应用开发最佳做法》）

   所以 `install` 会同时打开「经典完整右键菜单」。代价是**所有软件**的右键菜单
   都变回 Win10 风格。`FileConverter.exe classic off` 可还原。

2. **MSIX 路线已证伪**（别重试）：
   - `com:InProcessServer` → 注册报 `0xC00CE014 元素为意外元素`
   - `com:SurrogateServer` → dllhost 挂死 + Explorer 崩 `0xc0000005`

3. **`FolderItem.Verbs()` 不能用来验证级联菜单** —— 它只枚举带命令 ID 的菜单项，
   `MF_POPUP` 级联项没有命令 ID，**必然被跳过**（假阴性）。

4. **ffmpeg 必须单独装**（音视频转换靠它），按顺序找：`PATH` →
   `%LOCALAPPDATA%\Programs\ffmpeg\bin` → `C:\Program Files\ffmpeg\bin` →
   程序目录 `\ffmpeg\ffmpeg.exe`。推荐最后一种（绿色便携）。
   本机已有：`C:\Users\徐颢朗\AppData\Local\Microsoft\WinGet\Links\ffmpeg`（在 PATH 里）。

---

## 8. 常用命令速查

```bat
FileConverter.exe install              :: 装级联菜单 + 切经典菜单
FileConverter.exe uninstall            :: 卸载（保留配置）
FileConverter.exe uninstall --purge    :: 连配置一起删
FileConverter.exe classic on|off       :: 切经典完整菜单 / 还原 Win11 默认
FileConverter.exe check                :: 看各项注册状态
FileConverter.exe runm <动词> <文件...>  :: 直接触发一次转换（调试用）

python tools\menu_cleaner.py scan              :: 看能禁哪些第三方菜单项（只读）
python tools\menu_cleaner.py apply             :: 精简（写 HKCU，可还原）
python tools\menu_cleaner.py restore           :: 一键还原
python tools\menu_cleaner.py msix-scan         :: 列出装了菜单扩展的 MSIX 包
python tools\menu_cleaner.py msix-uninstall    :: 卸 WPS/QQ 的右键扩展包
```

---

## 9. 联系与约定

- 提交信息用中文，写清「改了什么 + 为什么 + 踩了什么坑」
- 新增外壳扩展功能时，**必须同时补 `test_ids.py` / `test_qi.py` 这类
  「走真实契约路径」的测试**，不能只加隔离测试
- 改动 `native/FileConvCtx.c` 后，记得三处同步 DLL（见 2.3）
- 不要把 `dist/FileConverter.exe`（158 MB）提交进仓库
