"""指数 v2 存储和任务生命周期隔离测试；所有金融响应均为合成。"""
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from pmi.market_data import MarketData, ReadUnavailable, SnapshotError
from pmi.market_data.index_activity import activity
from pmi.market_data.index_catalog import INDICES
from pmi.market_data.index_history_calendar import complete_window
from pmi.market_data.index_series_contract import build_manifest, digest, canonical
from pmi.market_data.index_series_fetch import FetchInterrupted, NetworkBudget
from pmi.market_data import index_series_update as update
from pmi.market_data.storage import index_store as store
from pmi.market_data.storage import Database, StorageError
from pmi.market_data.storage.tasks import Task
from pmi.market_data.storage.documents import Documents
from sqlite_fixture import price_writer as writer_lock, initialize as initialize_sqlite
from test_index_series_contract import NOW, WINDOW, originals, changed, change_east_price


def files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def state(index, job="test-job"):
    return {**store.idle_state(index), "job_id": job, "trigger": "manual", "stage": "publishing",
            "result": "business_changed", "target_start": WINDOW.start, "target_end": WINDOW.end,
            "started_at": NOW.isoformat(), "message": "synthetic"}


def fixture_fetch(parent, index, source, window, job, **kwargs):
    return next(item for item in originals(index, window) if item.source == source)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wolf-series-store-test-")
        self.root = Path(self.temporary.name).resolve()
        initialize_sqlite(self.root)
        self.index = INDICES[0]


    def tearDown(self):
        self.temporary.cleanup()


    def publish(self, index=None, items=None, job="test-job", window=WINDOW, checkpoint=None):
        index = index or self.index
        items = items or originals(index, window)
        with writer_lock(self.root):
            store.prepare_directories(self.root, index)
            return store.publish(self.root, index, window, build_manifest(index, window, items), items,
                                 {**state(index, job), "target_start": window.start, "target_end": window.end}, checkpoint)


    def test_empty_get_creates_nothing(self):
        before = files(self.root)
        self.assertIsNone(store.read_snapshot(self.root, self.index))
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "idle")
        self.assertTrue(Database(self.root).exists)
        self.assertEqual(files(self.root), before)
        self.assertTrue((self.root/"facts.sqlite").is_file())


    def test_six_indices_replay_and_evidence_isolation(self):
        published = [self.publish(index, job=index.code) for index in INDICES]
        before = files(self.root)
        for index, committed in zip(INDICES, published):
            snapshot = store.read_snapshot(self.root, index)
            self.assertEqual(snapshot["snapshot_id"], committed["snapshot_id"])
            self.assertEqual(snapshot["instrument"]["id"], index.index_id)
            self.assertEqual(len(snapshot["bars"]), len(WINDOW.dates))
            for evidence in snapshot["evidence"]:
                proof = store.read_evidence(self.root, index, snapshot["snapshot_id"], evidence["object_id"])
                self.assertEqual(proof["rows"], evidence["rows"])
                self.assertEqual(proof["verification"], snapshot["verification"])
            other = published[(INDICES.index(index) + 1) % 6]
            self.assertIsNone(store.read_snapshot(self.root, index, other["snapshot_id"]))
            with self.assertRaises(SnapshotError):
                store.read_evidence(self.root, index, snapshot["snapshot_id"], other["snapshot_id"])
        self.assertEqual(before, files(self.root))


    def test_first_observation_stable_and_older_observation_cannot_revert_current(self):
        first = self.publish()
        later_items = tuple(replace(item, started_at="2026-10-28T02:00:00Z", completed_at="2026-10-28T02:00:01Z") for item in originals())
        second = self.publish(items=later_items, job="later")
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertNotEqual(first["observation_id"], second["observation_id"])
        self.assertEqual(store.read_snapshot(self.root, self.index)["observation_id"], first["observation_id"])
        old_items = originals(prices=("101.00", "111.00", "91.00", "106.00"))
        old = self.publish(items=old_items, job="old-observation")
        self.assertNotEqual(old["snapshot_id"], first["snapshot_id"])
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], first["snapshot_id"])
        self.assertIsNotNone(store.read_snapshot(self.root, self.index, old["snapshot_id"]))


    def test_fractional_timestamps_order_by_instant_and_old_anchor_cannot_advance(self):
        first_items = tuple(replace(item, started_at="2026-10-28T01:00:00Z", completed_at="2026-10-28T01:00:00Z") for item in originals())
        self.publish(items=first_items)
        changed_items = tuple(replace(item, started_at="2026-10-28T01:00:00.100000Z", completed_at="2026-10-28T01:00:00.100000Z")
                              for item in originals(prices=("101.00", "111.00", "91.00", "106.00")))
        second = self.publish(items=changed_items, job="fractional")
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], second["snapshot_id"])
        later = complete_window(NOW.replace(day=26))
        earlier = complete_window(NOW.replace(day=25))
        self.assertEqual(later.end, earlier.end)
        # 使用另一指数隔离现有较新窗口，再给旧 anchor 更晚的观察时刻。
        index = INDICES[1]
        latest = self.publish(index=index, job="new-anchor", window=later)
        older = tuple(replace(item, started_at="2026-10-28T02:00:00Z", completed_at="2026-10-28T02:00:00Z") for item in originals(index, earlier))
        self.publish(index=index, items=older, job="old-anchor", window=earlier)
        self.assertEqual(store.read_snapshot(self.root, index)["snapshot_id"], latest["snapshot_id"])


    def test_job_replay_and_conflicting_job_rejected(self):
        first = self.publish()
        self.assertEqual(self.publish(), first)
        different = originals(prices=("101.00", "111.00", "91.00", "106.00"))
        with self.assertRaisesRegex(SnapshotError, "job_content_conflict"):
            self.publish(items=different)
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], first["snapshot_id"])


    def test_before_commit_retains_current_after_commit_is_recoverable(self):
        first = self.publish()
        items = originals(prices=("101.00", "111.00", "91.00", "106.00"))
        def fail_before(stage):
            if stage == "before_commit":
                raise OSError("synthetic crash")
        with self.assertRaises(OSError):
            self.publish(items=items, job="before", checkpoint=fail_before)
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], first["snapshot_id"])
        with writer_lock(self.root):
            self.assertIsNone(store.committed_job_locked(self.root, self.index, "before"))
        def fail_after(stage):
            if stage == "after_commit":
                raise OSError("synthetic crash")
        with self.assertRaises(OSError):
            self.publish(items=items, job="after", checkpoint=fail_after)
        with writer_lock(self.root):
            proof = store.committed_job_locked(self.root, self.index, "after")
            store.save_status(self.root, self.index, {**state(self.index, "after"), "stage": "publishing"})
        self.assertEqual(store.read_status(self.root, self.index), proof)
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], proof["snapshot_id"])


    def test_first_failed_transaction_can_retry_and_reads_stay_pure(self):
        def failure(stage):
            if stage == "before_commit":
                raise OSError("synthetic")
        with self.assertRaises(OSError):
            self.publish(checkpoint=failure)
        before = files(self.root)
        self.assertIsNone(store.read_snapshot(self.root, self.index))
        self.assertTrue(Database(self.root).exists)
        self.assertEqual(before, files(self.root))
        self.assertEqual(self.publish()["stage"], "completed")


