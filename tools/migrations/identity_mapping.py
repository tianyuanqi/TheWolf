"""离线旧备份验证的显式身份映射；仅映射摘要输入，绝不重定向文件读取。"""
from contextlib import contextmanager
import hashlib
from pathlib import Path

from read_boundary import BoundaryError, contained


class IdentityMapping:
    def __init__(self, physical_to_logical: dict[str, str]):
        self.roots = dict(physical_to_logical)
        if not self.roots or any(not Path(p).is_absolute() or not Path(q).is_absolute() for p, q in self.roots.items()):
            raise BoundaryError('invalid_identity_mapping')
        if any(contained(p, q) or contained(q, p) for p in self.roots for q in self.roots.values()):
            raise BoundaryError('overlapping_identity_mapping')

    def logical(self, value: str) -> str:
        matches = [(p, q) for p, q in self.roots.items() if contained(value, p)]
        if len(matches) != 1:
            raise BoundaryError('identity_path_not_mapped')
        physical, logical = matches[0]
        return logical + value[len(physical):]

    def physical(self, value: str) -> Path:
        matches = [(p, q) for p, q in self.roots.items() if contained(value, q)]
        if len(matches) != 1:
            raise BoundaryError('legacy_config_path_not_mapped')
        physical, logical = matches[0]
        return Path(physical + value[len(logical):])

    @contextmanager
    def installed(self):
        from pmi.market_data.etf_flow import store, options
        from pmi.market_data import periodic_budget
        old_store, old_options, old_periodic = store.digest, options.digest, periodic_budget.scope_id

        def store_digest(value):
            if isinstance(value, dict) and value.get('format') == 'etf-flow-root-v1':
                value = {**value, 'root': self.logical(value['root'])}
            return old_store(value)

        def options_digest(value):
            if isinstance(value, dict) and value.get('identity') == 'wolf-etf-flow-config-v1':
                value = {**value, 'paths': [self.logical(path) for path in value['paths']]}
            return old_options(value)

        def periodic_scope(root, activity_root):
            old_periodic(root, activity_root)  # 保留对实际副本路径的全部校验。
            return hashlib.sha256(periodic_budget._canonical([
                self.logical(str(root)), self.logical(str(activity_root))])).hexdigest()

        store.digest, options.digest, periodic_budget.scope_id = store_digest, options_digest, periodic_scope
        try:
            yield
        finally:
            store.digest, options.digest, periodic_budget.scope_id = old_store, old_options, old_periodic
