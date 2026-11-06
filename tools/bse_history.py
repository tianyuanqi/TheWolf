"""BSE-LIVE受控操作辅助：调用前须另获真实读写/联网授权；不是HTTP接口。

调用者提供已批准的Runtime、专属现存暂存目录和独立累计账本。collect只暂存，
publish复用正常发布入口；不改生产配置、不初始化/重置额度、不自动重试。
"""
from datetime import datetime
from dataclasses import replace
from pathlib import Path

from pmi.market_data.activity import fetch, three_market
from pmi.market_data.activity.model import ActivityError, MARKET, MARKET_IDS, MARKET_MAX_BYTES, Original, canonical, digest
from pmi.market_data.activity.store import Store
from pmi.market_data.index_history_calendar import complete_window, SHANGHAI


def _context(runtime, anchor):
    runtime.guard(MARKET)
    if MARKET not in runtime.options.write_series:
        raise ActivityError('activity_update_disabled', 403)
    day = datetime.fromisoformat(anchor+'T00:00:00+08:00')
    if day.date().isoformat() != anchor or day.date() > runtime.clock().astimezone(SHANGHAI).date():
        raise ActivityError('invalid_activity_parameters')
    window = complete_window(day)
    with runtime.store.lock(write=False):
        retained, pending = runtime._market_inputs(MARKET, window, refresh_missing=False)
        bases = {sid: runtime._latest_market_anchor(anchor, sid) for sid in MARKET_IDS}
        references = {sid: runtime.store.current(sid, value)['activity_id'] if value else None for sid, value in bases.items()}
    return window, retained, pending, references


def _validate(item, market, day):
    three_market.original_parts(item, market, day)
    start, end = datetime.fromisoformat(item.started_at), datetime.fromisoformat(item.completed_at)
    if start.utcoffset() is None or end.utcoffset() is None or start > end:
        raise ActivityError('activity_observation_invalid')