class UpdateTests(unittest.TestCase):
    publish = StoreTests.publish

    def setUp(self):
        StoreTests.setUp(self)
        self.runtime = update.Runtime()

    def tearDown(self):
        self.assertTrue(self.runtime.close(5))
        StoreTests.tearDown(self)

    def start(self, **kwargs):
        return update.start_update(self.root, self.index, WINDOW, budget=NetworkBudget(), runtime=self.runtime,
                                   fetch=kwargs.pop("fetch", fixture_fetch), **kwargs)

    def test_accepted_before_fetch_immutable_receipt_and_completion(self):
        events = []
        def accepted(receipt, replay):
            events.append("accepted")
            self.assertFalse(replay)
            receipt["message"] = "callback mutation"
        def fetch(*args, **kwargs):
            self.assertEqual(events[0], "accepted")
            events.append("fetch")
            return fixture_fetch(*args, **kwargs)
        initial = self.start(accepted=accepted, fetch=fetch)
        self.assertEqual(initial["stage"], "preparing")
        self.assertTrue(self.runtime.wait(5))
        final = store.read_status(self.root, self.index)
        self.assertEqual(final["stage"], "completed")
        self.assertEqual(final["result"], "business_changed")
        self.assertEqual(initial["stage"], "preparing")
        self.assertNotEqual(initial["message"], "callback mutation")

    def test_price_mismatch_preserves_current_and_all_differences_and_originals(self):
        first = self.publish()
        bad = changed(originals(), 1, lambda body: change_east_price(body, 0, 2, "106.00"))
        def fetch(parent, index, source, window, job, **kwargs):
            return next(item for item in bad if item.source == source)
        initial = self.start(fetch=fetch)
        self.assertTrue(self.runtime.wait(5))
        result = store.read_status(self.root, self.index)
        self.assertEqual(result["stage"], "failed")
        self.assertEqual(len(result["differences"]), 1)
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], first["snapshot_id"])
        root = store.index_root(self.root, self.index)
        with Database(root).read() as connection:
            records = [Documents(connection).get(row[0]) for row in connection.execute("SELECT metadata FROM source_observation")]
            self.assertEqual(sum(record.get("job_id")==initial["job_id"] for record in records), 2)
        self.assertTrue((root / "objects" / digest(bad[1].content)).exists())

    def test_source_not_ready_retains_current(self):
        first = self.publish()
        short = changed(originals(), 1, lambda body: body["data"]["klines"].pop())
        def fetch(parent, index, source, window, job, **kwargs):
            return next(item for item in short if item.source == source)
        initial = self.start(fetch=fetch)
        self.assertTrue(self.runtime.wait(5))
        final = store.read_status(self.root, self.index)
        self.assertEqual((final["stage"], final["result"]), ("completed", "source_not_ready"))
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], first["snapshot_id"])

    def test_active_proof_requires_exact_index_job_and_owner(self):
        entered, release = threading.Event(), threading.Event()
        def fetch(*args, **kwargs):
            entered.set()
            release.wait(5)
            return fixture_fetch(*args, **kwargs)
        try:
            initial = self.start(fetch=fetch)
            self.assertTrue(entered.wait(2))
            active = store.read_status(self.root, self.index)
            self.assertEqual(active["job_id"], initial["job_id"])
            self.assertIn(active["stage"], update.ACTIVE)
            self.assertEqual(store.read_status(self.root, INDICES[1])["stage"], "idle")
            with self.assertRaisesRegex((SnapshotError, StorageError), "writer_busy"):
                update.start_update(self.root, INDICES[1], WINDOW, budget=NetworkBudget(), runtime=update.Runtime(), fetch=fixture_fetch)
            self.assertIsNone(store.read_snapshot(self.root, self.index))
        finally:
            release.set()
        self.assertTrue(self.runtime.wait(5))

    def test_stale_active_status_read_interrupted_without_disk_repair(self):
        with writer_lock(self.root):
            store.prepare_directories(self.root, self.index)
            store.save_status(self.root, self.index, {**state(self.index), "stage": "fetching_csindex"})
        before = files(self.root)
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "interrupted")
        self.assertEqual(before, files(self.root))
        with writer_lock(self.root):
            self.assertEqual(store.read_status(self.root, self.index)["stage"], "interrupted")

    def test_commit_status_write_failure_recovered_without_false_failure(self):
        def crash(stage):
            if stage == "before_status":
                raise OSError("simulated status failure")
        notified = []
        initial = self.start(checkpoint=crash, notify=lambda result: notified.append(result))
        self.assertTrue(self.runtime.wait(5))
        final = store.read_status(self.root, self.index)
        self.assertEqual(final["stage"], "completed")
        self.assertEqual(final["job_id"], initial["job_id"])
        self.assertEqual(notified[-1]["stage"], "completed")

    def test_notify_failure_marks_unknown_but_keeps_committed_success(self):
        unknown = []
        def notify(value):
            raise OSError("secret must not be logged")
        initial = self.start(notify=notify, uncertain=unknown.append)
        self.assertTrue(self.runtime.wait(5))
        self.assertEqual(unknown, [initial["job_id"]])
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "completed")

    def test_thread_start_failure_returns_same_initial_then_terminal_failure(self):
        receipts = []
        with patch.object(threading.Thread, "start", side_effect=RuntimeError("synthetic")):
            initial = self.start(accepted=lambda receipt, replay: receipts.append(receipt))
        self.assertEqual(initial, receipts[0])
        self.assertEqual(initial["stage"], "preparing")
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "failed")
        self.assertTrue(self.runtime.wait(0))
        with writer_lock(self.root):
            pass

    def test_accepted_failure_never_starts_fetch_and_releases_locks(self):
        def accepted(*args):
            raise OSError("synthetic receipt failure")
        with patch("pmi.market_data.index_series_update.fetch_bounded") as fetch, self.assertRaises(OSError):
            self.start(accepted=accepted)
        fetch.assert_not_called()
        self.assertTrue(self.runtime.wait(0))
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "interrupted")
        with writer_lock(self.root):
            pass

    def test_close_stops_only_own_instance_and_wait_does_not_stop(self):
        other_dir = tempfile.TemporaryDirectory(prefix="wolf-series-other-")
        other_runtime = update.Runtime()
        entered = threading.Event()
        def blocked(parent, index, source, window, job, **kwargs):
            entered.set()
            if kwargs["stop"].wait(5):
                raise FetchInterrupted("synthetic shutdown")
            return fixture_fetch(parent, index, source, window, job)
        try:
            self.start(fetch=blocked)
            self.assertTrue(entered.wait(2))
            self.assertFalse(self.runtime.wait(.01))
            self.assertFalse(self.runtime.stop.is_set())
            initialize_sqlite(Path(other_dir.name).resolve())
            update.start_update(Path(other_dir.name).resolve(), self.index, WINDOW, budget=NetworkBudget(), runtime=other_runtime, fetch=fixture_fetch)
            self.assertTrue(self.runtime.close(5))
            self.assertFalse(other_runtime.stop.is_set())
            self.assertTrue(other_runtime.wait(5))
            self.assertEqual(store.read_status(self.root, self.index)["stage"], "interrupted")
            with self.assertRaisesRegex(SnapshotError, "runtime_closed"):
                self.start()
        finally:
            other_runtime.close(5)
            other_dir.cleanup()

    def test_stale_window_rejected_before_any_fetch(self):
        later = complete_window(NOW + timedelta(days=1))
        self.publish(window=later)
        with self.assertRaisesRegex(SnapshotError, "stale_window"), patch("pmi.market_data.index_series_update.fetch_bounded") as fetch:
            self.start()
        fetch.assert_not_called()

    def test_facade_new_canonical_preserves_old_read_and_records_new_locations(self):
        market = MarketData(self.root, {self.index.index_id: True})
        try:
            with patch("pmi.market_data.index_series_update.fetch_bounded", fixture_fetch), patch("pmi.market_data.datetime") as clock:
                clock.now.return_value = NOW
                market.update(self.index.index_id)
                self.assertTrue(market.wait_updates(5))
            view = market.read_daily(self.index.index_id)
            self.assertEqual(view["format"], "v2")
            self.assertEqual(view["snapshot"]["storage_decimals"], 2)
            with self.assertRaises(ValueError): market.read_daily("000300")
        finally:
            self.assertTrue(market.close_updates(5))

    def test_latest_success_survives_repeated_failure_interruption_and_not_ready(self):
        self.start()
        self.assertTrue(self.runtime.wait(5))
        first = store.read_snapshot(self.root, self.index)
        later = tuple(replace(item, started_at="2026-10-28T02:00:00Z", completed_at="2026-10-28T02:00:01Z") for item in originals())
        def later_fetch(parent, index, source, window, job, **kwargs):
            return next(item for item in later if item.source == source)
        self.start(fetch=later_fetch)
        self.assertTrue(self.runtime.wait(5))
        self.assertEqual(store.read_status(self.root, self.index)["result"], "unchanged")
        def failed(*args, **kwargs):
            raise OSError("synthetic")
        def interrupted(*args, **kwargs):
            raise FetchInterrupted("synthetic")
        short = changed(later, 1, lambda body: body["data"]["klines"].pop())
        def not_ready(parent, index, source, window, job, **kwargs):
            return next(item for item in short if item.source == source)
        for fetch in (failed, failed, interrupted, failed, not_ready, failed):
            initial = self.start(fetch=fetch)
            self.assertEqual(initial["last_success_at"], "2026-10-28T02:00:01Z")
            self.assertTrue(self.runtime.wait(5))
            self.assertEqual(store.read_status(self.root, self.index)["last_success_at"], "2026-10-28T02:00:01Z")
        self.assertEqual(store.read_snapshot(self.root, self.index), first)



