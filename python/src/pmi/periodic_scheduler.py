"""服务生命周期内调度，不建立系统任务，不唤醒或启动已退出服务。"""
from __future__ import annotations

from datetime import datetime
import threading
from typing import Callable

from pmi.market_data.index_history_calendar import SHANGHAI


class Scheduler:
    """启动合并一次，随后每日07:00检查；等待及墙钟均可隔离控制。"""
    def __init__(self, check: Callable[[], bool | None], stop: threading.Event,
                 clock: Callable[[], datetime] | None = None):
        self.check, self.stop = check, stop
        self.clock = clock or (lambda: datetime.now(SHANGHAI))
        self.started = False
        self.checked_day: str | None = None
        self._mutex = threading.Lock()

    def tick(self) -> bool:
        """仅检查当前应执行目标；休眠跨多日也只合并一次，不循环补跑。"""
        if self.stop.is_set() or not self._mutex.acquire(blocking=False):
            return False
        try:
            now = self.clock().astimezone(SHANGHAI)
            day = now.date().isoformat()
            due = now.hour >= 7 and (self.checked_day is None or day > self.checked_day)
            if self.started and not due:
                return False
            # 其他入口正持批次锁时尚未开始本次检查；释放后合并一次，不丢掉当天机会。
            if self.check() is False:
                return False
            self.started = True
            if now.hour >= 7:
                self.checked_day = day
            return True
        finally:
            self._mutex.release()

    def run(self) -> None:
        """短间隔重算上海日期，退出事件立即结束等待。"""
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(15)
