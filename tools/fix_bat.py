# -*- coding: utf-8 -*-
"""把 .bat 转成 GBK + CRLF（Windows cmd 要求）。

⚠️ 历史版本有两个 bug：
1. 写文件时若 GBK 编码失败，文件已被 'w' 模式截断成 0 字节，内容全丢。
   现在改成先在内存里编码，成功后才落盘。
2. 旧版用 f-string 写 b'\\r\\n'，实际变成字面反斜杠，CRLF 校验永远为假。
"""
import io
import sys
from pathlib import Path


def fix(p: Path) -> bool:
    raw = p.read_bytes()
    text = None
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = raw.decode("utf-8", errors="replace")

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out = "\r\n".join(text.split("\n"))

    # 先在内存里编码，失败就不要碰磁盘（否则会把文件截断成空）
    try:
        data = out.encode("gbk")
    except UnicodeEncodeError as e:
        print(f"{p.name}: GBK 编码失败，未改动文件 -- {e}")
        print("  提示：把 emoji 换成 ASCII（GBK 编不了 ⛔ ✅ 这类符号）")
        return False

    p.write_bytes(data)
    ok = data.count(b"\r\n") == data.count(b"\n") and data.count(b"\r\n") > 0
    print(f"{p.name}: {len(data)}B  CRLF-ok={ok}")
    return ok


if __name__ == "__main__":
    allok = True
    for a in sys.argv[1:]:
        allok &= fix(Path(a))
    sys.exit(0 if allok else 1)