"""可信本地ETF配置；文件身份冻结，浏览器不能传入数据根、成员或取数范围。"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .budget import Grant
from .evidence import Evidence
from .model import Configuration, FlowError, decode, digest, identifier
from pmi.market_data.storage.etf_store import Store, location


@dataclass(frozen=True)
class Options:
    root: Path
    configuration_path: Path
    evidence_path: Path
    grant_path: Path | None = None
    write_enabled: bool = False
    refresh_revision: str | None = None

    def __post_init__(self) -> None:
        location(self.root)
        for path in (self.configuration_path, self.evidence_path, self.grant_path):
            if path is not None:
                location(path, directory=False)
                if path == self.root or self.root in path.parents:
                    raise FlowError("etf_config_inside_data_root", 422)
        if type(self.write_enabled) is not bool or self.write_enabled and self.grant_path is None:
            raise FlowError("etf_invalid_options", 422)
        if self.refresh_revision is not None:
            identifier(self.refresh_revision)


class Settings:
    """只读受控文件，当前进程中变更即拒绝；重新连接须使用新可信描述。"""
    def __init__(self, options: Options):
        self.options = options
        self.files: dict[Path, tuple[int, int, bytes, int, int]] = {}
        for path in (options.configuration_path, options.evidence_path, options.grant_path):
            if path is not None:
                location(path, directory=False)
                if path.stat().st_size > 8 * 1024 * 1024:
                    raise FlowError("etf_config_too_large", 422)
                stat = path.stat()
                self.files[path] = (stat.st_dev, stat.st_ino, path.read_bytes(), stat.st_size, stat.st_mtime_ns)
        self.config = Configuration.parse(decode(self.files[options.configuration_path][2]))
        self.evidence = Evidence.parse(decode(self.files[options.evidence_path][2]), {m.id for p in self.config.pools for m in p.members})
        self.grant = Grant.parse(decode(self.files[options.grant_path][2])) if options.grant_path else None
        self.scope = Store(options.root).scope
        self.id = self.identity(options.write_enabled)
        self.check()

    def identity(self, write_enabled: bool) -> str:
        """连接权限进入摘要；只读核验旧终态可明确计算同配置的原启写身份。"""
        return digest({"identity": "wolf-etf-flow-config-v1", "scope": self.scope,
            "configuration": self.config.hash, "evidence": self.evidence.hash,
            "grant": self.grant.hash if self.grant else None, "write_enabled": write_enabled,
            "refresh_revision": self.options.refresh_revision,
            "paths": [str(p) for p in self.files]})

    def check(self) -> None:
        for path, expected in self.files.items():
            location(path, directory=False)
            stat = path.stat()
            if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != (expected[0], expected[1], expected[3], expected[4]):
                raise FlowError("etf_configuration_changed")

    def public(self) -> dict[str, Any]:
        """仅导出摘要；路径、授权原文和内部证据输入不透传页面。"""
        return {"feature_version": "etf-flow-v1", "identity_version": "wolf-etf-flow-config-v1",
                "etf_scope_id": self.scope, "config_id": self.id, "configuration_hash": self.config.hash,
                "evidence_version": self.evidence.version, "write_enabled": self.options.write_enabled,
                "grant_id": self.grant.id if self.grant else None, "refresh_revision": self.options.refresh_revision}
