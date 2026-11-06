"""周期更新协调：整批预检、固定窗口、三入口共享账本及失败保旧。"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import logging
import threading
from typing import TYPE_CHECKING
from uuid import uuid4

from pmi.market_data import SnapshotError, ReadUnavailable
from pmi.market_data.activity.model import ActivityError, TWO_MARKET, MARKET_IDS
from pmi.market_data.index_catalog import get_index
from pmi.market_data.index_history_calendar import SHANGHAI, complete_window, from_manifest_window
from pmi.market_data.index_series_contract import source_url
from pmi.market_data.periodic_budget import Budget, BudgetError, Lease, MIB

if TYPE_CHECKING:
    from pmi.market_data import MarketData

_LOGGER = logging.getLogger(__name__)
_SUCCESS = {'already_covered', 'business_changed', 'evidence_changed', 'unchanged'}


class Coordinator:
    """一个服务门面只有一个预算协调器，禁用后不改变旧模式。"""
    def __init__(self, data: MarketData, budget: Budget):
        self.data, self.budget = data, budget
        self.stop = threading.Event()
        self._mutex = threading.RLock()
        self._watchers: list[threading.Thread] = []
        self._revision = 0
        self._state = 'idle'
        self._reason: str | None = None
        self._reason_day: str | None = None
        self._anchor = budget.day()

    def _set(self, state: str, reason: str | None = None) -> None:
        with self._mutex:
            self._revision += 1
            self._state, self._reason = state, reason
            self._reason_day = self.budget.day()

    def _check(self) -> None:
        self.data.check_write_paths()
        if self.stop.is_set():
            raise BudgetError('periodic_stopped')

    def _begin(self, plan, *, target: str, automatic: bool) -> Lease:
        try:
            return self.budget.begin(plan, target=target, automatic=automatic)
        except BudgetError as error:
            if error.code in {'periodic_daily_exhausted', 'periodic_monthly_exhausted'} and (
                    len(plan) > self.budget.options.daily_requests or sum(limit for _, limit in plan) > self.budget.options.daily_bytes):
                self._set('blocked', 'periodic_batch_too_large')
                raise BudgetError('periodic_batch_too_large') from error
            if error.code not in {'periodic_busy', 'periodic_already_attempted'}:
                self._set('blocked', error.code)
            raise

    def _price_plan(self, index_id: str, window) -> list[tuple[str, int]]:
        index = get_index(index_id)
        return [(source_url(index, source, window), MIB) for source in index.sources]

    def _covered(self, index_id: str, window) -> bool:
        value = self.data.read_daily(index_id)
        return bool(value and value['format'] == 'v2' and set(window.dates) <= set(value['snapshot']['calendar_dates']))

    def _update_price(self, code: str, window, lease: Lease, **kwargs) -> dict:
        """将唯一租约和固定窗口传给原更新器；权限与原件校验仍由原路径执行。"""
        lease.ensure()
        self._check()
        return self.data._update(code, _periodic=(self, window, replace(self.data._series_budget, lease=lease)), **kwargs)

    def _finish(self, lease: Lease, reason: str | None) -> None:
        try:
            lease.finish(reason)
        except (OSError, ValueError):
            self._set('blocked', 'periodic_ledger_invalid')
            _LOGGER.exception('周期账本结束失败')
            raise
        self._set('blocked' if reason == 'periodic_unresolved_batch' else 'failed' if reason else 'idle', reason)

    def manual_price(self, code: str, **kwargs) -> dict:
        """手动价格沿用异步job回执，租约直到工作线程结束才释放。"""
        self._check()
        window = complete_window(self.budget.clock())
        lease = self._begin(self._price_plan(code, window), target='price:'+code+':'+window.anchor_date, automatic=False)
        self._set('running')
        try:
            result = self._update_price(code, window, lease, **kwargs)
        except Exception:
            # start_update交接后也可能抛错，先等原worker退出再释放，不能让后续批重用额度。
            self._watch(code, lease)
            raise
        self._watch(code, lease)
        return result

    def _watch(self, code: str, lease: Lease) -> None:
        def wait() -> None:
            reason = 'periodic_unresolved_batch'
            try:
                while not self.data.wait_updates(1):
                    pass
                result = self.data.status(code)
                reason = None if result.get('result') in _SUCCESS else 'periodic_update_failed' if result.get('stage') in {'completed','failed','interrupted'} else 'periodic_unresolved_batch'
            except Exception as error:
                _LOGGER.error('周期任务核对失败 error_type=%s', type(error).__name__)
            finally:
                self._finish(lease, reason)
        worker = threading.Thread(target=wait, name='periodic-price-receipt', daemon=True)
        with self._mutex:
            self._watchers = [x for x in self._watchers if x.is_alive()]
            self._watchers.append(worker)
        worker.start()

    def manual_activity(self, series: str, request_id: str, parameters: dict, config_id: str, instance: str) -> dict:
        """旧量额POST也须先取得整批租约；已有请求只重放，不借新身份重取未决项。"""
        self._check()
        runtime = self.data._activity_runtime
        if series not in runtime.options.write_series:
            raise ActivityError('activity_update_disabled', 403)
        runtime.guard(series)
        with runtime.store.lock(write=False):
            prior = runtime._operation(request_id)
        if prior is not None:
            lease = self._begin([], target='replay:'+series, automatic=False)
            reason = 'periodic_update_failed'
            try:
                result = runtime.start(series, request_id, parameters, config_id, instance, lease=lease)
                reason = None if result['state'] == 'completed' else 'periodic_update_failed'
                return result
            finally:
                self._finish(lease, reason)
        if series in MARKET_IDS:
            window = complete_window(datetime.fromisoformat(parameters['anchor_date']+'T00:00:00+08:00'))
        else:
            window = from_manifest_window(runtime._price(series, parameters['price_snapshot_id']))
        live_window = complete_window(self.budget.clock())
        if series in MARKET_IDS and window.anchor_date != live_window.anchor_date:
            raise ActivityError('invalid_activity_parameters', 422)
        plan = runtime.network_plan(series, window, refresh_missing=True)
        if plan and not set(window.dates) <= set(live_window.dates):
            raise ActivityError('price_binding_unverifiable')
        lease = self._begin(plan, target='activity:'+series+':'+window.anchor_date, automatic=False)
        self._set('running')
        reason = 'periodic_unresolved_batch'
        try:
            result = runtime.start(series, request_id, parameters, config_id, instance, lease=lease)
            reason = None if result['state'] == 'completed' else 'periodic_update_failed'
            return result
        finally:
            self._finish(lease, reason)

    def automatic(self, indices: tuple[str, ...], config_id: str, instance: str) -> bool:
        """启动、07:00及睡眠恢复合并到当天同一目标；无缺日则零来源请求。"""
        lease = None
        reason = None
        try:
            self._check()
            window = complete_window(self.budget.clock())
            runtime = self.data._activity_runtime
            prices = [index for index in indices if not self._covered(index, window)]
            plan = [request for index in prices for request in self._price_plan(index, window)]
            activities = []
            for series in sorted(runtime.options.startup_series, key=lambda x: x == "cn-a-turnover"):
                try:
                    runtime.guard(series)
                    if series in MARKET_IDS:
                        target = window.anchor_date
                        activity_window = window
                    else:
                        view = self.data.read_daily(series)
                        if series not in prices and (not view or view['format'] != 'v2'):
                            continue
                        target = view['snapshot']['snapshot_id'] if view else None
                        activity_window = window if series in prices else from_manifest_window(view['snapshot'])
                    current = runtime.current(series, target) if target else None
                    if series not in prices and current and not current['missing_dates']:
                        continue
                    requests = runtime.network_plan(series, activity_window)
                    if requests and not set(activity_window.dates) <= set(window.dates):
                        reason = 'periodic_update_failed'
                        continue
                    activities.append(series)
                    plan.extend(requests)
                except (ActivityError, SnapshotError, OSError) as error:
                    reason = 'periodic_update_failed'
                    _LOGGER.warning('量额计划不可用，价格独立继续 series=%s error_type=%s', series, type(error).__name__)
            plan = list(dict.fromkeys(plan))
            shared = {}
            lease = self._begin(plan, target='overview:'+window.anchor_date, automatic=True)
            with self._mutex:
                self._anchor = window.anchor_date
            self._set('running')
            for index in prices:
                self._check()
                try:
                    self._update_price(index, window, lease, trigger='startup', only_missing=True)
                    while not self.data.wait_updates(1):
                        if self.stop.is_set():
                            raise BudgetError('periodic_stopped')
                    status = self.data.status(index)
                    if status.get('stage') not in {'completed', 'failed', 'interrupted'}:
                        raise BudgetError('periodic_unresolved_batch')
                    if status.get('result') not in _SUCCESS:
                        reason = 'periodic_update_failed'
                except (SnapshotError, ValueError, OSError) as error:
                    if isinstance(error, OSError) or isinstance(error, BudgetError) and error.code == 'periodic_unresolved_batch':
                        raise BudgetError('periodic_unresolved_batch') from error
                    reason = 'periodic_update_failed'
                    _LOGGER.warning('周期价格更新失败 index=%s error_type=%s', index, type(error).__name__)
            for series in activities:
                self._check()
                try:
                    if series in MARKET_IDS:
                        target, key = window.anchor_date, 'anchor_date'
                    else:
                        value = self.data.read_daily(series)
                        if not value or value['format'] != 'v2':
                            raise ActivityError('price_binding_unverifiable')
                        target, key = value['snapshot']['snapshot_id'], 'price_snapshot_id'
                        # 价格失败时不拿旧P消费为新窗预留的请求，不把未知绑定为新值。
                        if series in prices and not self._covered(series, window):
                            continue
                    current = runtime.current(series, target)
                    if current and not current['missing_dates']:
                        continue
                    result = runtime.start(series, 'periodic-'+uuid4().hex,
                        {key: target, 'expected_activity_id': current['activity_id'] if current else None},
                        config_id, instance, refresh_missing=False, lease=lease, shared=shared)
                    if result['state'] != 'completed':
                        reason = 'periodic_update_failed'
                except (ActivityError, SnapshotError, OSError) as error:
                    if isinstance(error, OSError):
                        raise BudgetError('periodic_unresolved_batch') from error
                    reason = 'periodic_update_failed'
                    _LOGGER.warning('周期量额更新失败 series=%s error_type=%s code=%s', series, type(error).__name__, error.code if isinstance(error, ActivityError) else 'unavailable')
        except BudgetError as error:
            reason = error.code
            if reason not in {'periodic_already_attempted', 'periodic_busy'}:
                self._set('blocked', reason)
        except ReadUnavailable as error:
            # 只把真实共享读锁竞争延后；路径变化/坏库不能当忙碌自动重试。
            if lease is None and isinstance(error.__cause__, BlockingIOError):
                reason = 'periodic_busy'
            else:
                reason = 'periodic_unresolved_batch' if lease is not None else 'periodic_plan_unavailable'
                self._set('blocked', reason)
        except Exception as error:
            _LOGGER.error('周期批次停止 error_type=%s', type(error).__name__)
            reason = 'periodic_unresolved_batch' if lease is not None else 'calendar_uncovered' if str(error) == 'calendar_uncovered' else 'periodic_plan_unavailable'
            self._set('blocked', reason)
        finally:
            if lease is not None:
                # 关闭时也等在途价格结束，避免返还仍可能出站的计划。
                while not self.data.wait_updates(1):
                    pass
                self._finish(lease, reason)
        return reason != 'periodic_busy'

    def status(self) -> dict:
        """纯读控制状态；不执行检查／续期／建账／恢复或金融计算。"""
        self.data.check_location()
        usage = self.budget.status()
        now = self.budget.clock().astimezone(SHANGHAI)
        next_check = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if next_check <= now:
            next_check += timedelta(days=1)
        with self._mutex:
            state, reason, revision, anchor = self._state, self._reason, self._revision, self._anchor
            if self._reason_day and ((reason == 'periodic_daily_exhausted' and usage['day'] > self._reason_day)
                    or (reason == 'periodic_monthly_exhausted' and usage['month'] > self._reason_day[:7])):
                state, reason = 'idle', None
        if usage['active'] and self.budget.active is None:
            state, reason = 'blocked', 'periodic_unresolved_batch'
        try:
            anchor = self.data._activity_runtime.latest_market_anchor(usage['day']) or anchor
        except ActivityError:
            # 量额撤回或正在发布不能使价格状态与共用额度不可读；量额Client仍按原门槛拒绝。
            pass
        last = usage['last_batch']
        if state == 'idle' and last and last['state'] == 'failed':
            state, reason = 'failed', last['reason']
        resume = None
        if reason == 'periodic_daily_exhausted':
            resume = usage['daily_resets_at']
        elif reason == 'periodic_monthly_exhausted':
            resume = usage['monthly_resets_at']
        remaining = usage['active']['remaining'] if usage['active'] else []
        return {'revision': revision, 'state': state, 'reason': reason, 'market_anchor_date': anchor,
                'market_anchors': self.data._activity_runtime.market_anchors(usage['day']),
                'server_day': usage['day'], 'next_check_at': next_check.isoformat(), 'resume_at': resume,
                'daily': usage['daily'], 'monthly': usage['monthly'], 'warning': usage['warning'],
                'reserved': {'requests': len(remaining), 'bytes': sum(x[1] for x in remaining)},
                'daily_resets_at': usage['daily_resets_at'], 'monthly_resets_at': usage['monthly_resets_at']}

    def close(self, timeout: float = 2) -> bool:
        """仅回收本协调器的回执线程；停止信号先由生命周期设置。"""
        with self._mutex:
            workers = tuple(self._watchers)
        for worker in workers:
            worker.join(timeout)
        return not any(worker.is_alive() for worker in workers)
