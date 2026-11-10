"""量额应用服务：受控更新与无副作用读取经公共行情门面调用。"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from threading import Event
import re
from typing import TYPE_CHECKING

from . import fetch, two_market, three_market
from .calculations import calculate
from .facts import index_manifest, market_from_originals
from pmi.market_data.index_history_calendar import from_manifest_window, complete_window, SHANGHAI
from .model import ActivityError, INDEX_IDS, MARKET, MARKET_IDS, TWO_MARKET, MARKET_MAX_BYTES, MARKETS, SERIES, Options, Original, canonical, digest, identifier, rule
from pmi.market_data.storage.activity_store import Store
from contextlib import nullcontext

if TYPE_CHECKING:
    from pmi.market_data import MarketData
    from pmi.market_data.periodic_budget import Lease


class Runtime:
    """只冻结配置；读路径不联网／建库，写路径持独占锁完成单指针提交。"""
    def __init__(self, parent: MarketData, options: Options):
        self.parent, self.options = parent, options
        self.store = Store(options.root)
        self.cancel = Event()
        self.clock = lambda: datetime.now(SHANGHAI)
        self.market_anchor_date = self.clock().date().isoformat()
        self.scope = self.store.scope
        self.blocked = dict(options.blocked_series)
        for evidence_id in self.blocked.values():
            self.store.original(evidence_id)

    def guard(self, series: str, *, evidence: bool = False) -> None:
        if series not in SERIES:
            raise ActivityError('unknown_activity_series', 422)
        self.parent.check_location()
        self.store.check()
        if series in self.blocked and not evidence:
            raise ActivityError('source_withdrawn')

    def _price(self, series: str, target: str) -> dict:
        identifier(target)
        view = self.parent.read_daily(series, target)
        if view is None or view['format'] != 'v2' or view['snapshot']['snapshot_id'] != target:
            raise ActivityError('price_binding_unverifiable')
        return view['snapshot']

    def _fixed(self, series: str, activity_id: str) -> dict | None:
        manifest = self.store.fixed(activity_id)
        if manifest is None:
            return None
        if manifest['series_id'] != series:
            raise ActivityError('activity_identity_mismatch')
        if series not in MARKET_IDS and not rule(series).admitted:
            raise ActivityError('source_unverified')
        # 写入、导入及定期完整检查已重放来源；普通读取只核固定绑定和SQL观察。
        if series not in MARKET_IDS:
            price = self._price(series, manifest['price_snapshot_id'])
            if price['snapshot_id'] != manifest['price_snapshot_id']:
                raise ActivityError('price_binding_unverifiable')
        return {**manifest, 'activity_id': activity_id,
                'observations': self.store.observations(activity_id, manifest)}

    def current(self, series: str, target: str) -> dict | None:
        """仅解析指定价格ID或市场anchor；从不回退到另一快照。"""
        self.guard(series)
        with self.store.lock(write=False):
            pointer = self.store.current(series, target)
            if pointer is None:
                return None
            value = self._fixed(series, pointer['activity_id'])
            if value is None:
                raise ActivityError('activity_replay_mismatch')
            return self._current_value(series, target, pointer, value)

    def _current_value(self, series: str, target: str, pointer: dict, value: dict) -> dict:
        """固定输入与提交观察一致后生成current；调用者须持同一只读锁。"""
        actual_target = value['price_snapshot_id'] or value['anchor_date']
        if actual_target != target or value['series_id'] != series:
            raise ActivityError('activity_identity_mismatch')
        committed = pointer['operation']
        if committed['activity_id'] != value['activity_id'] or committed['target'] != target or committed['series_id'] != series:
            raise ActivityError('activity_identity_mismatch')
        if not any(x['observation_id'] == pointer['observation_id'] == committed['observation_id']
                   and x['request_id'] == committed['request_id'] for x in value['observations']):
            raise ActivityError('activity_observation_invalid')
        return {'series_id': series, 'activity_id': value['activity_id'], 'price_snapshot_id': value['price_snapshot_id'],
                'observation_id': pointer['observation_id'],
                'anchor_date': value['anchor_date'], 'coverage_start': value['calendar_dates'][0],
                'coverage_end': value['calendar_dates'][-1],
                'missing_dates': [r['trade_date'] for r in value['rows'] if any(x['value'] is None for x in ([v for parts in r['components'].values() for v in parts] if series in MARKET_IDS else [r['volume'], r['amount']]))]}

    def view(self, series: str, target: str, version: str) -> dict | None:
        """同次指针与固定输入重放生成完整只读视图，失败不返回局部结果。"""
        from pmi.market_data.compact_view import activity_calculations
        from .calculations import formula_for
        self.guard(series)
        if version != formula_for(series):
            raise ActivityError('calculation_parameters_invalid', 422)
        with self.store.lock(write=False):
            pointer = self.store.current(series, target)
            if pointer is None:
                return None
            snapshot = self._fixed(series, pointer['activity_id'])
            if snapshot is None:
                raise ActivityError('activity_replay_mismatch')
            current = self._current_value(series, target, pointer, snapshot)
            calculations = activity_calculations(snapshot, version)
            self.guard(series)
            return {'current': current, 'snapshot': snapshot, 'calculations': calculations}

    def fixed(self, series: str, activity_id: str) -> dict | None:
        self.guard(series)
        with self.store.lock(write=False):
            return self._fixed(series, activity_id)

    def calculations(self, series: str, activity_id: str, version: str) -> dict | None:
        value = self.fixed(series, activity_id)
        return calculate(value, version) if value else None

    def evidence(self, series: str, activity_id: str, object_id: str) -> dict | None:
        """撤回仍允许读取本活动原件；成员校验，不取任意URL或路径。"""
        import base64
        self.guard(series, evidence=True)
        with self.store.lock(write=False):
            manifest = self.store.fixed(activity_id)
            if manifest is None:
                return None
            if manifest['series_id'] != series:
                raise ActivityError('activity_identity_mismatch')
            member = next((x for x in manifest['sources'] if x['object_id'] == object_id), None)
            if member is None:
                raise ActivityError('activity_evidence_not_found', 404)
            raw = self.store.original(object_id)
            return {'series_id': series, 'activity_id': activity_id, 'price_snapshot_id': manifest['price_snapshot_id'], 'object_id': object_id,
                    'source': member['source'], 'url': member['url'], 'published_at': None,
                    'observations': self.store.observations(activity_id, manifest),
                    'content_base64': base64.b64encode(raw).decode(), 'byte_length': len(raw)}

    def _validate_completed(self, operation: dict) -> None:
        """完成状态必须能由固定输入和对应观察证明，不把丢失凭据标成成功。"""
        if operation['state'] != 'completed':
            return
        manifest = self.store.fixed(operation['activity_id'])
        if manifest is None or manifest['series_id'] != operation['series_id'] or (manifest['price_snapshot_id'] or manifest['anchor_date']) != operation['target']:
            raise ActivityError('activity_operation_mismatch')
        observations = self.store.observations(operation['activity_id'], manifest)
        if not any(x['request_id'] == operation['request_id'] and x['observation_id'] == operation['observation_id'] for x in observations):
            raise ActivityError('activity_observation_invalid')

    def _operation(self, request_id: str) -> dict | None:
        if not isinstance(request_id, str) or re.fullmatch('[a-zA-Z0-9_-]{1,80}', request_id) is None:
            raise ActivityError('invalid_request_id', 422)
        return self.store.json('operations', request_id + '.json')

    def lookup(self, series: str, request_id: str, config_id: str, instance: str) -> dict | None:
        """状态仅属于已验证的系列／配置；读取只报告提交凭据，不写恢复状态。"""
        self.guard(series)
        with self.store.lock(write=False):
            result = self._operation(request_id)
            if result is None:
                return None
            if result['series_id'] != series or result['config_id'] != config_id:
                raise ActivityError('activity_operation_mismatch')
            if result['instance_id'] != instance:
                raise ActivityError('activity_recovery_required')
            if result['state'] == 'preparing':
                pointer = self.store.current(series, result['target'])
                if pointer and pointer['operation']['request_id'] == request_id:
                    if any(pointer['operation'][k] != result[k] for k in ('series_id', 'target', 'signature', 'config_id', 'instance_id')):
                        raise ActivityError('activity_operation_mismatch')
                    result = pointer['operation']
            self._validate_completed(result)
            return result

    def _recover(self) -> None:
        """仅写入口恢复指针提交后的任务记录；其他中断不透明重取数据。"""
        for old in self.store.operations():
            if old['state'] != 'preparing':
                continue
            pointer = self.store.current(old['series_id'], old['target'])
            value = pointer['operation'] if pointer and pointer['operation']['request_id'] == old['request_id'] else {
                **old, 'state': 'interrupted', 'reason': 'activity_interrupted'}
            if any(value[k] != old[k] for k in ('series_id', 'target', 'signature', 'config_id', 'instance_id')):
                raise ActivityError('activity_operation_mismatch')
            self._validate_completed(value)
            self.store.write(('operations', old['request_id'] + '.json'), canonical(value))

    def start(self, series: str, request_id: str, parameters: dict, config_id: str, instance: str, *, refresh_missing: bool = True, lease: Lease | None = None, shared: dict[str, Original | None] | None = None) -> dict:
        """一次显式更新；连接断开不隐式重试，同请求恢复不重置预算或重新联网。"""
        self.guard(series)
        if series not in self.options.write_series:
            raise ActivityError('activity_update_disabled', 403)
        if not rule('bse-a-json' if series == MARKET else 'sse-a-json' if series == TWO_MARKET else series).admitted:
            raise ActivityError('source_unverified')
        self._operation(request_id)
        target_key = 'anchor_date' if series in MARKET_IDS else 'price_snapshot_id'
        if set(parameters) != {target_key, 'expected_activity_id'}:
            raise ActivityError('invalid_activity_parameters', 422)
        target = parameters[target_key]
        if series in MARKET_IDS:
            try:
                anchor = date.fromisoformat(target)
                if anchor > self.clock().astimezone(SHANGHAI).date():
                    raise ValueError()
                window = complete_window(datetime.combine(anchor, datetime.min.time(), SHANGHAI))
            except (ValueError, TypeError) as error:
                raise ActivityError('invalid_activity_parameters', 422) from error
        else:
            identifier(target)
        expected = parameters['expected_activity_id']
        if expected is not None:
            identifier(expected)
        signature = digest({'series': series, 'parameters': parameters})
        with (lease.task.use() if lease else nullcontext()), self.store.lock(write=True, **({"cancel": self.cancel} if lease is not None else {})):
            self._recover()
            previous = self._operation(request_id)
            if previous:
                if previous['config_id'] != config_id or previous['signature'] != signature:
                    raise ActivityError('activity_operation_mismatch')
                self._validate_completed(previous)
                if previous['instance_id'] != instance:
                    previous = {**previous, 'recovered_from_instance': previous['instance_id'], 'instance_id': instance}
                    self.store.write(('operations', request_id + '.json'), canonical(previous))
                return previous
            price = self._price(series, target) if series not in MARKET_IDS else None
            pointer = self.store.json(*self.store.location(series, target))
            target_pointer = self.store.current(series, target)
            # 三市只有一个当前指针；迟到旧目标不能以null CAS替代更新的发布日期。
            if series == MARKET and pointer and pointer['target'] > target:
                raise ActivityError('activity_cas_conflict')
            if (target_pointer['activity_id'] if target_pointer else None) != expected:
                raise ActivityError('activity_cas_conflict')
            operation = {'series_id': series, 'request_id': request_id, 'config_id': config_id, 'instance_id': instance,
                         'target': target, 'signature': signature, 'state': 'preparing', 'activity_id': None, 'reason': None,
                         'recovered_from_instance': None, 'observation_id': None}
            self.store.write(('operations', request_id + '.json'), canonical(operation))
            try:
                if series in MARKET_IDS:
                    obtained = self._obtain_market(series, window, refresh_missing=refresh_missing, lease=lease, shared=shared)
                    manifest = two_market.manifest(window, obtained) if series == TWO_MARKET else three_market.manifest(window, obtained)
                else:
                    obtained = [self._obtain(series, price, lease=lease)]
                    manifest = index_manifest(series, price, obtained[0])
                if self.cancel.is_set():
                    raise ActivityError('activity_cancelled')
                # 在提交前重查固定价格可重放性和定位；不使用变化的current。
                if price is not None and canonical(price) != canonical(self._price(series, target)):
                    raise ActivityError('price_binding_unverifiable')
                activity_id = self.store.publish(manifest, {x.object_id: x.content for x in obtained}, pointer["activity_id"] if pointer else None, operation,
                    {'series_id': series, 'sources': [{'source': x.source, 'object_id': x.object_id, 'url': x.url,
                     'started_at': x.started_at, 'completed_at': x.completed_at, 'published_at': None} for x in obtained]})
                result = self.store.current(series, target)['operation']
            except ActivityError as error:
                result = {**operation, 'state': 'failed', 'reason': error.code}
            # 此处失败时不可谎称回滚：单指针内operation供读取及后续写入口恢复。
            self.store.write(('operations', request_id + '.json'), canonical(result))
            return result

    def _market_inputs(self, series: str, window, *, refresh_missing: bool) -> tuple[dict, list]:
        """仅复用未撤回已提交原件，跨两/三市取最新观察；同时间冲突拒绝。"""
        cal = three_market.calendars(window) if series == MARKET else {m: list(window.dates) for m in ('sse', 'szse')}
        expected = {three_market.daily_url(m, d): (m, d) for m, days in cal.items() for d in days}
        retained, timestamps = {}, {}
        for candidate in MARKET_IDS:
            if candidate in self.blocked:
                continue
            anchor = self._latest_market_anchor(window.anchor_date, candidate)
            if anchor is None:
                continue
            pointer = self.store.current(candidate, anchor)
            previous = self._fixed(candidate, pointer['activity_id'])
            if previous['source_policy_version'] not in (two_market.TWO_POLICY, three_market.POLICY):
                continue
            receipts = {}
            for observation in previous['observations']:
                for receipt in observation['sources']:
                    key = (receipt['object_id'], receipt['url'])
                    if key not in receipts or datetime.fromisoformat(receipt['completed_at']) > datetime.fromisoformat(receipts[key]['completed_at']):
                        receipts[key] = receipt
            missing_urls = {three_market.daily_url(m, row['trade_date']) for row in previous['rows']
                            for m, parts in row['components'].items() if any(x['value'] is None for x in parts)} if refresh_missing else set()
            for source in previous['sources']:
                url = source['url']
                if url not in expected or url in missing_urls:
                    continue
                receipt = receipts.get((source['object_id'], url))
                if receipt is None:
                    raise ActivityError('activity_observation_invalid')
                stamp = datetime.fromisoformat(receipt['completed_at'])
                if url in timestamps:
                    if timestamps[url] > stamp:
                        continue
                    if timestamps[url] == stamp and retained[url].object_id != source['object_id']:
                        raise ActivityError('source_revision_conflict')
                retained[url] = Original(source['source'], self.store.original(source['object_id']), url,
                                         receipt['started_at'], receipt['completed_at'])
                timestamps[url] = stamp
        return retained, [(url, m, d) for url, (m, d) in expected.items() if url not in retained]

    def _two_market_inputs(self, window, *, refresh_missing: bool) -> tuple[dict, list]:
        """保留既有两市内部调用入口。"""
        return self._market_inputs(TWO_MARKET, window, refresh_missing=refresh_missing)

    def network_plan(self, series: str, window, *, refresh_missing: bool = False) -> list[tuple[str, int]]:
        """只读复用证明，返回准确出站URL与硬限；不初始化、恢复或采集。"""
        self.guard(series)
        if series in MARKET_IDS:
            with self.store.lock(write=False):
                _, pending = self._market_inputs(series, window, refresh_missing=refresh_missing)
            return [(target, MARKET_MAX_BYTES) for target, _, _ in pending]
        if series.startswith('sse:'):
            return []
        from .sources import url
        return [(url(series, list(window.dates)), 1048576)]

    def _obtain_market(self, series: str, window, *, refresh_missing: bool, lease: Lease | None = None,
                       shared: dict[str, Original | None] | None = None) -> list[Original]:
        """写锁内核对复用，批内原件只读一次；失败URL不得由另一系列隐式重试。"""
        retained, pending = self._market_inputs(series, window, refresh_missing=refresh_missing)
        shared = shared if shared is not None else {}
        # 即使另一个系列已有旧版，也不得掩盖本批同URL失败或已取得的新版本。
        for url, original in shared.items():
            if url in retained and original is None:
                raise ActivityError('source_fetch_failed')
            if url in retained and original is not None:
                retained[url] = original
        fetch.preflight(self.options, sum(url not in shared for url, _, _ in pending),
                        sum(MARKET_MAX_BYTES for url, _, _ in pending if url not in shared), lease)
        for target, market, day in pending:
            if self.cancel.is_set():
                raise ActivityError('activity_cancelled')
            if target in shared:
                original = shared[target]
                if original is None:
                    raise ActivityError('source_fetch_failed')
            else:
                shared[target] = None
                original = fetch.fetch(market+'-a-json', [day], self.options, self.cancel, **({'lease': lease} if lease is not None else {}))
            three_market.original_parts(original, market, day)
            shared[target] = original
            retained[target] = original
        return list(retained.values())

    def _latest_market_anchor(self, before: str, series: str) -> str | None:
        """三市单指针和两市anchor语义保持，物理索引改由SQL查询。"""
        return self.store.latest_anchor(series, before)

    def latest_market_anchor(self, before: str, series: str = TWO_MARKET) -> str | None:
        """只读该系列实际已发布日期；失败或重连不借另一市场的新日期。"""
        self.guard(series)
        with self.store.lock(write=False):
            return self._latest_market_anchor(before, series)

    def market_anchors(self, before: str) -> dict[str, str | None]:
        """各市场独立失败关闭，量额撤回不剥夺价格状态可读性。"""
        result = {}
        for series in MARKET_IDS:
            try:
                result["sse_szse" if series == TWO_MARKET else "sse_szse_bse"] = self.latest_market_anchor(before, series)
            except ActivityError:
                result["sse_szse" if series == TWO_MARKET else "sse_szse_bse"] = None
        return result

    def startup(self, config_id: str, instance: str) -> list[dict]:
        """serve显式调用一次；集合不从启写推导，每项最多一次，失败不重试。"""
        from uuid import uuid4
        results = []
        shared = {}
        for series in sorted(self.options.startup_series, key=lambda x: x == MARKET):
            if self.cancel.is_set():
                break
            try:
                if series in MARKET_IDS:
                    target = self.market_anchor_date
                    key = 'anchor_date'
                else:
                    price = self.parent.read_daily(series)
                    if price is None or price['format'] != 'v2':
                        raise ActivityError('price_binding_unverifiable')
                    target = price['snapshot']['snapshot_id']
                    key = 'price_snapshot_id'
                current = self.current(series, target)
                if current and not current['missing_dates']:
                    results.append({'series_id': series, 'state': 'already_covered'})
                    continue
                results.append(self.start(series, 'startup-'+str(uuid4()),
                                          {key: target, 'expected_activity_id': current['activity_id'] if current else None},
                                          config_id, instance, refresh_missing=False, shared=shared))
            except ActivityError as error:
                results.append({'series_id': series, 'state': 'failed', 'reason': error.code})
            # 单项失败不剥夺后续显式系列的执行机会；两市无需任何指数P。
            # 不重试失败项；下一项仍单独检查取消、权限、来源和剩余预算。
        return results

    def _obtain(self, series: str, price: dict, *, lease: Lease | None = None) -> Original:
        """中证优先复用P原件；国证严格使用原值接口，决不拿格式化量额补洞。"""
        if series.startswith('sse:'):
            source = price['evidence'][0]
            original = self.parent.read_index_original(series, price['snapshot_id'], source['object_id'])
            # 同一官方对象含量额字段时优先复用；缺字段保持缺值，不为填洞改用另一精度。
            return Original(rule(series).source, original.content, original.url, original.started_at, original.completed_at)
        return fetch.fetch(series, price['calendar_dates'], self.options, self.cancel, **({'lease': lease} if lease is not None else {}))

    def close(self) -> None:
        self.cancel.set()
