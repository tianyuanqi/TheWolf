"""统一任务锁可显式交接worker，但连接及事务不可跨线程借用。"""
from pathlib import Path
import tempfile
import threading
import unittest

from pmi.market_data.storage.database import Database, StorageError
from pmi.market_data.storage.documents import Documents
from pmi.market_data.storage.tasks import Task, task_writer


class SqliteTaskTests(unittest.TestCase):
    def test_worker_handoff_and_no_permission_leak(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-task-', dir='/private/tmp') as directory:
            root = Path(directory)
            db = Database(root)
            db.initialize()
            task = Task.acquire(root)
            outcomes = []
            with task.use():
                with db.transaction() as connection:
                    first = Documents(connection).put({'state': 'accepted'})
            self.assertFalse(db.is_writer)
            with self.assertRaisesRegex(StorageError, 'storage_writer_busy'):
                with db.writer():
                    self.fail('未获准的同线程请求不能借用仍存活任务')
            with self.assertRaisesRegex(StorageError, 'storage_writer_busy'):
                Task.acquire(root)
            def worker():
                try:
                    with task.use():
                        self.assertTrue(Database(root).is_writer)
                        with Database(root).transaction() as connection:
                            self.assertEqual(Documents(connection).get(first), {'state': 'accepted'})
                            outcomes.append(Documents(connection).put({'state': 'completed'}))
                    self.assertFalse(Database(root).is_writer)
                except BaseException as error:
                    outcomes.append(error)
                finally:
                    task.close()
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(len(outcomes), 1)
            self.assertIsInstance(outcomes[0], str)
            with db.writer(), db.transaction() as connection:
                self.assertEqual(Documents(connection).get(outcomes[0]), {'state': 'completed'})
            with self.assertRaisesRegex(StorageError, 'storage_task_closed'):
                with task.use():
                    self.fail('已释放批次不能恢复写权限')
        self.assertFalse(root.exists())

    def test_nested_domains_and_failure_release_global_lock(self):
        with tempfile.TemporaryDirectory(prefix='wolf-sql-task-', dir='/private/tmp') as directory:
            root = Path(directory)
            db = Database(root)
            db.initialize()
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                with task_writer(root) as outer:
                    with task_writer(root) as inner:
                        self.assertIs(outer, inner)
                        with db.transaction() as connection:
                            Documents(connection).put({'domain': 'quota'})
                        raise RuntimeError('synthetic')
            self.assertFalse(db.is_writer)
            with db.writer():
                pass
        self.assertFalse(root.exists())
