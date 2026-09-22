# Personal Market Intelligence

面向中长期投资者的本地个人市场研究系统。广度放在 A 股市场，深度放在少数重点公司。

协作规则见 [AGENTS.md](AGENTS.md)；当前阶段、授权、进展与下一步统一见 [项目状态](docs/status.md)。

## 设计交付包 · 2026-09-18

建议依次阅读：

1. [PRD V0.1](docs/PRD-V0.1.md)：产品目标、研究流程、页面、范围与验收。
2. [Architecture V0.1](docs/Architecture-V0.1.md)：模块、数据流、运行方式、AI、证据、同步与恢复。
3. [Implementation Plan V0.1](docs/Implementation-Plan-V0.1.md)：版本路线、依赖、开发任务和发布门槛。

架构附录：

- [核心数据模型](docs/Data-Model-V0.1.md)：时间语义、核心 schema、指标口径和存储预算。
- [数据源与验证清单](docs/Data-Sources-V0.1.md)：来源优先级、fallback、调研依据和技术风险。

设计依据为用户提供的项目说明。已明确的投资习惯、A 股为主、日线、单用户、本地优先、150 GB 软上限、证据要求、非交易系统等均作为约束保留。文档中的“建议默认值”是本次提案，可在设计确认时修改。

外部核验限于官方文档和公开页面；没有使用个人数据账户、实测付费接口、批量抓取公告或安装运行依赖。接口权限、完整历史覆盖和分发打包仍须通过计划中的技术验证。

## 最小本地验证

当前工程包含一个可持续扩展的本地验证切片：React 页面经 Vite 开发代理访问 FastAPI；服务将受控样本公司、日线和公告证据元数据写入 SQLite。样本内容只用于验证启动、读取、证据展示和服务重启后的恢复，不代表真实行情或公告来源已经接入。

网页开发时可在两个终端分别启动服务和界面：

```bash
WOLF_DATA_ROOT="$PWD/.local-data" python/.venv/bin/python -m uvicorn pmi.api:app --app-dir python/src --host 127.0.0.1 --port 8000
cd apps/desktop && npm run dev
```

桌面开发验证由 Tauri 管理本地 Python 服务，无需先手工启动服务：

```bash
cd apps/desktop && DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer npm run tauri -- dev
```

此命令依赖项目 `python/.venv`，只用于开发。当前 release 产物没有携带 Python 运行时，不能视为可分发安装包。

执行 Python 存储验证：

```bash
PYTHONPATH=python/src python/.venv/bin/python -m unittest discover -s python/tests -v
```

依赖锁定在 [apps/desktop/package-lock.json](apps/desktop/package-lock.json)。Python 服务依赖在 [python/pyproject.toml](python/pyproject.toml) 声明；首次在新机器安装后可执行 `python/.venv/bin/pip install -e python`。
