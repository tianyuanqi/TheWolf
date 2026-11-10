"""ETF缓存准入在导入/写入时验证；普通计划只读取SQL中的固定证明。"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pmi.market_data.etf_flow.cache import merge
from pmi.market_data.etf_flow.budget import Budget, Grant, Request
from pmi.market_data.etf_flow.calendar import trading_dates
from pmi.market_data.etf_flow.model import Configuration, FlowError, Input, Member, digest, exact, instant
from pmi.market_data.etf_flow.sources import parse, request_for, verify_nav_pages
from pmi.market_data.etf_flow.transport import Original
from .database import Database, StorageError
from .documents import Documents
from .journals import Journals
from .etf_store import Store
from . import state

POLICY = 'etf-cache-source-check-v1'


def member_identity(member: Member) -> dict[str, str]:
    """只绑定解析器实际使用的身份；显示名称/分组变化不废弃同一来源证明。"""
    return {'id': member.id, 'code': member.code, 'exchange': member.exchange}


def proof_key(member: Member, references: list[str]) -> str:
    return 'response-proof:' + digest([POLICY, member_identity(member), sorted(references)])


def verified_result(store: Store, member: Member, requests: tuple[Request, ...], values: list[dict]) -> bool:
    """沿用原解析器与整组NAV约束；完整指纹原件仅在受控验证用例打开。"""
    pages = tuple(parse(member, request, store.get(value['object_id']), value['object_id'], value['retrieved_at'])
                  for request, value in zip(requests, values))
    if requests[0].kind != 'nav':
        return bool(pages[0].rows)
    start, end = requests[0].start, requests[0].end
    if any(page.total != len(trading_dates(start, end)) for page in pages):
        return False
    try:
        missing = verify_nav_pages(pages, start, end)
    except FlowError as error:
        if error.code not in {'etf_source_page_missing', 'etf_source_page_mismatch', 'etf_source_count_mismatch'}:
            raise
        return False
    return not missing


class Cache:
    """统一SQL缓存；沿用配置、字段合并与已验证输入规则。"""

    store: Store

    def __init__(self, store: Store, revision: str | None, config: Configuration):
        self.store, self.revision, self.config = store, revision, config
        self.inputs_key = digest({"format": "etf-flow-input-cache-v1", "scope": store.scope})
        self.configuration_key = digest({"format": "etf-flow-used-configuration-v1", "scope": store.scope})
        self.members = {m.id: m for pool in config.pools for m in pool.members}


    def check_configuration(self, *, required: bool = False) -> str | None:
        """首次快照前也保留已使用配置；只读检查不得为旧缓存补造身份。"""
        reference, value = self.store.journal(self.configuration_key)
        if reference is None:
            if required:
                raise FlowError("etf_cache_configuration_missing")
            self._check_unused_root()
            return None
        value = exact(value, {"configuration_ref"})
        old = Configuration.parse(self.store.get_json(value["configuration_ref"]))
        if not self.config.extends(old):
            raise FlowError("etf_config_history_changed")
        return reference


    def bind_configuration(self) -> None:
        """在缓存/排队写入前追加配置依据；不改写旧版本及已用成员身份。"""
        self.store._require_writer()
        reference = self.check_configuration()
        config_ref = self.store.put_json(self.config.raw)
        _, prior = self.store.journal(self.configuration_key)
        if prior is None or prior["configuration_ref"] != config_ref:
            self.store.write_journal(self.configuration_key, {"configuration_ref": config_ref}, reference)


    def save_inputs(self, incoming: tuple[Input, ...]) -> None:
        self.store._require_writer()
        reference, _ = self.store.journal(self.inputs_key)
        rows = merge(self.inputs(), incoming, "已验证原件缓存；不代表已发布")
        if any(row.member_id not in self.members for row in rows):
            raise FlowError("etf_source_identity_mismatch")
        self.bind_configuration()
        refs = [self.store.put_json(row.raw) for row in rows]
        self.store.write_journal(self.inputs_key, {"input_refs": refs}, reference)


    def response_key(self, request: Request) -> str:
        return digest({"format": "etf-flow-response-cache-v1", "request": request.key, "revision": self.revision})


    def _save_response_reference(self, original: Original, *, replace: bool = False) -> None:
        """调用者先完成字段解析；NAV整组一致性另检查后才进入输入缓存。"""
        key = self.response_key(original.request)
        prior, _ = self.store.journal(key)
        if prior is not None and not replace:
            raise FlowError("etf_response_already_cached")
        self.bind_configuration()
        self.store.write_journal(key, {"request": asdict(original.request), "object_id": original.object_id,
            "retrieved_at": original.retrieved_at, "receipt_id": original.receipt_id}, prior)


    def _check_unused_root(self) -> None:
        if not self.store.initialized:
            return
        if self.store.current_id() is not None:
            raise FlowError('etf_cache_configuration_missing')
        for key in self.store.journal_keys():
            reference, value = self.store.journal(key)
            if not isinstance(value, dict) or value.get('format') != 'etf-flow-budget-v1':
                raise FlowError('etf_cache_configuration_missing')
            budget = Budget(self.store, Grant.parse(value.get('grant')))
            checked, ledger = budget.read()
            if key != budget.key or reference != checked or ledger['attempts']:
                raise FlowError('etf_cache_configuration_missing')

    def inputs(self) -> tuple[Input, ...]:
        reference, value = self.store.journal(self.inputs_key)
        self.check_configuration(required=reference is not None)
        if reference is None:
            return ()
        value = exact(value, {'input_refs'})
        if not isinstance(value['input_refs'], list):
            raise FlowError('etf_invalid_cache')
        values = self.store.get_many(value['input_refs'])
        rows = tuple(Input.parse(values[ref]) for ref in value['input_refs'])
        if len({(row.member_id, row.date) for row in rows}) != len(rows):
            raise FlowError('etf_invalid_cache')
        if any(row.member_id not in self.members for row in rows):
            raise FlowError('etf_source_identity_mismatch')
        return rows

    def response(self, request: Request) -> dict[str, Any] | None:
        reference, value = self.store.journal(self.response_key(request))
        if reference is None:
            return None
        self.check_configuration(required=True)
        value = exact(value, {'request', 'object_id', 'retrieved_at', 'receipt_id'})
        if value['request'] != asdict(request):
            raise FlowError('etf_invalid_cache')
        receipt = self.store.get_json(value['receipt_id'])
        if receipt.get('object_id') != value['object_id'] or receipt.get('request_key') != request.key or receipt.get('code') is not None:
            raise FlowError('etf_invalid_cache')
        instant(value['retrieved_at'])
        with self.store.database.read() as connection:
            if connection.execute('SELECT 1 FROM original_object WHERE id=?', (value['object_id'],)).fetchone() is None:
                raise FlowError('etf_invalid_cache')
        return value

    def reusable_response(self, request: Request) -> dict[str, Any] | None:
        if request.kind == 'nav':
            member = self.members.get(request.member_id)
            if member is None:
                raise FlowError('etf_source_identity_mismatch')
            count = len(trading_dates(request.start, request.end))
            requests = tuple(request_for(member, 'nav', request.start, request.end, page=n)
                             for n in range(1, (count + 19) // 20 + 1))
        else:
            requests = (request,)
        return self.reusable_responses(requests).get(request.key)

    def reusable_responses(self, requests: tuple[Request, ...]) -> dict[str, dict[str, Any] | None]:
        """整组指纹与准入证明一一对应；更换任一页不得沿用旧准入。"""
        result = {request.key: None for request in requests}
        groups: dict[tuple[str, str, str, str], list[Request]] = {}
        for request in requests:
            group = (request.member_id, request.start, request.end, 'nav' if request.kind == 'nav' else request.key)
            groups.setdefault(group, []).append(request)
        for (member_id, _, _, _), group in groups.items():
            member = self.members.get(member_id)
            if member is None:
                raise FlowError('etf_source_identity_mismatch')
            values = [self.response(request) for request in group]
            if any(value is None for value in values):
                continue
            references = [self.store.journal(self.response_key(request))[0] for request in group]
            with self.store.database.read() as connection:
                proof = state.read(connection, 'etf', proof_key(member, references))
            if proof is None:
                raise FlowError('etf_cache_verification_required')
            if (proof['policy'] != POLICY or proof['member_identity'] != member_identity(member)
                    or proof['references'] != sorted(references) or type(proof['reusable']) is not bool):
                raise FlowError('etf_invalid_cache')
            if proof['reusable']:
                result.update((request.key, value) for request, value in zip(group, values))
        return result

    def save_response(self, original, *, replace: bool = False) -> None:
        """保存响应后检查其整组；尚缺页时不生成完整准入证明。"""
        with self.store.database.transaction():
            self._save_response(original, replace=replace)

    def _save_response(self, original, *, replace: bool) -> None:
        self._save_response_reference(original, replace=replace)
        request = original.request
        member = self.members.get(request.member_id)
        if member is None:
            raise FlowError('etf_source_identity_mismatch')
        if request.kind == 'nav':
            count = len(trading_dates(request.start, request.end))
            requests = tuple(request_for(member, 'nav', request.start, request.end, page=n)
                             for n in range(1, (count + 19) // 20 + 1))
        else:
            requests = (request,)
        values = [self.response(item) for item in requests]
        if any(value is None for value in values):
            return
        refs = [self.store.journal(self.response_key(item))[0] for item in requests]
        save_proof(self.store, member, requests, values, refs)


def save_proof(store: Store, member: Member, requests: tuple[Request, ...], values: list[dict], references: list[str]) -> None:
    store._require_writer()
    reusable = verified_result(store, member, requests, values)
    proof = {'policy': POLICY, 'member_identity': member_identity(member), 'member': asdict(member),
             'references': sorted(references), 'reusable': reusable}
    with store.database.transaction() as connection:
        state.write(connection, 'etf', proof_key(member, references), proof, immutable=True)


def import_proofs(database: Database, connection) -> dict[str, int]:
    """导入后首次建立全部当前缓存证明；无法区分的重复修订不猜测分组。"""
    from pmi.market_data.etf_flow.model import Configuration
    store = Store(database.root)
    docs, journals = Documents(connection), Journals(connection, 'etf')
    key = digest({'format': 'etf-flow-used-configuration-v1', 'scope': store.scope})
    _, binding = journals.read(key)
    if binding is None:
        if journals.keys():
            raise StorageError('storage_cache_configuration_missing')
        return {'groups': 0, 'responses': 0}
    config = Configuration.parse(docs.get(binding['configuration_ref']))
    members = {member.id: member for pool in config.pools for member in pool.members}
    groups = {}
    for key in journals.keys():
        revision, value = journals.read(key)
        if not isinstance(value, dict) or set(value) != {'request', 'object_id', 'retrieved_at', 'receipt_id'}:
            continue
        request = Request(**value['request'])
        receipt = docs.get(value['receipt_id'])
        if receipt.get('object_id') != value['object_id'] or receipt.get('request_key') != request.key or receipt.get('code') is not None:
            raise StorageError('storage_cache_receipt_invalid')
        instant(value['retrieved_at'])
        group = (request.member_id, request.start, request.end, 'nav' if request.kind == 'nav' else revision)
        groups.setdefault(group, []).append((request, value, revision))
    responses = 0
    for (member_id, _, _, _), entries in groups.items():
        requests = tuple(item[0] for item in entries)
        if len({request.key for request in requests}) != len(requests):
            raise StorageError('storage_cache_revision_ambiguous')
        if member_id not in members:
            raise StorageError('storage_cache_member_missing')
        # 原接口的NAV核验依赖页序；不能将journal hash字典序误当成页序。
        from urllib.parse import parse_qs, urlsplit
        entries.sort(key=lambda item: int(parse_qs(urlsplit(item[0].url).query).get('pageIndex', ['1'])[0]))
        save_proof(store, members[member_id], tuple(item[0] for item in entries),
                   [item[1] for item in entries], [item[2] for item in entries])
        responses += len(entries)
    return {'groups': len(groups), 'responses': responses}


def verify_proofs(database: Database, connection) -> None:
    """定期完整检查重放每份保存的准入；失败不能只让某次页面查询绕过。"""
    store, docs = Store(database.root), Documents(connection)
    for row in connection.execute("SELECT key,revision FROM state WHERE domain_id='etf' AND key LIKE 'response-proof:%'"):
        proof = docs.get(row['revision'])
        member = Member.parse(proof['member'])
        if row['key'] != proof_key(member, proof['references']) or proof['policy'] != POLICY or proof['member_identity'] != member_identity(member):
            raise StorageError('storage_cache_proof_invalid')
        values = []
        for reference in proof['references']:
            value = Journals(connection, 'etf').wrapper(reference)['value']
            request = Request(**value['request'])
            receipt = docs.get(value['receipt_id'])
            if receipt.get('object_id') != value['object_id'] or receipt.get('request_key') != request.key or receipt.get('code') is not None:
                raise StorageError('storage_cache_receipt_invalid')
            values.append((request, value))
        from urllib.parse import parse_qs, urlsplit
        values.sort(key=lambda item: int(parse_qs(urlsplit(item[0].url).query).get('pageIndex', ['1'])[0]))
        actual = verified_result(store, member, tuple(item[0] for item in values), [item[1] for item in values])
        if actual != proof['reusable']:
            raise StorageError('storage_cache_proof_invalid')
    # 不能只重放仍然存在的证明；完整的当前响应组丢失证明也必须报告损坏。
    from pmi.market_data.etf_flow.model import Configuration
    journals = Journals(connection, 'etf')
    _, binding = journals.read(digest({'format': 'etf-flow-used-configuration-v1', 'scope': store.scope}))
    if binding is None:
        return
    config = Configuration.parse(docs.get(binding['configuration_ref']))
    members = {member.id: member for pool in config.pools for member in pool.members}
    groups = {}
    for key in journals.keys():
        reference, value = journals.read(key)
        if isinstance(value, dict) and set(value) == {'request', 'object_id', 'retrieved_at', 'receipt_id'}:
            request = Request(**value['request'])
            group = (request.member_id, request.start, request.end, 'nav' if request.kind == 'nav' else request.key)
            groups.setdefault(group, []).append((request, reference))
    for (member_id, start, end, kind), entries in groups.items():
        if member_id not in members:
            raise StorageError('storage_cache_member_missing')
        member = members[member_id]
        if kind == 'nav':
            pages = (len(trading_dates(start, end)) + 19) // 20
            expected = {request_for(member, 'nav', start, end, page=page).key for page in range(1, pages + 1)}
            if {request.key for request, _ in entries} != expected:
                continue
        if state.read(connection, 'etf', proof_key(member, [ref for _, ref in entries])) is None:
            raise StorageError('storage_cache_proof_missing')