CRASH_CODE = r"""
import os, sys
from pathlib import Path
from pmi.market_data.storage import Database, index_store as store
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_series_contract import build_manifest
from test_index_series_contract import WINDOW, originals
from test_index_series_runtime import state
root, mode = Path(sys.argv[1]), sys.argv[2]
index=get_index('csi:000300:price')
items=originals(index,WINDOW,prices=('101.00','111.00','91.00','106.00'))
database=Database(root)
def checkpoint(stage):
    if stage==mode: os._exit(86)
with database.writer() as connection:
    connection.execute('PRAGMA cache_size=1')
    store.save_status(root,index,state(index,'hard-crash'))
    store.publish(root,index,WINDOW,build_manifest(index,WINDOW,items),items,state(index,'hard-crash'),checkpoint)
raise AssertionError('crash point missed')
"""


class RecoveryTests(unittest.TestCase):
    """实际进程退出验证单库事务；恢复用已核备份，新格式不重用旧文件替换协议。"""
    setUp = StoreTests.setUp
    tearDown = StoreTests.tearDown
    publish = StoreTests.publish

    def test_actual_exit_before_and_after_commit_and_backup_restore(self):
        import os
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools/migrations'))
        from backup_sqlite import backup
        with tempfile.TemporaryDirectory(prefix='wolf-sql-crash-',dir='/private/tmp') as parent:
            base=Path(parent)
            for existing in (False,True):
                for phase in ('objects_written','candidate_started','before_commit','after_commit'):
                    with self.subTest(existing=existing,phase=phase):
                        case=base/(str(existing)+'-'+phase);case.mkdir()
                        root=case/'data';root.mkdir();initialize_sqlite(root)
                        prior=None
                        if existing:
                            with writer_lock(root):
                                items=originals(self.index,WINDOW)
                                store.publish(root,self.index,WINDOW,build_manifest(self.index,WINDOW,items),items,state(self.index))
                            prior=store.read_snapshot(root,self.index)
                        saved=case/'backup';backup(root,saved)
                        child=subprocess.run([sys.executable,'-B','-c',CRASH_CODE,str(root),phase],capture_output=True,text=True,
                            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=25)
                        self.assertEqual(child.returncode,86,child.stderr)
                        before=files(root)
                        if phase=='before_commit':
                            self.assertTrue((root/'facts.sqlite-journal').exists())
                            with self.assertRaisesRegex(StorageError,'recovery_required'):
                                store.read_snapshot(root,self.index)
                            with self.assertRaisesRegex(StorageError,'recovery_required'):
                                with Database(root).writer():pass
                        else:
                            actual=store.read_snapshot(root,self.index)
                            if phase=='after_commit':
                                self.assertIsNotNone(actual)
                                self.assertEqual(store.read_status(root,self.index)['job_id'],'hard-crash')
                                if prior:self.assertEqual(store.read_snapshot(root,self.index,prior['snapshot_id']),prior)
                            else:self.assertEqual(actual,prior)
                        self.assertEqual(files(root),before)
                        restored=case/'restored';receipt=backup(saved,restored)
                        self.assertTrue(receipt['passed'])
                        self.assertEqual(store.read_snapshot(restored,self.index),prior)

    def test_all_sidecars_reject_before_read_or_write(self):
        self.publish()
        for suffix in ('-journal','-wal','-shm'):
            path=self.root/('facts.sqlite'+suffix);path.write_bytes(b'unrecovered synthetic journal')
            try:
                before=files(self.root)
                with self.assertRaisesRegex(StorageError,'recovery_required'):store.read_snapshot(self.root,self.index)
                with self.assertRaisesRegex(StorageError,'recovery_required'):
                    with Database(self.root).writer():pass
                self.assertEqual(files(self.root),before)
            finally:path.unlink()

    def test_current_observation_wrong_series_and_missing_reference_reject(self):
        first=self.publish();second=self.publish(index=INDICES[1],job='second')
        database=Database(self.root);saved=database.path.read_bytes()
        try:
            for reference in ('0'*64,second['observation_id']):
                with sqlite3.connect(database.path) as connection:
                    connection.execute("UPDATE current_publication SET observation_id=? WHERE domain_id='price-v2' AND subject=?",(reference,self.index.index_id))
                before=files(self.root)
                with self.assertRaises(SnapshotError):store.read_snapshot(self.root,self.index)
                self.assertEqual(files(self.root),before)
                database.path.write_bytes(saved)
        finally:database.path.write_bytes(saved)
        self.assertEqual(store.read_snapshot(self.root,self.index)['snapshot_id'],first['snapshot_id'])

    def test_database_inode_or_root_replacement_rejects_frozen_facade(self):
        self.publish();data=MarketData(self.root,{})
        original=self.root/'facts.sqlite';saved=self.root/'saved.sqlite'
        try:
            saved.write_bytes(original.read_bytes());saved.replace(original)
            with self.assertRaises(StorageError):data.read_daily(self.index.index_id)
        finally:data.close_updates()

    def test_schema_failure_never_implicitly_initializes_or_promotes(self):
        from pmi.market_data.storage import schema
        with tempfile.TemporaryDirectory(prefix='wolf-init-fail-',dir='/private/tmp') as directory:
            root=Path(directory);database=Database(root)
            with patch.object(schema,'SCHEMA',schema.SCHEMA+'INVALID SQL;'),self.assertRaises(sqlite3.Error):database.initialize()
            before=files(root)
            with self.assertRaises(StorageError):MarketData(root,{})
            self.assertEqual(files(root),before)
            with self.assertRaises(StorageError):Database(root).initialize()


if __name__=='__main__':unittest.main()
