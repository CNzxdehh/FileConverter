# -*- coding: utf-8 -*-
"""多选合并器的子进程：模拟"右键选中 N 个文件"时同时被拉起的 N 个实例之一。

打印结果： LEADER <文件数>  或  follow <文件数>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import collector  # noqa: E402

src = Path(sys.argv[1])
wait = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
files, leader = collector.collect("unittest", [src], wait)
if leader:
    for f in files:
        collector.mark_done(f)     # 模拟"转换完成"
    collector.finish()             # 主进程收尾，跟随者随即退出
print(("LEADER" if leader else "follow"), len(files))
