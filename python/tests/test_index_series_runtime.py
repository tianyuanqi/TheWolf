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
from pmi.market_data import index_series_store as store, index_series_update as update
from pmi.market_data.writer_lock import writer_lock
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


CRASH_CODE = r'''
import os,sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_series_contract import build_manifest
from pmi.market_data import index_series_store as store
from pmi.market_data.writer_lock import writer_lock
from test_index_series_contract import WINDOW, originals
from test_index_series_runtime import state
root,index,mode=Path(sys.argv[1]),get_index(sys.argv[2]),sys.argv[3]
items=originals(index,WINDOW,prices=('101.00','111.00','91.00','106.00'))
base_connection=store.candidate_connection
@contextmanager
def connection(path):
    with base_connection(path) as value:
        if mode=='journal_hot': value.execute('PRAGMA cache_size=1')
        yield value
original_unlink=store.os.unlink
original_new_file=store._new_file
def copy_or_crash(path,content):
    if mode=='copy_partial' and Path(path).name=='candidate.sqlite':
        Path(path).write_bytes(content[:128])
        os._exit(91)
    return original_new_file(path,content)
def unlink_or_crash(path,*args,**kwargs):
    if mode=='object_link' and Path(path).name.startswith('.index-v2-pending-'): os._exit(87)
    return original_unlink(path,*args,**kwargs)
def checkpoint(stage):
    if mode.startswith('journal') and stage=='before_commit': os._exit(86)
    if mode=='database_link' and stage=='database_linked': os._exit(87)
    if mode=='after_commit' and stage=='after_commit': os._exit(88)
    if mode=='exit:'+stage: os._exit(90)
with writer_lock(root):
    store.prepare_directories(root,index)
    prior=store.read_snapshot_locked(root,index)
    pending={**state(index,'hard-crash'),'previous_snapshot_id':prior['snapshot_id'] if prior else None}
    store.save_status(root,index,pending)
    with patch.object(store,'candidate_connection',connection),patch.object(store.os,'unlink',unlink_or_crash),patch.object(store,'_new_file',copy_or_crash):
        store.publish(root,index,WINDOW,build_manifest(index,WINDOW,items),items,pending,checkpoint)
raise AssertionError('crash point missed')
'''


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wolf-series-store-test-")
        self.root = Path(self.temporary.name).resolve()
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
        self.assertFalse(store.has_database(self.root, self.index))
        self.assertEqual(files(self.root), before)
        self.assertEqual(list(self.root.iterdir()), [])

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
        self.assertFalse(store.has_database(self.root, self.index))
        self.assertEqual(before, files(self.root))
        self.assertEqual(self.publish()["stage"], "completed")

    def test_schema_initialization_failure_does_not_publish_half_database(self):
        with patch.object(store, "_schema", side_effect=OSError("synthetic initialization interruption")):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(store.has_database(self.root, self.index))
        self.assertIsNone(store.read_snapshot(self.root, self.index))
        self.assertEqual(self.publish()["stage"], "completed")

    def test_copied_database_wrong_index_and_damaged_objects_fail_closed(self):
        committed = self.publish()
        other = INDICES[1]
        with writer_lock(self.root):
            target = store.prepare_directories(self.root, other)
            shutil.copyfile(store.index_root(self.root, self.index) / "index-v2.sqlite", target / "index-v2.sqlite")
        with self.assertRaisesRegex(SnapshotError, "wrong_database_index"):
            store.read_snapshot(self.root, other)
        obj = store.index_root(self.root, self.index) / "objects" / committed["snapshot_id"]
        obj.write_bytes(b"corrupt synthetic object")
        with self.assertRaisesRegex(SnapshotError, "object_hash_mismatch"):
            store.read_snapshot(self.root, self.index)
        with writer_lock(self.root), self.assertRaises(SnapshotError):
            store.write_object(store.index_root(self.root, self.index), canonical(build_manifest(self.index, WINDOW, originals())))

    def test_sidecars_symlinks_special_files_and_parent_lock(self):
        self.publish()
        root = store.index_root(self.root, self.index)
        for name in ("index-v2.sqlite-wal", "index-v2.sqlite-shm", "index-v2.sqlite-journal"):
            path = root / name
            path.write_bytes(b"unrecovered")
            with self.assertRaises(ReadUnavailable):
                store.read_snapshot(self.root, self.index)
            path.unlink()
        with writer_lock(self.root), self.assertRaises(ReadUnavailable):
            store.read_snapshot(self.root, self.index)
        path = root / "update-v2-status.json"
        path.symlink_to(root / "index-v2.sqlite")
        with self.assertRaises(ReadUnavailable):
            store.read_status(self.root, self.index)

    def test_current_observation_corruption_detected_without_writes(self):
        self.publish()
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE current_snapshot SET observation_id=?", ("0" * 64,))
        before = files(self.root)
        with self.assertRaises(SnapshotError):
            store.read_snapshot(self.root, self.index)
        self.assertEqual(before, files(self.root))


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
        self.start(fetch=fetch)
        self.assertTrue(self.runtime.wait(5))
        result = store.read_status(self.root, self.index)
        self.assertEqual(result["stage"], "failed")
        self.assertEqual(len(result["differences"]), 1)
        self.assertEqual(store.read_snapshot(self.root, self.index)["snapshot_id"], first["snapshot_id"])
        root = store.index_root(self.root, self.index)
        self.assertEqual(len((root / "index-v2-original-observations.jsonl").read_text().splitlines()), 2)
        self.assertTrue((root / "objects" / digest(bad[1].content)).exists())

    def test_source_not_ready_retains_current(self):
        first = self.publish()
        short = changed(originals(), 1, lambda body: body["data"]["klines"].pop())
        def fetch(parent, index, source, window, job, **kwargs):
            return next(item for item in short if item.source == source)
        self.start(fetch=fetch)
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
            with self.assertRaises(ReadUnavailable):
                store.read_status(self.root, INDICES[1])
            with self.assertRaisesRegex(SnapshotError, "writer_busy"):
                update.start_update(self.root, INDICES[1], WINDOW, budget=NetworkBudget(), runtime=update.Runtime(), fetch=fixture_fetch)
            with self.assertRaises(ReadUnavailable):
                store.read_snapshot(self.root, self.index)
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
        with writer_lock(self.root), self.assertRaises(ReadUnavailable):
            store.read_status(self.root, self.index)

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


