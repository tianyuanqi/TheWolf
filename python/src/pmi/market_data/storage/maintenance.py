"""服务存活期间的本地完整性维护；与金融采集调度完全分开。"""
from threading import Event, Lock, Thread
from typing import Callable

from .database import Database, StorageError
from .integrity import Integrity
from .validation import check_all


class Maintenance:
    def __init__(self, database: Database, clear: Callable[[], None]):
        self.database, self.clear = database, clear
        self.integrity = Integrity(database)
        self.stop = Event()
        self._mutex = Lock()
        self._thread = None
        self.failure = None

    def check_once(self) -> None:
        state = self.integrity.status()
        if state['quarantined']:
            self.clear()
            return
        kind = 'full' if state['full_due'] else 'structure' if state['structure_due'] else None
        if kind is not None:
            self.clear()
            self.integrity.run(kind, semantic_check=lambda connection: check_all(self.database, connection))

    def start(self) -> None:
        with self._mutex:
            if self._thread is not None:
                return
            def worker():
                while not self.stop.is_set():
                    try:
                        self.check_once()
                    except StorageError as error:
                        if str(error) != 'storage_writer_busy':
                            self.failure = 'storage_maintenance_failed'
                            self.clear()
                    except Exception:
                        self.failure = 'storage_maintenance_failed'
                        self.clear()
                    if self.stop.wait(60):
                        break
            self._thread = Thread(target=worker, name='sqlite-integrity-maintenance', daemon=True)
            self._thread.start()

    def require_available(self) -> None:
        try:
            if self.failure:
                raise StorageError(self.failure)
            self.integrity.require_available()
        except BaseException:
            self.clear()
            raise

    def close(self, timeout: float = 50) -> bool:
        self.stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self.clear()
        return thread is None or not thread.is_alive()
