"""独立量额文件库：不可变对象、单指针提交、CAS与已有文件只读。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import os
import re
from pathlib import Path
import stat
import tempfile
import time
from threading import Event
from typing import Iterator

from pmi.market_data.read_only import checked_path, read_bytes
from .model import ActivityError, MARKET, MARKET_IDS, TWO_MARKET, SERIES, canonical, digest, identifier, load


class Store:
    """构造只冻结已有根，读取绝不建目录、锁或恢复。"""
    def __init__(self, root: Path):
        checked_path(root)
        if not root.is_dir() or root.resolve() != root:
            raise ValueError('量额根必须已存在且无链接')
        self.root = root
        self.identities = {p: (p.stat().st_dev, p.stat().st_ino) for p in (root, *root.parents)}

    def check(self) -> None:
        for path, identity in self.identities.items():
            checked_path(path)
            if (path.stat().st_dev, path.stat().st_ino) != identity:
                raise ActivityError('activity_location_changed')

    def path(self, *parts: str) -> Path:
        self.check()
        path = checked_path(self.root.joinpath(*parts))
        if not path.is_relative_to(self.root):
            raise ActivityError('activity_path_invalid')
        if path.exists():
            current = path.stat()
            if not stat.S_ISREG(current.st_mode) or current.st_nlink != 1:
                raise ActivityError('activity_file_invalid')
        return path

    def read(self, *parts: str, limit: int = 4 * 1048576) -> bytes | None:
        path = self.path(*parts)
        if not path.exists():
            return None
        result = read_bytes(path, limit + 1)
        if len(result) > limit:
            raise ActivityError('activity_size_exceeded')
        self.check()
        return result

    def json(self, *parts: str) -> dict | None:
        content = self.read(*parts)
        return load(content) if content is not None else None

    @contextmanager
    def lock(self, *, write: bool, cancel: Event | None = None) -> Iterator[None]:
        """读入口立即返回竞争；周期写入口可取消地等待读锁，最多30秒，不重试出站。"""
        path = self.path('.activity.lock')
        if not write and not path.exists():
            yield
            return
        fd = os.open(path, (os.O_RDWR | os.O_CREAT if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ActivityError('activity_file_invalid')
            deadline = time.monotonic() + 30
            while True:
                try:
                    fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError as error:
                    if not write or cancel is None or time.monotonic() >= deadline:
                        raise ActivityError('activity_busy') from error
                    if cancel.wait(.05):
                        raise ActivityError('activity_cancelled') from error
            self.check()
            yield
            self.check()
        finally:
            os.close(fd)

    def write(self, parts: tuple[str, ...], content: bytes, *, immutable: bool = False) -> None:
        """持写锁后原子写和fsync，immutable对象冲突拒绝；只清本次暂存。"""
        path = self.path(*parts)
        for parent in reversed(path.parent.relative_to(self.root).parents):
            directory = checked_path(self.root / parent)
            created = not directory.exists()
            directory.mkdir(exist_ok=True)
            if created:
                descriptor = os.open(directory.parent, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        created = not path.parent.exists()
        path.parent.mkdir(exist_ok=True)
        if created:
            descriptor = os.open(path.parent.parent, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        checked_path(path.parent)
        if immutable and path.exists():
            if self.read(*parts) != content:
                raise ActivityError('immutable_conflict')
            return
        fd, temporary = tempfile.mkstemp(prefix='.activity-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.path(*parts)
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def location(series: str, target: str) -> tuple[str, ...]:
        if series not in SERIES:
            raise ActivityError('unknown_activity_series', 422)
        if series == TWO_MARKET:
            from datetime import date
            try:
                if date.fromisoformat(target).isoformat() != target: raise ValueError()
            except (ValueError, TypeError):
                raise ActivityError('invalid_activity_parameters', 422) from None
            return ('market', 'sse-szse', 'current-by-anchor', target + '.json')
        if series == MARKET:
            return ('market', 'cn-a', 'current.json')
        identifier(target)
        return ('index', series.replace(':', '_'), 'current-by-price', target + '.json')

    def current(self, series: str, target: str) -> dict | None:
        result = self.json(*self.location(series, target))
        if result is not None and (result['series_id'] != series or result['target'] != target):
            # 全市场只有一个current，旧anchor须使用固定V；指数位置自身就是P。
            if series == MARKET and result['series_id'] == series:
                return None
            raise ActivityError('activity_identity_mismatch')
        return result

    def observations(self, activity_id: str, manifest: dict) -> list[dict]:
        """校验独立观察索引及提交归属；预提交条目不发布，GET不补写恢复。

        索引在指针提交前追加，金融V不包含获取时点。完成操作或尚未恢复的
        当前指针是提交凭据；旧操作保留观察引用，因此current前移后仍可追溯。
        """
        index = self.json('observation-refs', activity_id + '.json')
        binding = {'series_id': manifest['series_id'], 'activity_id': activity_id,
                   'price_snapshot_id': manifest['price_snapshot_id']}
        if index is None or set(index) != {*binding, 'entries'} or any(index[k] != v for k, v in binding.items()):
            raise ActivityError('activity_observation_invalid')
        target = manifest['price_snapshot_id'] or manifest['anchor_date']
        pointer = self.current(manifest['series_id'], target)
        result, seen = [], set()
        for entry in index['entries']:
            if set(entry) != {'request_id', 'observation_id'} or re.fullmatch('[a-zA-Z0-9_-]{1,80}', entry['request_id']) is None:
                raise ActivityError('activity_observation_invalid')
            if entry['request_id'] in seen:
                raise ActivityError('activity_observation_invalid')
            seen.add(entry['request_id'])
            operation = self.json('operations', entry['request_id'] + '.json')
            if operation is None or operation['request_id'] != entry['request_id'] or operation['series_id'] != manifest['series_id'] or operation['target'] != target or operation['state'] not in {'preparing', 'completed', 'failed', 'interrupted'}:
                raise ActivityError('activity_observation_invalid')
            if operation['state'] == 'preparing' and pointer and pointer['operation']['request_id'] == entry['request_id']:
                committed = pointer['operation']
                if any(committed[k] != operation[k] for k in ('series_id', 'request_id', 'target', 'signature', 'config_id', 'instance_id')):
                    raise ActivityError('activity_operation_mismatch')
                operation = committed
            if operation['state'] != 'completed':
                continue
            if operation['activity_id'] != activity_id or operation['observation_id'] != entry['observation_id']:
                raise ActivityError('activity_observation_invalid')
            oid = identifier(entry['observation_id'])
            raw = self.read('observations', oid + '.json')
            if raw is None or hashlib.sha256(raw).hexdigest() != oid:
                raise ActivityError('activity_observation_invalid')
            observation = load(raw)
            if canonical(observation) != raw:
                raise ActivityError('activity_observation_invalid')
            self._validate_observation(observation, binding, manifest)
            result.append({**observation, 'observation_id': oid, 'request_id': entry['request_id']})
        if not result:
            raise ActivityError('activity_observation_uncommitted')
        return result

    def _validate_observation(self, observation: dict, binding: dict, manifest: dict) -> None:
        """写入提交前和读取时共用回执归属、源成员与时点校验，不推断发布时间。"""
        if set(observation) != {*binding, 'sources'} or any(observation[k] != v for k, v in binding.items()):
            raise ActivityError('activity_observation_invalid')
        refs = [{k: source[k] for k in ('source', 'object_id', 'url')} for source in observation['sources']]
        if not refs or sorted(refs, key=canonical) != sorted(manifest['sources'], key=canonical):
            raise ActivityError('activity_observation_invalid')
        for source in observation['sources']:
            if set(source) != {'source', 'object_id', 'url', 'started_at', 'completed_at', 'published_at'} or source['published_at'] is not None:
                raise ActivityError('activity_observation_invalid')
            try:
                start, end = (datetime.fromisoformat(source[k]) for k in ('started_at', 'completed_at'))
                if start.utcoffset() is None or end.utcoffset() is None or start > end:
                    raise ValueError()
            except (ValueError, TypeError) as error:
                raise ActivityError('activity_observation_invalid') from error
            self.original(source['object_id'])

    def fixed(self, activity_id: str) -> dict | None:
        identifier(activity_id)
        raw = self.read('snapshots', activity_id + '.json')
        if raw is None:
            return None
        if hashlib.sha256(raw).hexdigest() != activity_id:
            raise ActivityError('activity_digest_mismatch')
        manifest = load(raw)
        if canonical(manifest) != raw:
            raise ActivityError('activity_digest_mismatch')
        return manifest

    def original(self, object_id: str) -> bytes:
        identifier(object_id)
        raw = self.read('objects', object_id)
        if raw is None or hashlib.sha256(raw).hexdigest() != object_id:
            raise ActivityError('activity_evidence_invalid')
        return raw

    def publish(self, manifest: dict, originals: dict[str, bytes], expected: str | None, operation: dict, observation: dict) -> str:
        """先落不可变输入，最终单指针同时提交结果和请求归属；指针即提交凭据。"""
        series = manifest['series_id']
        target = manifest['price_snapshot_id'] or manifest['anchor_date']
        pointer = self.json(*self.location(series, target))
        if (pointer['activity_id'] if pointer else None) != expected:
            raise ActivityError('activity_cas_conflict')
        if pointer:
            old = self.fixed(pointer['activity_id'])
            if old is None:
                raise ActivityError('activity_digest_mismatch')
            self.observations(pointer['activity_id'], old)
            previous = {row['trade_date']: row for row in old['rows']}
            for row in manifest['rows']:
                if row['trade_date'] not in previous:
                    continue
                pairs = [(previous[row['trade_date']][k], row[k]) for k in ('volume', 'amount')] if series not in MARKET_IDS else [
                    (x, next((v for v in row['components'][k] if v['locator'] == x['locator']), {'value': None})) for k in (('sse', 'szse') if series == TWO_MARKET else ('sse', 'szse', 'bse')) for x in previous[row['trade_date']]['components'][k]]
                if any(before['value'] is not None and after['value'] is None for before, after in pairs):
                    raise ActivityError('activity_degradation_rejected')
        activity_id = digest(manifest)
        for object_id, raw in originals.items():
            if hashlib.sha256(raw).hexdigest() != identifier(object_id):
                raise ActivityError('activity_evidence_invalid')
            self.write(('objects', object_id), raw, immutable=True)
        self.write(('snapshots', activity_id + '.json'), canonical(manifest), immutable=True)
        observation = {**observation, 'activity_id': activity_id, 'price_snapshot_id': manifest['price_snapshot_id']}
        binding = {'series_id': series, 'activity_id': activity_id, 'price_snapshot_id': manifest['price_snapshot_id']}
        self._validate_observation(observation, binding, manifest)
        observation_id = digest(observation)
        self.write(('observations', observation_id + '.json'), canonical(observation), immutable=True)
        index_parts = ('observation-refs', activity_id + '.json')
        index = self.json(*index_parts)
        if index is None:
            index = {**binding, 'entries': []}
        elif set(index) != {*binding, 'entries'} or any(index[k] != v for k, v in binding.items()):
            raise ActivityError('activity_observation_invalid')
        entry = {'request_id': operation['request_id'], 'observation_id': observation_id}
        if any(x['request_id'] == entry['request_id'] for x in index['entries']):
            raise ActivityError('activity_operation_mismatch')
        index['entries'].append(entry)
        self.write(index_parts, canonical(index))
        committed = {**operation, 'state': 'completed', 'activity_id': activity_id, 'reason': None, 'observation_id': observation_id}
        self.write(self.location(series, target), canonical({'series_id': series, 'target': target, 'activity_id': activity_id,
                                                          'operation': committed, 'observation_id': observation_id}))
        return activity_id
