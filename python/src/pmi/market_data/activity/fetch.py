"""量额有限取数：固定URL、不跟随跳转、持久预留预算，失败不退预算。"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import os
from pathlib import Path
import stat
from threading import Event
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pmi.market_data.read_only import checked_path
from .model import ActivityError, MAX_BYTES, MARKET_MAX_BYTES, THREE_SOURCE_KEYS, Options, Original, canonical, load, rule
from .sources import url, market_url
from pmi.market_data.periodic_budget import Lease


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ActivityError('source_redirect_rejected')


def _budget(options: Options, attempts: int, count: int, *, write: bool) -> None:
    """只使用显式已有账本；根／配置变化不清零，损坏失败关闭，无自动初始化。"""
    path = options.budget_ledger
    if path is None:
        raise ActivityError('activity_budget_exhausted')
    checked_path(path)
    before = path.stat()
    if (before.st_dev, before.st_ino) != options.ledger_identity:
        raise ActivityError('activity_budget_invalid')
    fd = os.open(path, (os.O_RDWR if write else os.O_RDONLY) | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        actual = os.fstat(fd)
        if not stat.S_ISREG(actual.st_mode) or actual.st_nlink != 1 or (before.st_dev, before.st_ino) != (actual.st_dev, actual.st_ino):
            raise ActivityError('activity_budget_invalid')
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ActivityError('activity_busy') from error
        raw = os.read(fd, 8193)
        if len(raw) > 8192:
            raise ActivityError('activity_budget_invalid')
        ledger = load(raw)
        if set(ledger) != {'cycle', 'attempts', 'bytes', 'limit_attempts', 'limit_bytes'} or ledger['cycle'] != options.budget_cycle:
            raise ActivityError('activity_budget_invalid')
        if any(type(ledger[k]) is not int or ledger[k] < 0 for k in ('attempts', 'bytes', 'limit_attempts', 'limit_bytes')):
            raise ActivityError('activity_budget_invalid')
        if ledger['attempts'] + attempts > min(options.max_attempts, ledger['limit_attempts']) or ledger['bytes'] + count > min(options.max_bytes, ledger['limit_bytes']):
            raise ActivityError('activity_budget_exhausted')
        if not write:
            return
        ledger['attempts'] += attempts
        ledger['bytes'] += count
        content = canonical(ledger)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, content)
        os.ftruncate(fd, len(content))
        os.fsync(fd)
        checked_path(path)
        if (path.stat().st_dev, path.stat().st_ino) != (actual.st_dev, actual.st_ino):
            raise ActivityError('activity_budget_invalid')
    finally:
        os.close(fd)



def preflight(options: Options, attempts: int, count: int, lease: Lease | None = None) -> None:
    """整批余额预检；不足时零网络，实际扣额仍逐请求持锁执行。"""
    if attempts < 0 or attempts > 2200 or count < 0:
        raise ActivityError('activity_budget_exhausted')
    if lease is not None:
        lease.ensure()
        return
    if attempts:
        _budget(options, attempts, count, write=False)


def reserve(options: Options, limit: int = MAX_BYTES) -> None:
    """按固定来源响应硬限预留，不退款；无来源参数的既有调用仍扣1MiB。"""
    if limit not in (MAX_BYTES, MARKET_MAX_BYTES):
        raise ActivityError('activity_budget_invalid')
    _budget(options, 1, limit, write=True)


def fetch(series: str, dates: list[str], options: Options, cancel: Event, *, lease: Lease | None = None,
          history_batch_paced: bool = False) -> Original:
    """一个官方响应一次请求；403、重定向及超限立即停止，不自动换源或重试。"""
    if not rule(series).admitted:
        raise ActivityError('source_unverified')
    if series in THREE_SOURCE_KEYS:
        from .three_market import daily_url
        if len(dates) != 1:
            raise ActivityError('source_date_mismatch')
        target = daily_url(series.split('-')[0], dates[0])
        limit = MARKET_MAX_BYTES
    else:
        target = market_url(series, dates[0]) if series == "sse" and len(dates) == 1 else url(series, dates)
        limit = MAX_BYTES
    # 仅显式历史工具负责批间等待；日常调用不传此内部参数，仍保持原间隔。
    if type(history_batch_paced) is not bool or (history_batch_paced and (series != 'bse-a-json' or lease is not None)):
        raise ActivityError('invalid_history_pacing')
    if cancel.wait(0 if history_batch_paced else 60 if series == 'bse-a-json' else 1):
        raise ActivityError('activity_cancelled')
    attempt = lease.charge(target, limit) if lease is not None else None
    if lease is None:
        reserve(options, limit)
    success = False
    content = bytearray()
    started = datetime.now(timezone.utc).isoformat()
    deadline = monotonic() + 60
    try:
        with build_opener(NoRedirect()).open(Request(target, headers={'Accept': 'application/json', 'User-Agent': 'TheWolf/0.1', **({'Referer': 'https://www.sse.com.cn/'} if series in ('sse', 'sse-a-json') else {})}), timeout=15) as response:
            if response.status != 200 or response.geturl() != target or response.headers.get_content_type() not in (('text/html', 'application/json') if series == 'bse-a-json' else ('application/json',)):
                raise ActivityError('invalid_source_response')
            content = bytearray()
            while True:
                if cancel.is_set() or monotonic() > deadline:
                    raise ActivityError('activity_cancelled')
                chunk = response.read(min(65536, limit + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
                if len(content) > limit:
                    raise ActivityError('source_size_exceeded')
            success = True
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ActivityError('source_fetch_failed') from error
    finally:
        if lease is not None:
            lease.settle(attempt, len(content) if len(content) <= limit else None, success)
    return Original(rule(series).source, bytes(content), target, started, datetime.now(timezone.utc).isoformat())
