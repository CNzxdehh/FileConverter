# -*- coding: utf-8 -*-
"""多选合并器。

Windows 的静态右键动词对每个选中的文件各起一个进程、各自只能拿到 %1。
这里用一个临时"投递目录"做无服务的主进程选举：

    每个实例          →  %TEMP%/FileConv/<会话>/<token>.rec   写入自己拿到的文件
    最先启动的实例    →  写 state 文件成为主进程，收走全部文件一次性转换
    其余实例          →  等待主进程处理完，静默退出（期间靠 state 心跳判断主进程是否还活着）

容错：
    · 迟到者（主进程已开始转换才启动）→ 排队等主进程补扫；主进程挂了它就接管
    · 主进程每转完一个文件就刷新 state 时间戳，跟随者以此判断存活
    · 结束后会话目录被删掉，没有任何常驻进程

用法：
    files, leader = collector.collect(verb, files, wait_ms)
    if not leader: return            # 跟随者直接退出
    for f in files: ...; collector.heartbeat()
    if more := collector.more(): ... # 补扫迟到者
    collector.finish()
"""

from __future__ import annotations

import hashlib
import os
import random
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(tempfile.gettempdir()) / "FileConv"
STALE_SECONDS = 900      # 15 分钟前的会话目录视为残留，清掉
HEARTBEAT_STALE = 25     # 主进程 state 超过 25s 没刷新 → 认为它挂了，跟随者接管
FOLLOW_MAX = 1800        # 跟随者最多等待 30 分钟

_current: "Batch | None" = None


def _rmtree(d: Path) -> None:
    shutil.rmtree(d, ignore_errors=True)


def _cleanup_stale() -> None:
    try:
        if not ROOT.is_dir():
            return
        now = time.time()
        for d in ROOT.iterdir():
            try:
                if d.is_dir() and now - d.stat().st_mtime > STALE_SECONDS:
                    _rmtree(d)
            except Exception:
                pass
    except Exception:
        pass


def session_key(verb: str, first: Path) -> str:
    return hashlib.sha1(f"{verb}|{str(first.parent).lower()}".encode("utf-8")).hexdigest()[:12]


