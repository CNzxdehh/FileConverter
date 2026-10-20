# -*- coding: utf-8 -*-
"""诊断工具：列出 Explorer 视角下某个文件的右键菜单项，确认【转换文件格式】是否真的出现。

用法：
    python tools\\check_menu.py                # 默认查一个临时 txt
    python tools\\check_menu.py D:\\a\\b.png     # 查指定文件

为什么需要它：注册表写对了 ≠ 菜单会显示。Explorer 对 SubCommands 很挑，
只有用 Verbs() 枚举才能验证"真的出现了"。
需要 pywin32： pip install pywin32
"""
import os
import sys

import win32com.client

PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["TEMP"], "verb_probe", "probe.txt")


def main() -> int:
    if not os.path.exists(PATH):
        print("文件不存在:", PATH)
        return 2
    folder_dir, name = os.path.split(PATH)
    sh = win32com.client.Dispatch("Shell.Application")
    folder = sh.Namespace(folder_dir)
    if folder is None:
        print("Namespace 失败:", folder_dir)
        return 2
    item = folder.ParseName(name)
    if item is None:
        print("ParseName 失败:", name)
        return 2

    print(f"=== {name} 的右键动词（Explorer 视角）===")
    hit = False
    for v in item.Verbs():
        nm = (v.Name or "").replace("&", "")
        mark = ""
        if "转换" in nm:
            hit = True
            mark = "   <=== 找到了"
        print(f"  - {nm}{mark}")
    print()
    print("结论:", "菜单项已出现在右键菜单中" if hit else "菜单项【没有】出现")
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main())