class History:
    """私有暂存锁、防重复、每份原件回执；不把未提交缓存供日常接口读取。"""
    def __init__(self, runtime, stage: Path, anchor: str):
        self.runtime, self.stage, self.anchor = runtime, Store(stage), anchor
        if stage == runtime.options.root or stage.is_relative_to(runtime.options.root) or runtime.options.root.is_relative_to(stage):
            raise ValueError('历史暂存与量额根必须分离')

    def _plan(self):
        window, retained, pending, references = _context(self.runtime, self.anchor)
        header = {'version':'bse-history-v1', 'activity_root':str(self.runtime.options.root),
                  'price_root':str(self.runtime.parent._root), 'anchor':self.anchor,
                  'policy':three_market.POLICY, 'references':references,
                  'pending':[[url, market, day] for url, market, day in pending]}
        return window, retained, pending, header

    def prepare(self, research=()):
        """研究原件由调用者先核对固定档案SHA；此处再校验来源、日期、单位和回执。"""
        window, retained, pending, header = self._plan()
        expected = {url:(market,day) for url,market,day in pending}
        with self.stage.lock(write=True):
            previous = self.stage.json('plan.json')
            if previous is not None and previous != header:
                raise ActivityError('history_plan_changed')
            self.stage.write(('plan.json',), canonical(header), immutable=True)
            index = self.stage.json('receipts.json') or {}
            for item in research:
                if item.url not in expected:
                    continue
                market, day = expected[item.url]
                _validate(item,market,day)
                self._save(item,index)
            self.stage.write(('receipts.json',),canonical(index))
            items = self._read(index, expected)
        return {'anchor':self.anchor,'calendar_days':len(set().union(*map(set,three_market.calendars(window).values()))),
                'reused_committed':len(retained),'staged':len(items),'requests':len(pending)-len(items),
                'reserved_bytes':(len(pending)-len(items))*MARKET_MAX_BYTES,
                'urls':[url for url,_,_ in pending if url not in items]}

    def _save(self,item,index):
        record={'source':item.source,'object_id':item.object_id,'url':item.url,
                'started_at':item.started_at,'completed_at':item.completed_at}
        if item.url in index and index[item.url] != record:
            raise ActivityError('history_original_conflict')
        self.stage.write(('raw',item.object_id),item.content,immutable=True)
        index[item.url]=record

    def _read(self,index,expected):
        if not isinstance(index,dict) or not set(index) <= set(expected):
            raise ActivityError('history_stage_invalid')
        result={}
        for url,r in index.items():
            if set(r) != {'source','object_id','url','started_at','completed_at'} or r['url'] != url:
                raise ActivityError('history_stage_invalid')
            from pmi.market_data.activity.model import identifier
            raw=self.stage.read('raw',identifier(r['object_id']),limit=MARKET_MAX_BYTES)
            if raw is None:raise ActivityError('history_stage_invalid')
            item=Original(r['source'],raw,url,r['started_at'],r['completed_at'])
            if item.object_id != r['object_id']:raise ActivityError('history_stage_invalid')
            _validate(item,*expected[url]);result[url]=item
        return result

    def collect(self, progress=lambda result: None, *, bse_batch_pacing: bool = False):
        """整批预检，不足零请求；每次出站先持久扣额，失败停止；成功即原子保存。"""
        _, _, pending, header=self._plan()
        expected={url:(market,day) for url,market,day in pending}
        with self.stage.lock(write=True):
            if self.stage.json('plan.json') != header:raise ActivityError('history_plan_changed')
            index=self.stage.json('receipts.json') or {}
            items=self._read(index,expected)
            remaining=[x for x in pending if x[0] not in items]
            fetch.preflight(self.runtime.options,len(remaining),len(remaining)*MARKET_MAX_BYTES)
            # 请求前落下占位；未完成/失败不得因重启再次尝试同URL。
            attempts=self.stage.json('attempts.json') or {}
            if any(url in attempts for url,_,_ in remaining):raise ActivityError('history_attempt_unresolved')
            if type(bse_batch_pacing) is not bool:raise ActivityError('invalid_history_pacing')
            pace=self.stage.json('pacing.json')
            if bse_batch_pacing:
                if any(market!='bse' for _,market,_ in remaining):raise ActivityError('invalid_history_pacing')
                if pace is None:
                    pace={'version':'bse-history-3s-20x20s-v1','base_saved':len(index)}
                    self.stage.write(('pacing.json',),canonical(pace),immutable=True)
                if (set(pace)!={'version','base_saved'} or pace['version']!='bse-history-3s-20x20s-v1'
                        or type(pace['base_saved']) is not int or not 0<=pace['base_saved']<=len(index)):
                    raise ActivityError('invalid_history_pacing')
            elif pace is not None:raise ActivityError('invalid_history_pacing')
            for url,market,day in remaining:
                # 计数来自已保存回执，重启不重置批边界；重启后完整等待只会更保守。
                completed=len(index)-pace['base_saved'] if pace else 0
                if completed and self.runtime.cancel.wait(20 if completed%20==0 else 3):
                    raise ActivityError('activity_cancelled')
                attempts[url]={'state':'started'};self.stage.write(('attempts.json',),canonical(attempts))
                try:
                    timing={'history_batch_paced':True} if pace else {}
                    item=fetch.fetch(market+'-a-json',[day],self.runtime.options,self.runtime.cancel,**timing)
                    _validate(item,market,day);self._save(item,index)
                    self.stage.write(('receipts.json',),canonical(index))
                    attempts[url]={'state':'saved','object_id':item.object_id}
                    self.stage.write(('attempts.json',),canonical(attempts))
                except Exception:
                    # 保留占位/账本，由人工核对后决定失败URL是否允许一次新尝试。
                    raise
                progress({'saved':len(index),'remaining':len(pending)-len(index),'day':day,'market':market})
        return self.prepare()

    def publish(self, request_id: str):
        """零网络发布；研究/暂存均重放校验，未齐或提交基线变化则不发布。"""
        with self.stage.lock(write=True):
            completed=self.stage.json('published.json')
            plan=self.stage.json('plan.json')
            if plan is None:raise ActivityError('history_stage_invalid')
            if plan['activity_root'] != str(self.runtime.options.root) or plan['price_root'] != str(self.runtime.parent._root) or plan['anchor'] != self.anchor:
                raise ActivityError('history_plan_changed')
            # 提交后、暂存回执落盘前退出：正常操作凭据证明已完成，不重取或重发。
            previous=self.runtime.lookup(MARKET,request_id,digest(plan),'bse-history')
            if completed is not None and completed != previous:raise ActivityError('history_stage_invalid')
            if previous and previous['state']=='completed':completed=previous
            if completed:
                if completed['request_id'] != request_id:raise ActivityError('history_request_mismatch')
                if self.runtime.fixed(MARKET,completed['activity_id']) is None:raise ActivityError('history_stage_invalid')
                return completed
            _, _, pending, header=self._plan()
            if self.stage.json('plan.json') != header:raise ActivityError('history_plan_changed')
            expected={url:(market,day) for url,market,day in pending}
            items=self._read(self.stage.json('receipts.json') or {},expected)
            if set(items) != set(expected):raise ActivityError('history_incomplete')
            # 本次历史补齐不替其他旧任务执行恢复；有未决记录先交回具体处置。
            from pmi.market_data.read_only import checked_path
            operations=checked_path(self.runtime.options.root/'operations')
            with self.runtime.store.lock(write=False):
                if operations.exists():
                    for path in operations.iterdir():
                        op=self.runtime._operation(path.stem)
                        if op and op['state']=='preparing' and op['request_id']!=request_id:
                            raise ActivityError('history_existing_operation_unresolved')
            pointer=self.runtime.store.current(MARKET,self.anchor)
            from pmi.market_data.activity.runtime import Runtime
            offline=Runtime(self.runtime.parent,replace(self.runtime.options,max_attempts=0,max_bytes=0))
            offline.clock=self.runtime.clock
            result=offline.start(MARKET,request_id,{'anchor_date':self.anchor,'expected_activity_id':pointer['activity_id'] if pointer else None},
                                      digest(header),'bse-history',refresh_missing=False,shared=items)
            if result['state'] != 'completed':raise ActivityError(result['reason'] or 'history_publish_failed')
            self.runtime.fixed(MARKET,result['activity_id'])
            self.stage.write(('published.json',),canonical(result),immutable=True)
            return result