class Batch:
    def __init__(self, verb: str, files: list[Path]):
        self.verb = verb
        self.own_files = list(files)
        # token 里带启动时间戳：最先启动的实例名字最小
        self.token = f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:6]}"
        self.dir = ROOT / session_key(verb, files[0])
        self.rec = self.dir / f"{self.token}.rec"
        self.state = self.dir / "state"
        self.processed: set[str] = set()
        self.leader = False
        self._stop = False

    # ---- 记录读写 -------------------------------------------------- #
    def _write_rec(self) -> bool:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / f"{self.token}.tmp"
            tmp.write_text("\n".join(str(p) for p in self.own_files), encoding="utf-8")
            os.replace(tmp, self.rec)
            return True
        except Exception:
            return False

    def _read_state(self) -> str | None:
        try:
            return self.state.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None

    def _write_state(self, token: str) -> None:
        try:
            self.state.write_text(token, encoding="utf-8")
        except Exception:
            pass

    def _try_claim(self) -> bool:
        """原子抢占 state 文件（O_CREAT|O_EXCL）：谁创建成功谁是主进程。

        用文件创建而不是"比较 token 大小"，是为了避免主进程删掉自己的投递记录后
        剩下的人把赢家算成自己（那样会产生重复转换）。
        """
        try:
            fd = os.open(self.state, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(self.token)
            return True
        except (FileExistsError, PermissionError):
            return False
        except Exception:
            return False

    def _reclaim_if_stale(self) -> bool:
        """state 存在但心跳过期（主进程崩了）→ 删掉它重新抢。"""
        if self.state.exists() and not self._leader_alive():
            try:
                self.state.unlink()
            except Exception:
                pass
        return self._try_claim()

    def _state_mtime(self) -> float:
        try:
            return self.state.stat().st_mtime
        except Exception:
            return 0.0

    def heartbeat(self) -> None:
        """刷新 state 时间戳，告诉跟随者"我还活着"（每转完一个文件调用一次）。"""
        if self.leader:
            try:
                os.utime(self.state, None)
            except Exception:
                pass

    def start_heartbeat(self) -> None:
        """后台线程每 5 秒心跳一次：防止单个大文件转太久被跟随者误判为"挂了"。"""

        def loop():
            while not self._stop:
                try:
                    os.utime(self.state, None)
                except Exception:
                    pass
                time.sleep(5)

        threading.Thread(target=loop, daemon=True).start()

    def _all_files(self) -> list[Path]:
        out: list[Path] = []
        seen: set[str] = set()
        try:
            recs = sorted(self.dir.glob("*.rec"))
        except Exception:
            return list(self.own_files)
        for rec in recs:
            try:
                for line in rec.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and line.lower() not in seen:
                        seen.add(line.lower())
                        out.append(Path(line))
            except Exception:
                pass
        return out or list(self.own_files)

    # ---- 选举 ------------------------------------------------------ #
    def _leader_alive(self) -> bool:
        """state 文件存在且心跳新鲜 → 确实有主进程在干活。"""
        tok = self._read_state()
        if not tok or tok == self.token:
            return False
        return (time.time() - self._state_mtime()) < HEARTBEAT_STALE

    def gather(self, wait_ms: int) -> tuple[list[Path], bool]:
        _cleanup_stale()
        if not self._write_rec():
            return list(self.own_files), True

        # 已经有主进程在干活 → 直接进跟随模式
        if self._leader_alive():
            return self._follow()

        # 截止时刻按"会话里最早那条记录的创建时间"算，而不是各自进程的启动时间。
        # 这样晚启动的实例会立刻发现窗口已过、直接去跟随主进程，而不是自己另起一局。
        min_wait = max(wait_ms, 0) / 1000.0
        idle_wait = 0.35
        max_wait = min_wait + 3.0
        last_count = 0
        while True:
            if self._leader_alive():           # 别的实例先决定了
                return self._follow()
            try:
                recs = sorted(self.dir.glob("*.rec"), key=lambda p: p.stat().st_ctime)
            except Exception:
                recs = []
            now = time.time()
            if not recs:
                break
            started = recs[0].stat().st_ctime
            last_change = max(r.stat().st_mtime for r in recs)
            if now - started >= min_wait and now - last_change >= idle_wait:
                break
            if now - started >= max_wait:
                break
            time.sleep(0.05)

        # 我的投递记录没了 = 主进程已经把我的文件转完并清理了，别再转一遍
        if not self.rec.exists():
            return [], False

        # 原子抢占：只有一个人能创建 state 文件，赢了的就是主进程
        if self.state.exists() and self._leader_alive():
            return self._follow()
        if not self._reclaim_if_stale():
            return self._follow()

        self.leader = True
        self.start_heartbeat()
        files = self._all_files()
        files.sort(key=lambda p: (str(p.parent).lower(), p.name.lower()))
        return files, True

    def _follow(self) -> tuple[list[Path], bool]:
        """跟随者：等主进程把自己的文件收走；主进程挂了（心跳超时）就接管。"""
        t0 = time.monotonic()
        while time.monotonic() - t0 < FOLLOW_MAX:
            if not self.rec.exists():        # 主进程已经处理完并清理掉我的投递记录
                return [], False
            if not self.state.exists() or time.time() - self._state_mtime() > HEARTBEAT_STALE:
                # 主进程没了（转完/崩溃）。抢主进程前先随机抖一下，避免几个人同时接管
                time.sleep(random.uniform(0, 0.5))
                if not self.rec.exists():
                    return [], False
                if not self._reclaim_if_stale():
                    continue                 # 被别人抢走了，继续等
                self.leader = True
                self.start_heartbeat()
                return self._all_files(), True
            time.sleep(0.4)
        return [], False

    # ---- 收尾 ------------------------------------------------------ #
    def mark(self, path: Path) -> None:
        """标记一个文件已处理；对应的投递记录全部处理完就删掉，让那个跟随者进程立刻退出。"""
        self.processed.add(str(path).lower())
        if not self.leader:
            return
        try:
            for rec in self.dir.glob("*.rec"):
                try:
                    lines = [l.strip() for l in rec.read_text(encoding="utf-8").splitlines() if l.strip()]
                    if lines and all(l.lower() in self.processed for l in lines):
                        rec.unlink()
                except Exception:
                    pass
        except Exception:
            pass

    def more(self, settle: float = 0.8) -> list[Path]:
        """主进程补扫：返回"我还没处理"的迟到文件。

        没有新文件时也会再等 settle 秒（默认 0.6s）才返回空，
        给那些启动特别慢的实例一点投递时间。
        """
        if not self.leader:
            return []
        pending = [p for p in self._all_files() if str(p).lower() not in self.processed]
        if not pending and settle > 0:
            time.sleep(settle)
            pending = [p for p in self._all_files() if str(p).lower() not in self.processed]
        return pending

    def finish(self) -> None:
        self._stop = True
        try:
            if self.rec.exists():
                self.rec.unlink()
        except Exception:
            pass
        if self.leader:
            try:
                if self.state.exists():
                    self.state.unlink()
            except Exception:
                pass
            # 只删处理过的记录，没处理完的留着（万一还有跟随者在等）
            try:
                for rec in self.dir.glob("*.rec"):
                    try:
                        lines = [l.strip() for l in rec.read_text(encoding="utf-8").splitlines() if l.strip()]
                        if lines and all(l.lower() in self.processed for l in lines):
                            rec.unlink()
                    except Exception:
                        pass
                if not any(self.dir.iterdir()):
                    self.dir.rmdir()
            except Exception:
                pass


def collect(verb: str, files: list[Path], wait_ms: int = 1200) -> tuple[list[Path], bool]:
    global _current
    if not files:
        return [], False
    b = Batch(verb, files)
    got, leader = b.gather(wait_ms)
    _current = b if leader else None
    return got, leader


def heartbeat() -> None:
    if _current:
        _current.heartbeat()


def mark_done(path: Path) -> None:
    if _current:
        _current.mark(path)


def more(settle: float = 0.8) -> list[Path]:
    return _current.more(settle) if _current else []


def finish() -> None:
    global _current
    if _current:
        _current.finish()
        _current = None


def reset_all() -> None:
    _rmtree(ROOT)
