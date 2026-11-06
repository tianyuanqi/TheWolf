"""服务内周期预算：固定根账本、跨进程整批预留、出站前扣额及未知保护。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import threading
from typing import Callable, TypedDict, Literal

from pmi.market_data import SnapshotError
from pmi.market_data.activity.model import ActivityError
from pmi.market_data.read_only import checked_path, read_bytes
from pmi.market_data.index_history_calendar import SHANGHAI

MIB = 1024 * 1024
LEDGER = 'overview-periodic-ledger.json'
INDEX_IDS = ('sse:000001:price', 'sse:000688:price', 'szse:399001:price', 'szse:399006:price')
MARKET_ID = 'cn-a-turnover-sse-szse'


class Counter(TypedDict):
    requests: int
    bytes: int


class Batch(TypedDict):
    id: str
    target: str
    automatic: bool
    day: str
    state: Literal['running', 'completed', 'failed']
    remaining: list[list[str | int]]
    reason: str | None


class Attempt(TypedDict):
    id: str
    batch: str
    key: str
    day: str
    limit: int
    actual_bytes: int | None
    success: bool | None


class Ledger(TypedDict):
    version: str
    scope_id: str
    last_day: str | None
    days: dict[str, Counter]
    months: dict[str, Counter]
    batches: list[Batch]
    attempts: list[Attempt]


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_ledger_key')
        result[key] = value
    return result


def _day(value: str) -> bool:
    return isinstance(value, str) and date.fromisoformat(value).isoformat() == value


class BudgetError(ActivityError, SnapshotError):
    """只携带稳定码；不把本机路径或原始异常发送给页面。"""
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PeriodicOptions:
    """可信服务的固定周期策略；默认值为本人批准额度。"""
    daily_requests: int = 80
    daily_bytes: int = 32 * MIB
    monthly_requests: int = 500
    monthly_bytes: int = 512 * MIB

    def __post_init__(self) -> None:
        for value in (self.daily_requests, self.daily_bytes, self.monthly_requests, self.monthly_bytes):
            if type(value) is not int or value <= 0:
                raise ValueError('invalid_periodic_limits')
        if self.daily_requests > 80 or self.daily_bytes > 32 * MIB or self.monthly_requests > 500 or self.monthly_bytes > 512 * MIB:
            raise ValueError('periodic_limits_exceed_approved_policy')
        if self.daily_requests > self.monthly_requests or self.daily_bytes > self.monthly_bytes:
            raise ValueError('invalid_periodic_limits')

    def public(self) -> dict:
        return {'version': 'overview-periodic-v1', 'timezone': 'Asia/Shanghai', 'check_time': '07:00',
                'daily_requests': self.daily_requests, 'daily_bytes': self.daily_bytes,
                'monthly_requests': self.monthly_requests, 'monthly_bytes': self.monthly_bytes,
                'charging': 'response-limit-no-refund', 'ledger_version': 'overview-periodic-ledger-v1'}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def scope_id(root: Path, activity_root: Path) -> str:
    """账本身份绑定规范价格／量额根；配置别名和实例变化不能另获额度。"""
    for path in (root, activity_root):
        checked_path(path)
        if path.resolve() != path or not path.is_dir():
            raise ValueError('invalid_periodic_scope')
    return hashlib.sha256(_canonical([str(root), str(activity_root)])).hexdigest()


def initialize(root: Path, activity_root: Path) -> None:
    """仅供明确授权的初始化；正常构造、状态GET和重启不隐式创建账本。"""
    path = checked_path(root / LEDGER)
    initial = {'version': 'overview-periodic-ledger-v1', 'scope_id': scope_id(root, activity_root),
               'last_day': None, 'days': {}, 'months': {}, 'batches': [], 'attempts': []}
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        raw = memoryview(_canonical(initial))
        while raw:
            count = os.write(fd, raw)
            if count <= 0:
                raise BudgetError('periodic_ledger_write_failed')
            raw = raw[count:]
        os.fsync(fd)
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.close(fd)


class Budget:
    """一根一个账本；整个批次持排他锁，GET遇到未完整写入会受控拒绝。"""
    def __init__(self, root: Path, activity_root: Path, options: PeriodicOptions,
                 clock: Callable[[], datetime] | None = None):
        self.root, self.path, self.options = root, checked_path(root / LEDGER), options
        self.scope = scope_id(root, activity_root)
        self.clock = clock or (lambda: datetime.now(SHANGHAI))
        self._mutex = threading.RLock()
        self.active: Lease | None = None
        self._identity = self._stat_identity()
        self.read()

    def _stat_identity(self) -> tuple[int, int]:
        checked_path(self.path)
        info = self.path.stat()
        if not self.path.is_file() or info.st_nlink != 1:
            raise BudgetError('periodic_ledger_invalid')
        return info.st_dev, info.st_ino

    def read(self) -> Ledger:
        """状态读取不建账、不加写锁、不恢复、不续额落盘。"""
        if self._stat_identity() != self._identity:
            raise BudgetError('periodic_ledger_replaced')
        try:
            data = json.loads(read_bytes(self.path), object_pairs_hook=_unique)
            if data['version'] != 'overview-periodic-ledger-v1' or data['scope_id'] != self.scope:
                raise ValueError()
            if set(data) != {'version', 'scope_id', 'last_day', 'days', 'months', 'batches', 'attempts'}:
                raise ValueError()
            for groups in (data['days'], data['months']):
                if not isinstance(groups, dict): raise ValueError()
                for value in groups.values():
                    if set(value) != {'requests', 'bytes'} or any(type(n) is not int or n < 0 for n in value.values()): raise ValueError()
            if not isinstance(data['batches'], list) or not isinstance(data['attempts'], list): raise ValueError()
            batch_ids = set()
            for row in data['batches']:
                if set(row) != {'id', 'target', 'automatic', 'day', 'state', 'remaining', 'reason'}:
                    raise ValueError()
                if not isinstance(row['id'], str) or not re.fullmatch('[a-f0-9]{32}', row['id']) or row['id'] in batch_ids:
                    raise ValueError()
                batch_ids.add(row['id'])
                if not _day(row['day']) or type(row['automatic']) is not bool or not isinstance(row['target'], str):
                    raise ValueError()
                if row['state'] not in {'running', 'completed', 'failed'} or not isinstance(row['remaining'], list):
                    raise ValueError()
                if row['reason'] is not None and (not isinstance(row['reason'], str) or not re.fullmatch('[a-z_]{1,100}', row['reason'])):
                    raise ValueError()
                if row['state'] != 'running' and row['remaining']:
                    raise ValueError()
                for item in row['remaining']:
                    if not isinstance(item, list) or len(item) != 2 or not isinstance(item[0], str) or type(item[1]) is not int or item[1] not in (MIB, 65536):
                        raise ValueError()
            if sum(row['state'] == 'running' for row in data['batches']) > 1:
                raise ValueError()
            if data['last_day'] is not None and (not _day(data['last_day']) or any(row['day'] > data['last_day'] for row in data['batches'])):
                raise ValueError()
            # 持久计数须能从每个已扣请求重放；不能删历史请求而保留较小计数。
            days, months = {}, {}
            ids = set()
            for item in data['attempts']:
                if set(item) != {'id', 'batch', 'key', 'day', 'limit', 'actual_bytes', 'success'} or item['batch'] not in batch_ids:
                    raise ValueError()
                if not _day(item['day']) or data['last_day'] is None or item['day'] > data['last_day'] or not isinstance(item['key'], str):
                    raise ValueError()
                if not isinstance(item['id'], str) or not re.fullmatch('[a-f0-9]{32}', item['id']) or item['success'] is not None and type(item['success']) is not bool:
                    raise ValueError()
                if item['id'] in ids or item['limit'] not in (MIB, 65536) or item['actual_bytes'] is not None and (type(item['actual_bytes']) is not int or not 0 <= item['actual_bytes'] <= item['limit']): raise ValueError()
                ids.add(item['id'])
                for groups, key in ((days, item['day']), (months, item['day'][:7])):
                    value = groups.setdefault(key, {'requests': 0, 'bytes': 0}); value['requests'] += 1; value['bytes'] += item['limit']
            if days != data['days'] or months != data['months']: raise ValueError()
            return data
        except (KeyError, TypeError, ValueError, UnicodeDecodeError) as error:
            raise BudgetError('periodic_ledger_invalid') from error

    def day(self) -> str:
        now = self.clock()
        if now.tzinfo is None: raise BudgetError('periodic_clock_invalid')
        return now.astimezone(SHANGHAI).date().isoformat()

    def _check_time(self, data: dict, day: str) -> None:
        if data['last_day'] and day < data['last_day']:
            raise BudgetError('periodic_clock_regressed')

    def _enough(self, data: dict, day: str, requests: int, count: int) -> None:
        self._check_time(data, day)
        for group, key, max_requests, max_bytes in (
            ('months', day[:7], self.options.monthly_requests, self.options.monthly_bytes),
            ('days', day, self.options.daily_requests, self.options.daily_bytes)):
            used = data[group].get(key, {'requests': 0, 'bytes': 0})
            if requests + used['requests'] > max_requests or count + used['bytes'] > max_bytes:
                raise BudgetError('periodic_' + ('daily' if group == 'days' else 'monthly') + '_exhausted')

    def begin(self, plan: list[tuple[str, int]], *, target: str, automatic: bool) -> Lease:
        """整批先获锁及四项余额，失败不创建批次，不产生网络尝试。"""
        import uuid
        with self._mutex:
            if self.active is not None: raise BudgetError('periodic_busy')
            fd = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != self._identity: raise BudgetError('periodic_ledger_replaced')
                data = self.read(); day = self.day()
                if any(row['state'] == 'running' for row in data['batches']): raise BudgetError('periodic_unresolved_batch')
                if automatic and any(row['automatic'] and row['day'] == day and row['target'] == target for row in data['batches']): raise BudgetError('periodic_already_attempted')
                if any(type(limit) is not int or limit not in (MIB, 65536) or not isinstance(key, str) for key, limit in plan): raise BudgetError('periodic_plan_invalid')
                self._enough(data, day, len(plan), sum(limit for _, limit in plan))
                row = {'id': uuid.uuid4().hex, 'target': target, 'automatic': automatic, 'day': day,
                       'state': 'running', 'remaining': [list(x) for x in plan], 'reason': None}
                data['last_day'] = day; data['batches'].append(row)
                lease = Lease(self, fd, data, row); lease._save(); self.active = lease
                return lease
            except BlockingIOError as error:
                os.close(fd); raise BudgetError('periodic_busy') from error
            except BaseException:
                os.close(fd); raise

    def status(self) -> dict:
        data = self.read(); day = self.day(); self._check_time(data, day)
        daily = data['days'].get(day, {'requests': 0, 'bytes': 0}); monthly = data['months'].get(day[:7], {'requests': 0, 'bytes': 0})
        now = self.clock().astimezone(SHANGHAI); tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        month_end = (now.replace(day=28, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=4)).replace(day=1)
        result = {'day': day, 'month': day[:7], 'daily': daily, 'monthly': monthly,
                  'daily_resets_at': tomorrow.isoformat(), 'monthly_resets_at': month_end.isoformat(),
                  'warning': any(value >= limit * .8 for value, limit in ((daily['requests'], self.options.daily_requests), (daily['bytes'], self.options.daily_bytes), (monthly['requests'], self.options.monthly_requests), (monthly['bytes'], self.options.monthly_bytes))),
                  'active': next((row for row in reversed(data['batches']) if row['state'] == 'running'), None),
                  'last_batch': data['batches'][-1] if data['batches'] else None}
        return result


class Lease:
    """仅由持排他锁的Budget创建；各传输层消费同一份已批准出站计划。"""
    def __init__(self, budget: Budget, fd: int, data: Ledger, row: Batch):
        self.budget, self.fd, self.data, self.row = budget, fd, data, row
        self._mutex = threading.RLock(); self.closed = False

    def _save(self) -> None:
        # 同inode更新保留锁身份；GET可能遇到短写，按账本无效暂拒而非修复。
        if self.budget._stat_identity() != self.budget._identity: raise BudgetError('periodic_ledger_replaced')
        raw = _canonical(self.data); os.lseek(self.fd, 0, os.SEEK_SET)
        view = memoryview(raw)
        while view:
            count = os.write(self.fd, view)
            if count <= 0: raise BudgetError('periodic_ledger_write_failed')
            view = view[count:]
        os.ftruncate(self.fd, len(raw)); os.fsync(self.fd)

    def ensure(self) -> None:
        if self.closed or self.budget.active is not self: raise BudgetError('periodic_lease_invalid')

    def charge(self, key: str, limit: int) -> str:
        """每次出站前持久扣额；跨日月按剩余整批重新预检，不重复扣月额。"""
        import uuid
        with self._mutex:
            self.ensure(); wanted = [key, limit]
            if wanted not in self.row['remaining']: raise BudgetError('periodic_unplanned_request')
            day = self.budget.day(); remaining = self.row['remaining']
            self.budget._enough(self.data, day, len(remaining), sum(x[1] for x in remaining))
            self.row['remaining'].remove(wanted)
            identifier = uuid.uuid4().hex
            self.data['attempts'].append({'id': identifier, 'batch': self.row['id'], 'key': key,
                                          'day': day, 'limit': limit, 'actual_bytes': None, 'success': None})
            for group, period in (('days', day), ('months', day[:7])):
                count = self.data[group].setdefault(period, {'requests': 0, 'bytes': 0}); count['requests'] += 1; count['bytes'] += limit
            self.data['last_day'] = day; self._save(); return identifier

    def settle(self, identifier: str, actual_bytes: int | None, success: bool) -> None:
        """实际字节单列，不冲减按硬限已扣额度；未知仍保持已扣。"""
        with self._mutex:
            self.ensure(); row = next(x for x in self.data['attempts'] if x['id'] == identifier)
            if actual_bytes is not None and (type(actual_bytes) is not int or not 0 <= actual_bytes <= row['limit']): raise BudgetError('periodic_receipt_invalid')
            row.update(actual_bytes=actual_bytes, success=success); self._save()

    def finish(self, reason: str | None = None) -> None:
        """只释放能证明尚未出站的计划；已扣尝试永久保留，崩溃不自动调用。"""
        with self._mutex, self.budget._mutex:
            if self.closed: return
            if reason == 'periodic_unresolved_batch':
                # 无法确认发布或工作线程终态时，只释放操作系统锁，持久占位继续阻断新请求。
                self.row.update(state='running', reason=reason)
            else:
                self.row.update(state='failed' if reason else 'completed', reason=reason, remaining=[])
            try: self._save()
            finally:
                self.closed = True; self.budget.active = None; os.close(self.fd)
