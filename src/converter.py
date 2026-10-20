# -*- coding: utf-8 -*-
"""
文件格式转换 —— Windows 右键菜单扩展（无后台常驻，只在右键点击时运行）

用法：
    converter.py run   <动词> <文件> [更多文件...]   # 具体转换
    converter.py util  <名称> [文件]                 # 菜单里的辅助项
    converter.py install   [--lean]                  # 写入右键菜单
    converter.py uninstall [--purge]                 # 删除右键菜单
    converter.py selftest                            # 自检（批量转换 samples）
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

VERSION = "1.0.0"

sys.path.insert(0, str(Path(__file__).resolve().parent))  # 打包/脚本两种运行方式都能 import core

from core import collector, ffmpegtool, registry, winui  # noqa: E402
from core.config import Config, config_path, log_dir, out_root, unique_path  # noqa: E402
from core.tasks import SPECS, UTILS, VERB_ORDER, images_to_pdf, out_name  # noqa: E402
from core.winui import print_safe  # noqa: E402


# -------------------------------------------------------------------------- #
def log(msg: str) -> None:
    try:
        with (log_dir() / "converter.log").open("a", encoding="utf-8") as fh:
            fh.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def _touch_console(title: str) -> None:
    winui.ensure_console(title)


def _banner(kind: str = "转换") -> None:
    print_safe("=" * 74)
    print_safe(f" 文件格式转换工具 v{VERSION}  ——  {kind}")
    print_safe("=" * 74)


# -------------------------------------------------------------------------- #
def do_util(name: str, files: list[Path]) -> int:
    cfg = Config.load()
    init = files[0].parent if files else None

    if name == "setoutdir":
        initial = cfg.get("out_dir") or (str(init) if init else None)
        picked = winui.pick_folder("选择转换后的文件保存位置", initial)
        if picked:
            from core.config import set_out_dir

            set_out_dir(picked)
            winui.info_box(
                f"已设置自定义输出文件夹：\n\n{picked}\n\n"
                f"（配置文件：{config_path()}）\n\n"
                f"想恢复输出到原文件目录，请点右键菜单里的【恢复输出到原目录】。",
                "设置成功",
            )
        else:
            winui.info_box("已取消，输出位置保持原样。", "提示")
        return 0

    if name == "cleardir":
        from core.config import set_out_dir

        set_out_dir(None)
        winui.info_box("已恢复：转换后的文件仍保存在原文件所在目录。", "设置成功")
        return 0

    if name == "checkenv":
        _touch_console("运行环境检查")
        _banner("环境检查")
        ff = ffmpegtool.find_ffmpeg(cfg.get("ffmpeg_path"))
        if ff:
            ffprobe = ffmpegtool.find_ffprobe(ff)
            print_safe(f"[OK]   ffmpeg     : {ff}  ({ffmpegtool.version(ff)})")
            print_safe(f"[OK]   ffprobe    : {ffprobe or '未找到（不影响转换，只影响进度准确度）'}")
        else:
            print_safe("[缺失] ffmpeg     : 未找到 —— wav/flac/m4a/ogg→mp3、mov/mkv/avi/flv→mp4 需要它")
            print_safe("       搜索过的位置：PATH、%LOCALAPPDATA%\\Programs\\ffmpeg\\bin、")
            print_safe("                     C:\\Program Files\\ffmpeg\\bin、C:\\ffmpeg\\bin、")
            print_safe(f"                     {ffmpegtool.base_dir()}\\ffmpeg\\bin")

        for mod, label in (("PIL", "Pillow（图片转换）"),
                           ("fitz", "PyMuPDF（PDF 转 TXT）"),
                           ("pdf2docx", "pdf2docx（PDF 转 Word）"),
                           ("docx", "python-docx（生成 Word）")):
            try:
                __import__(mod)
                print_safe(f"[OK]   {label}")
            except Exception as e:
                print_safe(f"[缺失] {label} : {e}")

        from core.tasks import _find_browser, word_installed

        print_safe(f"[{'OK' if word_installed() else '缺失'}]   Microsoft Word（Word 转 PDF 方案一）")
        soffice = Path(r"C:\Program Files\LibreOffice\program\soffice.exe")
        print_safe(f"[{'OK' if soffice.is_file() else '缺失'}]   LibreOffice（Word 转 PDF 方案二）")
        browser = _find_browser()
        print_safe(f"[{'OK' if browser else '缺失'}]   {browser.name if browser else 'Edge/Chrome'}"
                   "（Word 转 PDF 方案三：docx→HTML→打印，不装 Office 也能用）")

        print_safe("")
        print_safe(f"配置文件         : {config_path()}")
        print_safe(f"当前输出位置     : {cfg.get('out_dir') or '原文件所在目录'}")
        print_safe(f"已装右键菜单     : {'是' if registry.is_installed() else '否'}")
        print_safe("")
        if not winui.silent():
            print_safe("按回车键关闭本窗口…")
            try:
                input()
            except Exception:
                time.sleep(5)
        return 0

    if name == "ffmpeghelp":
        from ctypes import windll

        text = (
            "ffmpeg 是处理音视频的开源工具，本工具用它做 mp3 / mp4 转换。\n\n"
            "推荐做法（免安装）：\n"
            "  1. 打开 https://www.gyan.dev/ffmpeg/builds/\n"
            "  2. 下载 ffmpeg-release-essentials.zip\n"
            "  3. 解压，把里面的 ffmpeg.exe（可选 ffprobe.exe）\n"
            f"     放到本程序所在目录的 ffmpeg\\ 子文件夹，即：\n"
            f"     {ffmpegtool.base_dir()}\\ffmpeg\\ffmpeg.exe\n"
            "  4. 或者： winget install Gyan.FFmpeg\n\n"
            "放好后重新右键即可生效。是否现在打开下载页面？"
        )
        ret = windll.user32.MessageBoxW(None, text, "ffmpeg 下载指引", 0x24 | 0x40000)
        if ret == 6:
            winui.open_url("https://www.gyan.dev/ffmpeg/builds/")
        return 0

    if name == "about":
        info = (
            f"文件格式转换工具 v{VERSION}\n\n"
            "右键任意文件 → 【转换文件格式】→ 选择转换方案。\n"
            "支持一次选中多个文件批量转换；默认输出到原文件同目录，\n"
            "文件名形如 原名_转换后.后缀。\n\n"
            f"配置信息：{config_path()}\n"
            "无后台进程，不常驻内存。"
        )
        winui.info_box(info, "关于")
        return 0

    winui.error_box(f"未知的菜单项：{name}", "错误")
    return 1


# -------------------------------------------------------------------------- #
def do_run(verb: str, raw_files: list[str], skip_collect: bool = False) -> int:
    cfg = Config.load()
    if verb not in SPECS:
        winui.error_box(f"未支持的转换方案：{verb}", "错误")
        return 2

    spec = SPECS[verb]
    files: list[Path] = []
    for f in raw_files:
        p = Path(f)
        if p.exists():
            files.append(p)

    # 右键文件夹：把它当成"这个文件夹里所有能转的文件"
    dirs = [p for p in files if p.is_dir()]
    dir_count = 0
    if dirs:
        expanded: list[Path] = [p for p in files if p.is_file()]
        for d in dirs:
            try:
                for c in sorted(d.iterdir()):
                    if c.is_file() and c.suffix.lower() in spec["accept"]:
                        expanded.append(c)
                        dir_count += 1
            except Exception:
                pass
        files = expanded

    if skip_collect:
        leader = True                     # 一次性拿到全部文件，不需要选举
    else:
        # 多选合并：非主进程直接静默退出
        files, leader = collector.collect(verb, files or [Path(raw_files[0])],
                                          int(cfg.get("collect_ms", 1500)))
        if not leader:
            return 0

    accepted = [p for p in files if p.suffix.lower() in spec["accept"]]
    skipped = [p for p in files if p not in accepted]

    _touch_console(f"正在转换 → {spec['label']}")
    _banner(spec["label"])
    print_safe("")

    if not accepted:
        if skipped:
            exts = " ".join(sorted(spec["accept"]))
            msg = (f"选中的 {len(skipped)} 个文件都不是该方案支持的格式。\n\n"
                   f"【{spec['label']}】支持：{exts}\n\n"
                   f"示例：{skipped[0].name}")
        elif dirs:
            exts = " ".join(sorted(spec["accept"]))
            msg = (f"这个文件夹里没有【{spec['label']}】能处理的文件。\n\n"
                   f"需要：{exts}\n\n提示：本工具只处理文件夹第一层的文件，不递归子文件夹。")
        else:
            msg = "没有取到文件路径。"
        print_safe(msg)
        winui.error_box(msg, "无法转换")
        return 1

    # 输出目录（自定义目录失效时自动回落到原目录）
    outdir_root = out_root(cfg, accepted[0])
    print_safe(f"输出位置 : {outdir_root}")
    print_safe(f"共 {len(accepted)} 个文件")
    if skipped:
        print_safe(f"跳过 {len(skipped)} 个不支持的文件："
                   + ", ".join(p.name for p in skipped[:5])
                   + ("…" if len(skipped) > 5 else ""))
    print_safe("")

    t0 = time.time()
    failures: list[tuple[str, str]] = []
    ok_files: list[Path] = []

    def process_one(src: Path, idx: int, total: int, ffmpeg=None) -> None:
        print_safe(f"({idx}/{total}) {src.name}")
        dst, err, outs = _convert_one(verb, src, cfg, ffmpeg)
        if err:
            failures.append((src.name, err))
            print_safe(f"       [失败] {err}")
        else:
            ok_files.append(src)
            if len(outs) > 1:
                total_kb = sum(p.stat().st_size for p in outs) / 1024
                print_safe(f"       [完成] {len(outs)} 个文件（{outs[0].name} … "
                           f"{outs[-1].name}，共 {total_kb:.0f} KB）")
            else:
                try:
                    size = dst.stat().st_size / 1024
                    print_safe(f"       [完成] {dst.name}  ({size:.0f} KB)")
                except Exception:
                    print_safe(f"       [完成] {dst.name}")
        collector.mark_done(src)
        collector.heartbeat()
        print_safe("")

    # ---- 特殊：整批合并成一个文件（多图→PDF / 多PDF→PDF） ----
    if spec.get("batch_handler"):
        # 先标记已收集的（顺带清掉它们的投递记录），否则补扫会把同一批再收一遍
        for p in accepted:
            collector.mark_done(p)
        late = [p for p in collector.more(settle=1.5) if p.suffix.lower() in spec["accept"]]
        if late:
            print_safe(f"→ 又收到 {len(late)} 个迟到文件，一起合并")
            accepted += late
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = unique_path(outdir_root / f"合并_{ts}{spec['out_ext']}")
        kind = spec.get("batch_kind", "个文件")
        print_safe(f"→ 合并 {len(accepted)} {kind}")
        try:
            spec["batch_handler"](accepted, dst, cfg, {})
            ok_files = list(accepted)
            print_safe(f"[完成] {dst.name}  ({dst.stat().st_size / 1024:.0f} KB)")
        except Exception as e:
            failures.append((dst.name, f"{type(e).__name__}: {e}"[:300]))
            print_safe(f"[失败] {dst.name} : {e}")
        for p in accepted:
            collector.mark_done(p)
    else:
        ffmpeg = None
        if spec.get("needs_ff"):
            try:
                ffmpeg = ffmpegtool.ensure_ffmpeg(cfg)
            except SystemExit:
                print_safe("缺少 ffmpeg，转换取消。")
                collector.finish()
                return 2
        for i, src in enumerate(accepted, 1):
            process_one(src, i, len(accepted), ffmpeg)

        # 补扫：启动比主进程晚、刚把文件投递进来的实例
        for _ in range(3):
            extra = [p for p in collector.more() if p.suffix.lower() in spec["accept"]]
            if not extra:
                break
            print_safe(f"→ 又收到 {len(extra)} 个迟到文件，接着转换")
            n = len(accepted) + len(extra)
            for j, src in enumerate(extra):
                process_one(src, len(accepted) + j + 1, n, ffmpeg)
            accepted += extra

    collector.finish()

    elapsed = time.time() - t0
    print_safe("=" * 74)
    print_safe(f"完成 {len(ok_files)} 个，失败 {len(failures)} 个，用时 {elapsed:.1f}s")
    print_safe("=" * 74)

    if failures:
        detail = "\n".join(f"· {n}\n    {m}" for n, m in failures[:6])
        more = f"\n… 其余 {len(failures) - 6} 个省略" if len(failures) > 6 else ""
        winui.error_box(
            f"转换结束，有 {len(failures)} 个失败：\n\n{detail}{more}\n\n"
            f"成功 {len(ok_files)} 个。",
            "部分失败" if ok_files else "全部失败",
        )
        return 1 if not ok_files else 0

    if len(ok_files) == 1:
        one = ok_files[0]
        dst = out_name(one, spec, cfg)
        winui.info_box(f"转换成功！\n\n输出文件：\n{dst}", "转换完成")
    else:
        winui.info_box(f"{len(ok_files)} 个文件全部转换成功！\n\n输出位置：{outdir_root}",
                       "转换完成")
    return 0


def _convert_one(verb: str, src: Path, cfg: Config, ffmpeg=None):
    from core.tasks import convert_file

    return convert_file(verb, src, cfg, ffmpeg)


# -------------------------------------------------------------------------- #
def do_classic(argv: list[str]) -> int:
    """classic on / classic off：切换「经典完整右键菜单」（一级菜单的关键）。"""
    arg = (argv[0].lower() if argv else "on")
    enable = arg not in ("off", "0", "false", "no")
    now = registry.set_classic_menu(enable)
    registry.notify_explorer()
    if now:
        text = ("已切到【经典完整右键菜单】。\n\n"
                "之后右键文件会直接看到【转换文件格式】+ 15 个子项，不用再点「显示更多选项」。\n"
                "注意：所有软件的经典菜单项都会回到一级菜单（体积会大一些）。\n\n"
                "要还原 Win11 默认菜单：classic off")
    else:
        text = ("已还原 Windows 11 默认的紧凑右键菜单。\n\n"
                "【转换文件格式】会回到「显示更多选项」里。")
    winui.info_box(text + "\n\n提示：需要重启资源管理器（或注销）才会生效。", "右键菜单样式")
    return 0


def do_install(argv: list[str]) -> int:
    """装菜单：现代菜单（MSIX 稀疏包）→ COM 注册 → 经典级联菜单，逐级回退。"""
    force_cascade = "--cascade" in argv

    com_ok, com_msg, msix_ok, msix_msg = False, "跳过", False, "跳过"
    if not force_cascade:
        info = registry.install_com()
        if info.get("ok"):
            com_ok, com_msg = registry.com_verify()
        else:
            com_msg = info.get("reason", "未知原因")
        if com_ok:
            msix = registry.install_msix()
            msix_ok = bool(msix.get("ok"))
            msix_msg = msix.get("pkg") or msix.get("reason", "")

    if msix_ok:
        registry.remove_cascade()
        registry.set_classic_menu(False)
        mode = "msix"
        body = ("安装方式：【MSIX 稀疏包 + COM 外壳扩展】\n"
                "→ 右键任意文件/文件夹，Windows 11 一级菜单里直接有【转换文件格式】。\n"
                f"包名：{msix_msg}\n"
                "Windows 11 默认菜单样式保持不变。")
    elif com_ok:
        registry.remove_cascade()
        registry.set_classic_menu(True)
        mode = "com+classic"
        body = ("COM 扩展已就绪，但现代菜单包注册失败：\n"
                f"  {msix_msg}\n\n"
                "已改用【经典完整右键菜单】方案，菜单项同样在一级（系统菜单样式会变成 Windows 10 风格）。")
    else:
        registry.install(lean=False)
        registry.set_classic_menu(True)
        mode = "cascade"
        body = (f"COM 扩展不可用（{com_msg}），已回退到经典级联菜单方案。\n"
                "已切到 Windows 10 风格完整右键菜单，菜单项在一级。")

    registry.notify_explorer()
    winui.info_box(
        f"右键菜单已安装（当前用户，无需管理员）。\n\n{body}\n\n"
        f"注册位置：HKEY_CURRENT_USER\\{registry.PARENT_KEY}",
        "安装完成",
    )
    print_safe(f"install mode = {mode}")
    return 0


def do_uninstall(argv: list[str]) -> int:
    purge = "--purge" in argv
    registry.uninstall_msix()
    removed = registry.uninstall(remove_config=purge)
    registry.remove_com()
    registry.set_classic_menu(False)   # 还原 Win11 默认菜单样式
    registry.notify_explorer()
    winui.info_box(
        f"右键菜单已删除。\n\n"
        f"MSIX 菜单包：已移除\n"
        f"COM 外壳扩展：已注销\n"
        f"级联菜单：{'已删除' if removed['menu'] else '本来就不存在'}\n"
        f"临时文件：已清理\n"
        f"菜单样式：已还原 Windows 11 默认\n"
        f"配置数据：{'已删除' if removed.get('config') else '保留（如需删除：uninstall --purge）'}",
        "卸载完成",
    )
    return 0


def usage() -> str:
    return (
        f"文件格式转换工具 v{VERSION}\n\n"
        "converter.py install [--lean]        安装右键菜单\n"
        "converter.py uninstall [--purge]     卸载右键菜单\n"
        "converter.py classic on|off          经典完整右键菜单（一级菜单）/ 还原 Win11 默认\n"
        "converter.py check                   查看安装状态\n"
        "converter.py run <动词> <文件>...     执行一次转换（自动合并多进程）\n"
        "converter.py runm <动词> <文件>...    直接转换（不做多进程合并）\n"
        "converter.py util <名称> [文件]        执行辅助项\n"
        f"可用动词：{', '.join(VERB_ORDER)}\n"
        f"可用辅助项：{', '.join(UTILS)}"
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(usage())
        return 0

    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "run":
            if len(rest) < 2:
                winui.error_box("参数不足：run <动词> <文件>", "错误")
                return 2
            return do_run(rest[0], rest[1:])
        if cmd == "runm":          # 一次传入全部选中文件（不选举、直接转）
            if len(rest) < 2:
                winui.error_box("参数不足：runm <动词> <文件...>", "错误")
                return 2
            return do_run(rest[0], rest[1:], skip_collect=True)
        if cmd == "classic":
            return do_classic(rest)
        if cmd == "util":
            return do_util(rest[0], [Path(p) for p in rest[1:] if Path(p).exists()])
        if cmd == "install":
            return do_install(rest)
        if cmd == "uninstall":
            return do_uninstall(rest)
        if cmd == "check":
            print("已安装" if registry.is_installed() else "未安装")
            return 0
        if cmd in ("-v", "--version", "version"):
            print(f"FileConverter v{VERSION}")
            return 0
        if cmd == "selftest":
            from selftest import main as st_main

            return st_main(rest)
        print(usage())
        return 1
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 0
    except Exception as e:
        log("EXC " + traceback.format_exc())
        winui.ensure_console("转换出错")
        traceback.print_exc()
        winui.error_box(f"出错了：\n\n{type(e).__name__}: {e}", "错误")
        return 1


if __name__ == "__main__":
    sys.exit(main())
