# -*- coding: utf-8 -*-
"""把 .bat 统一转成 GBK + CRLF（Windows cmd 要求）。

用法： python tools\\fix_bat.py a.bat b.bat
"""
import io
import sys
from pathlib import Path


def fix(p: Path) -> None:
    raw = p.read_bytes()
    for enc in ("utf-8-sig", "gbk"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = "\r\n".join(text.split("\n"))
    io.open(p, "w", encoding="gbk", newline="").write(out)
    raw2 = p.read_bytes()
    print(f"{p.name}: {len(raw2)}B  CRLF-ok={raw2.count(b'\\r\\n') == raw2.count(b'\\n')}")


if __name__ == "__main__":
    for a in sys.argv[1:]:
        fix(Path(a))
