# -*- coding: utf-8 -*-
"""从 src/core/tasks.py 生成 native/verbs_gen.h（COM 扩展的菜单项表）。

只生成"转换类"动词，不含实用项（自定义目录/检查环境等），
因为一级菜单要给的是转换功能；实用项仍在经典菜单的级联里。
"""
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core.tasks import SPECS, VERB_ORDER  # noqa: E402


def cstr(s: str) -> str:
    return 'L"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    lines = ["// 本文件由 native/gen_verbs.py 自动生成，勿手改"]
    for verb in VERB_ORDER:
        spec = SPECS[verb]
        lines.append(f"{{{cstr(verb)}, {cstr(spec['label'])}}},")
    out = ROOT / "native" / "verbs_gen.h"
    io.open(out, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print(f"已生成 {out}（{len(VERB_ORDER)} 项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