class RecoveryTests(unittest.TestCase):
    """真实退出只发生在隔离候选，正式 sidecar 反例始终保留拒绝。"""
    publish = StoreTests.publish
    setUp = UpdateTests.setUp
    tearDown = UpdateTests.tearDown
    start = UpdateTests.start

    def crash(self, mode, root=None, index=None):
        completed = subprocess.run([sys.executable, "-B", "-c", CRASH_CODE, str(root or self.root),
                                    (index or self.index).index_id, mode], capture_output=True, timeout=40, check=False)
        expected = 86 if mode.startswith("journal") else 88 if mode == "after_commit" else 90 if mode.startswith("exit:") else 91 if mode == "copy_partial" else 87
        self.assertEqual(completed.returncode, expected, completed.stderr.decode(errors="replace"))

    def fingerprint(self, root=None):
        root = root or self.root
        return {str(path.relative_to(root)): (digest(path.read_bytes()), path.stat().st_dev, path.stat().st_ino,
                                             path.stat().st_size, path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                for path in root.rglob("*") if path.is_file()}

    def stages(self, root=None, index=None):
        return list(store.index_root(root or self.root, index or self.index).glob(".index-v2-stage-*"))

    def test_candidate_crashes_never_publish_or_modify_old_database(self):
        parent = self.root
        modes = ("copy_partial", "exit:candidate_copied", "exit:candidate_started", "journal_cold", "journal_hot",
                 "exit:candidate_committed", "exit:candidate_synced", "exit:publication_synced", "exit:before_publish")
        for mode in modes:
            with self.subTest(mode=mode):
                self.root = parent / mode.replace(":", "-")
                self.root.mkdir()
                baseline = self.publish()
                fixed = store.read_snapshot(self.root, self.index)
                path = store.index_root(self.root, self.index) / "index-v2.sqlite"
                before = (path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_ctime_ns)
                self.crash(mode)
                self.assertEqual((path.read_bytes(), path.stat().st_ino, path.stat().st_mtime_ns, path.stat().st_ctime_ns), before)
                self.assertEqual(store.read_snapshot(self.root, self.index), fixed)
                with writer_lock(self.root):
                    self.assertIsNone(store.committed_job_locked(self.root, self.index, "hard-crash"))
                    self.assertEqual(store.committed_job_locked(self.root, self.index, "test-job"), baseline)
                self.assertFalse(list(path.parent.glob("index-v2.sqlite-*")))
                residue = self.fingerprint(self.stages()[0])
                with writer_lock(self.root):
                    store.recover_locked(self.root, self.index)
                self.assertEqual(self.fingerprint(self.stages()[0]), residue)

    def test_first_unpublished_candidate_is_not_promoted(self):
        self.crash("exit:publication_synced")
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        self.assertFalse(path.exists())
        before = self.fingerprint()
        with writer_lock(self.root):
            store.recover_locked(self.root, self.index)
        self.assertEqual(self.fingerprint(), before)
        self.assertIsNone(store.read_snapshot(self.root, self.index))
        self.start()
        self.assertTrue(self.runtime.wait(20))
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "completed")
        self.assertTrue(self.stages())  # 旧候选仍保留，没有被提升或删除。

    def test_actual_published_crashes_keep_complete_job_and_all_old_references(self):
        parent = self.root
        for mode in ("exit:database_replaced", "exit:directory_synced", "exit:after_publish", "after_commit"):
            with self.subTest(mode=mode):
                self.root = parent / mode.replace(":", "-")
                self.root.mkdir()
                old = self.publish()
                fixed = store.read_snapshot(self.root, self.index)
                before_inode = (store.index_root(self.root, self.index) / "index-v2.sqlite").stat().st_ino
                self.crash(mode)
                self.assertNotEqual(before_inode, (store.index_root(self.root, self.index) / "index-v2.sqlite").stat().st_ino)
                final = store.read_status(self.root, self.index)
                self.assertEqual((final["job_id"], final["stage"]), ("hard-crash", "completed"))
                self.assertEqual(store.read_snapshot(self.root, self.index, old["snapshot_id"]), fixed)
                before = self.fingerprint()
                with writer_lock(self.root):
                    store.recover_locked(self.root, self.index)
                self.assertEqual(self.fingerprint(), before)

    def test_first_completed_database_two_links_recover_and_only_missing_skips_through_facade(self):
        self.crash("database_link")
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        self.assertEqual(path.stat().st_nlink, 2)
        database_bytes = path.read_bytes()
        with self.assertRaises(ReadUnavailable):
            store.read_snapshot(self.root, self.index)
        market = MarketData(self.root, {self.index.index_id: True})
        try:
            with patch("pmi.market_data.datetime") as clock, patch.object(update, "fetch_bounded") as fetch:
                clock.now.return_value = NOW
                result = market.update(self.index.index_id, only_missing=True)
                self.assertEqual(result, {"index_id": self.index.index_id, "stage": "completed", "result": "already_covered"})
                fetch.assert_not_called()
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertEqual(path.read_bytes(), database_bytes)
            self.assertEqual(market.status(self.index.index_id)["job_id"], "hard-crash")
            before = self.fingerprint()
            with patch("pmi.market_data.datetime") as clock, patch.object(update, "fetch_bounded") as fetch:
                clock.now.return_value = NOW
                market.update(self.index.index_id, only_missing=True)
                fetch.assert_not_called()
            self.assertEqual(self.fingerprint(), before)
        finally:
            self.assertTrue(market.close_updates(20))

    def test_first_link_recovery_real_exit_can_be_retried(self):
        self.crash("database_link")
        code = r'''
import os,sys
from pathlib import Path
from unittest.mock import patch
from pmi.market_data.index_catalog import get_index
from pmi.market_data import index_series_store as store
from pmi.market_data.writer_lock import writer_lock
root,index=Path(sys.argv[1]),get_index(sys.argv[2])
original=store.os.unlink
def crash(path,*args,**kwargs):
    if Path(path).name=='candidate.sqlite': os._exit(89)
    return original(path,*args,**kwargs)
with writer_lock(root),patch.object(store.os,'unlink',crash): store.recover_locked(root,index)
'''
        child = subprocess.run([sys.executable, "-B", "-c", code, str(self.root), self.index.index_id], capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 89, child.stderr)
        with writer_lock(self.root):
            store.recover_locked(self.root, self.index)
        self.assertEqual(store.read_status(self.root, self.index)["job_id"], "hard-crash")

    def test_first_link_rejects_tampered_receipts_external_and_third_links(self):
        parent = self.root
        for mode in ("hash", "job", "location", "missing", "extra", "external"):
            with self.subTest(mode=mode):
                self.root = parent / mode
                self.root.mkdir()
                self.crash("database_link")
                path = store.index_root(self.root, self.index) / "index-v2.sqlite"
                stage = self.stages()[0]
                proof = stage / "publication.json"
                if mode in {"hash", "job", "location"}:
                    value = json.loads(proof.read_text())
                    if mode == "hash": value["candidate_sha256"] = "0" * 64
                    elif mode == "job": value["completed_state"]["job_id"] = "other-job"
                    else: value["stage_location"]["inode"] += 1
                    value.pop("record_sha256")
                    value["record_sha256"] = digest(canonical(value))
                    proof.write_bytes(canonical(value))
                elif mode == "missing": proof.unlink()
                elif mode == "extra": (self.root / "third").hardlink_to(path)
                else:
                    (self.root / "outside").hardlink_to(path)
                    (stage / "candidate.sqlite").unlink()
                before = self.fingerprint()
                with writer_lock(self.root), self.assertRaises((ReadUnavailable, SnapshotError)):
                    store.recover_locked(self.root, self.index)
                self.assertEqual(self.fingerprint(), before)

    def test_original_sidecars_all_reject_before_any_mutation_in_actual_facade(self):
        self.publish()
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        market = MarketData(self.root, {self.index.index_id: True})
        try:
            for suffix in ("-journal", "-wal", "-shm"):
                for content in (b"", b"unknown original journal"):
                    with self.subTest(suffix=suffix, content=content):
                        auxiliary = Path(str(path) + suffix)
                        auxiliary.write_bytes(content)
                        before = self.fingerprint()
                        with patch("pmi.market_data.datetime") as clock, patch.object(update, "fetch_bounded") as fetch:
                            clock.now.return_value = NOW
                            with self.assertRaises(ReadUnavailable): market.update(self.index.index_id, only_missing=True)
                            fetch.assert_not_called()
                        with self.assertRaises(ReadUnavailable): market.read_daily(self.index.index_id)
                        self.assertEqual(self.fingerprint(), before)
                        auxiliary.unlink()
        finally:
            self.assertTrue(market.close_updates(20))

    def test_wrong_index_and_same_index_old_journal_never_remove_committed_rows(self):
        self.publish()
        self.crash("after_commit")  # 已提交 job，外部状态仍 publishing；AP1-01。
        fixed = store.read_snapshot(self.root, self.index)
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        for index in (self.index, INDICES[1]):
            with self.subTest(index=index.index_id), tempfile.TemporaryDirectory(dir=self.root) as directory:
                other = Path(directory)
                with writer_lock(other):
                    store.prepare_directories(other, index)
                    items = originals(index)
                    store.publish(other, index, WINDOW, build_manifest(index, WINDOW, items), items, state(index))
                self.crash("journal_hot", root=other, index=index)
                stages = self.stages(other, index)
                journal = stages[0] / "candidate.sqlite-journal"
                self.assertGreater(journal.stat().st_size, 512)
                auxiliary = Path(str(path) + "-journal")
                shutil.copyfile(journal, auxiliary)
                before = self.fingerprint()
                with self.assertRaises(ReadUnavailable): self.start()
                self.assertEqual(self.fingerprint(), before)
                auxiliary.unlink()
                self.assertEqual(store.read_snapshot(self.root, self.index, fixed["snapshot_id"]), fixed)
                with writer_lock(self.root):
                    self.assertIsNotNone(store.committed_job_locked(self.root, self.index, "hard-crash"))

    def test_object_link_real_exit_and_legacy_empty_database_link_compatibility(self):
        self.crash("object_link")
        with writer_lock(self.root): store.recover_locked(self.root, self.index)
        self.start()
        self.assertTrue(self.runtime.wait(20))
        self.assertEqual(store.read_status(self.root, self.index)["stage"], "completed")
        other = INDICES[1]
        with writer_lock(self.root):
            root = store.prepare_directories(self.root, other)
            pending = root / ".index-v2-db-pending-abcdefgh"
            with sqlite3.connect(pending) as connection: store._schema(connection, other)
            (root / "index-v2.sqlite").hardlink_to(pending)
            store.recover_locked(self.root, other)
        self.assertIsNone(store.read_snapshot(self.root, other))
        self.assertFalse(pending.exists())

    def test_candidate_full_history_and_current_tampering_never_publishes(self):
        self.publish()
        later = tuple(replace(item, started_at="2026-10-28T02:00:00Z", completed_at="2026-10-28T02:00:01Z") for item in originals())
        self.publish(items=later, job="same-content-later")
        self.publish(items=originals(prices=("102.00", "112.00", "92.00", "107.00")), job="noncurrent")
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        before = path.read_bytes()
        for mode in ("old_job", "old_snapshot", "current", "observation"):
            with self.subTest(mode=mode):
                def tamper(point):
                    if point != "candidate_synced": return
                    candidate = self.stages()[0] / "candidate.sqlite"
                    with sqlite3.connect(candidate) as connection:
                        if mode == "old_job": connection.execute("DELETE FROM committed_jobs WHERE job_id='test-job'")
                        elif mode == "old_snapshot": connection.execute("UPDATE snapshots SET anchor_date='2000-01-01' WHERE id=(SELECT snapshot_id FROM committed_jobs WHERE job_id='noncurrent')")
                        elif mode == "current": connection.execute("UPDATE current_snapshot SET snapshot_id=(SELECT snapshot_id FROM committed_jobs WHERE job_id='noncurrent'),observation_id=(SELECT json_extract(state,'$.observation_id') FROM committed_jobs WHERE job_id='noncurrent')")
                        else: connection.execute("UPDATE current_snapshot SET observation_id=(SELECT first_observation FROM snapshots WHERE id=current_snapshot.snapshot_id)")
                with self.assertRaises((SnapshotError, ReadUnavailable)):
                    self.publish(job="candidate-" + mode, checkpoint=tamper)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.stages(), [])

    def test_published_sync_or_identity_failure_is_unknown_and_preserves_stage(self):
        parent = self.root
        for mode in ("directory_fsync", "identity"):
            with self.subTest(mode=mode):
                self.root = parent / mode
                self.root.mkdir()
                self.publish()
                notifications, unknown = [], []
                target = store.index_root(self.root, self.index)
                original_sync = store.sync_directory
                publication_started = [False]
                def checkpoint(point):
                    if point == "database_replaced":
                        publication_started[0] = True
                        if mode == "identity": raise ReadUnavailable("synthetic final identity uncertain")
                def sync(path):
                    if mode == "directory_fsync" and publication_started[0] and path == target:
                        raise OSError("synthetic fsync failure")
                    return original_sync(path)
                with patch.object(store, "sync_directory", sync):
                    initial = self.start(checkpoint=checkpoint, notify=notifications.append, uncertain=unknown.append)
                    self.assertTrue(self.runtime.wait(20))
                self.assertEqual(unknown, [initial["job_id"]])
                self.assertFalse(any(item["stage"] == "completed" for item in notifications))
                self.assertEqual(store.raw_status(self.root, self.index)["stage"], "publishing")
                self.assertEqual(store.read_status(self.root, self.index)["job_id"], initial["job_id"])
                stage = self.stages()[0]
                self.assertTrue((stage / "before.sqlite").is_file())
                self.assertTrue((stage / "publication.json").is_file())

    def test_unpublished_failures_keep_original_and_clean_own_stage(self):
        self.publish()
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        before = path.read_bytes()
        for method in ("_new_file", "_sync_file", "_validate_publication", "os.replace"):
            with self.subTest(method=method):
                owner, name = (store.os, "replace") if method == "os.replace" else (store, method)
                with patch.object(owner, name, side_effect=OSError("synthetic failure")), self.assertRaises(OSError):
                    self.publish(job=method)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(self.stages(), [])

    def test_legitimate_inode_replacement_preserves_same_facade_guard_and_read(self):
        market = MarketData(self.root, {self.index.index_id: True})
        try:
            with patch("pmi.market_data.datetime") as clock, patch.object(update, "fetch_bounded", fixture_fetch):
                clock.now.return_value = NOW
                market.update(self.index.index_id)
                self.assertTrue(market.wait_updates(20))
                path = store.index_root(self.root, self.index) / "index-v2.sqlite"
                old_inode = path.stat().st_ino
                old = market.read_daily(self.index.index_id)
                market.update(self.index.index_id)
                self.assertTrue(market.wait_updates(20))
                self.assertNotEqual(path.stat().st_ino, old_inode)
                market.check_location()
                self.assertEqual(market.read_daily(self.index.index_id), old)
        finally:
            self.assertTrue(market.close_updates(20))

    def test_first_publish_unlink_failure_unknown_then_strict_recovery(self):
        notifications, unknown = [], []
        original_unlink = store.os.unlink
        def fail_candidate(path, *args, **kwargs):
            if Path(path).name == "candidate.sqlite":
                raise OSError("synthetic unlink failure after link")
            return original_unlink(path, *args, **kwargs)
        with patch.object(store.os, "unlink", fail_candidate):
            initial = self.start(notify=notifications.append, uncertain=unknown.append)
            self.assertTrue(self.runtime.wait(20))
        self.assertEqual(unknown, [initial["job_id"]])
        self.assertFalse(any(item["stage"] == "completed" for item in notifications))
        final = store.index_root(self.root, self.index) / "index-v2.sqlite"
        self.assertEqual(final.stat().st_nlink, 2)
        before = final.read_bytes()
        with patch.object(update, "fetch_bounded") as fetch:
            result = self.start(only_missing=True)
            fetch.assert_not_called()
        self.assertEqual(result["result"], "already_covered")
        self.assertEqual(final.stat().st_nlink, 1)
        self.assertEqual(final.read_bytes(), before)

    def test_first_unlinked_crashes_publish_complete_database(self):
        parent = self.root
        for point in ("database_unlinked", "directory_synced"):
            with self.subTest(point=point):
                self.root = parent / point
                self.root.mkdir()
                self.crash("exit:" + point)
                path = store.index_root(self.root, self.index) / "index-v2.sqlite"
                self.assertEqual(path.stat().st_nlink, 1)
                self.assertEqual(store.read_status(self.root, self.index)["job_id"], "hard-crash")

    def test_first_publish_no_clobber_and_link_failure(self):
        path = store.index_root(self.root, self.index) / "index-v2.sqlite"
        def race(point):
            if point == "before_publish": path.write_bytes(b"external sentinel")
        with self.assertRaises(FileExistsError): self.publish(checkpoint=race)
        self.assertEqual(path.read_bytes(), b"external sentinel")
        self.assertEqual(self.stages(), [])
        path.unlink()  # 测试自身注入的文件。
        link = store.os.link
        def fail(source, target, **kwargs):
            if Path(target).name == "index-v2.sqlite": raise OSError("synthetic link failure")
            return link(source, target, **kwargs)
        with patch.object(store.os, "link", fail), self.assertRaises(OSError): self.publish()
        self.assertFalse(path.exists())
        self.assertEqual(self.stages(), [])

    def test_prepublication_tampering_rejected_without_replacing_formal_database(self):
        parent = self.root
        for mode in ("candidate_symlink", "receipt", "backup", "directory", "original_inode"):
            with self.subTest(mode=mode):
                self.root = parent / mode
                self.root.mkdir()
                self.publish()
                final = store.index_root(self.root, self.index) / "index-v2.sqlite"
                before, before_inode = final.read_bytes(), final.stat().st_ino
                injected_inode = []
                def tamper(point):
                    if point != "before_publish": return
                    stage = self.stages()[0]
                    if mode == "candidate_symlink":
                        (stage / "candidate.sqlite").unlink()
                        (stage / "candidate.sqlite").symlink_to(final)
                    elif mode == "receipt": (stage / "publication.json").write_bytes(b"{}")
                    elif mode == "backup": (stage / "before.sqlite").write_bytes(b"changed")
                    elif mode == "directory":
                        moved = stage.with_name(stage.name + "-moved")
                        stage.rename(moved)
                        stage.mkdir()
                    else:
                        replacement = self.root / "external-replacement.sqlite"
                        replacement.write_bytes(before)
                        replacement.replace(final)
                        injected_inode.append(final.stat().st_ino)
                with self.assertRaises((ReadUnavailable, SnapshotError)):
                    self.publish(job="new", checkpoint=tamper)
                self.assertEqual(final.read_bytes(), before)
                self.assertEqual(final.stat().st_ino, injected_inode[0] if injected_inode else before_inode)


if __name__ == "__main__":
    unittest.main()
