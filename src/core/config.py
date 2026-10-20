# -*- coding: utf-8 -*-
"""配置读写：自定义输出目录 / ffmpeg 路径 / 批处理参数。"""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "FileConverter"
CONFIG_FILE = "config.json"

DEFAULTS = {
    "out_dir": None,        # 自定义输出文件夹；None = 输出到原文件同目录
    "ffmpeg_path": None,    # 手动指定的 ffmpeg.exe 路径
    "collect_ms": 1500,     # 多选文件合并的等待窗口（毫秒）
    "suffix": "_转换后",    # 输出文件名后缀
    "mp3_bitrate": "192k",
    "mp4_crf": "23",
}


def app_dir() -> Path:
    """存放配置与日志的目录（%APPDATA%\\FileConverter）。"""
    base = os.environ.get("APPDATA") or str(Path.home())
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return app_dir() / CONFIG_FILE


def log_dir() -> Path:
    p = app_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


class Config(dict):
    def __init__(self, data: dict | None = None):
        super().__init__(DEFAULTS)
        if data:
            self.update({k: v for k, v in data.items() if k in DEFAULTS})

    def load() -> "Config":  # type: ignore[override]
        try:
            raw = config_path().read_text(encoding="utf-8")
            return Config(json.loads(raw))
        except Exception:
            return Config()

    def save(self) -> None:
        config_path().write_text(
            json.dumps(self, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def set_out_dir(path: str | Path | None) -> Path:
    cfg = Config.load()
    cfg["out_dir"] = str(path) if path else None
    cfg.save()
    return config_path()


def out_root(cfg: Config, src: Path) -> Path:
    """输出根目录：自定义目录优先，否则原文件所在目录。"""
    d = cfg.get("out_dir")
    if d:
        p = Path(d)
        if p.is_dir():
            return p
    return src.parent


def unique_path(p: Path) -> Path:
    """目标文件已存在时追加序号，避免覆盖用户数据。"""
    if not p.exists():
        return p
    stem, ext, parent = p.stem, p.suffix, p.parent
    for i in range(2, 1000):
        cand = parent / f"{stem}_{i}{ext}"
        if not cand.exists():
            return cand
    return parent / f"{stem}_{os.getpid()}{ext}"
