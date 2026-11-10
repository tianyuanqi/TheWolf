"""实例内的有界计算缓存；键由完整请求身份组成，失败不缓存。"""
from collections import OrderedDict
import json
from threading import Lock, RLock
from typing import Callable


class ResultCache:
    def __init__(self):
        self._values = OrderedDict()
        self._bytes = 0
        self._lock = Lock()
        # SQLite逐行装配释放GIL；多个首页视图同时解码会反复争用它。
        # 只串行未缓存计算，缓存命中不等待计算锁。
        self._calculate = RLock()
        self._generation = 0

    def clear(self) -> None:
        with self._lock:
            self._values.clear()
            self._bytes = 0
            self._generation += 1

    def get(self, key: tuple, calculate: Callable[[], dict]) -> dict:
        with self._lock:
            value = self._values.get(key)
            if value is not None:
                self._values.move_to_end(key)
        if value is None:
            with self._calculate:
                with self._lock:
                    value = self._values.get(key)
                    generation = self._generation
                    if value is not None:
                        self._values.move_to_end(key)
                if value is None:
                    value = json.dumps(calculate(), ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
                    if len(value) <= 32 * 1048576:
                        with self._lock:
                            # 维护/断连清理不能被较早开始的计算重新填回。
                            if generation == self._generation:
                                previous = self._values.pop(key, None)
                                self._bytes -= len(previous) if previous else 0
                                self._values[key] = value
                                self._bytes += len(value)
                                while len(self._values) > 12 or self._bytes > 32 * 1048576:
                                    _, removed = self._values.popitem(last=False)
                                    self._bytes -= len(removed)
        return json.loads(value)
