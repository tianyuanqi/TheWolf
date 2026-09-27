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

当前本地项目虚拟环境使用 Python 3.12。新建环境时在仓库根目录执行：

```bash
python3.12 -m venv python/.venv
python/.venv/bin/python -m pip install -r python/requirements.lock
python/.venv/bin/python -m pip install -e python
```

`python/requirements.lock` 记录本机 macOS arm64 / Python 3.12 的受测依赖组合；其他平台仍须验证适用 wheel。

网页开发时可在两个终端分别启动服务和界面：

```bash
WOLF_DATA_ROOT="$PWD/.local-data" python/.venv/bin/python -m uvicorn pmi.api:app --app-dir python/src --host 127.0.0.1 --port 8000
cd apps/desktop && npm run dev
```

桌面开发验证由 Tauri 管理本地 Python 服务，无需先手工启动服务：

```bash
cd apps/desktop && npm run tauri -- dev
```

此命令依赖项目 `python/.venv`，只用于开发。当前 release 产物没有携带 Python 运行时，不能视为可分发安装包。

执行 Python 存储验证：

```bash
PYTHONPATH=python/src python/.venv/bin/python -m unittest discover -s python/tests -v
```

TASK-20260923-01 执行中的源中立存储和受保护 API 可用隔离合成夹具冒烟；此命令只绑定 loopback、自动清理临时数据，不采集真实行情：

```bash
PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/live_service_smoke.py
```

002245 的新浪未复权日线已在固定的 2026-07-03 至 2026-09-24 窗口按深交所官方接口逐日对账，并与 7 月业绩预告、8 月正式半年度报告存入独立的 `.local-data/slice-002245-sina`。旧单公告快照仍可按固定 ID 读取。手动重新获取并校验同一固定窗口的命令如下；新浪底层接口会返回该证券的完整历史响应，但只将目标 60 日标准化发布，原响应完整归档。新浪文档提示多次获取可能封禁 IP，不要频繁运行或设定时任务。

```bash
python/.venv/bin/python -m pmi.sina_slice --data-root "$PWD/.local-data/slice-002245-sina"
```

此命令会核对完整 60 日、深交所同日 OHLC/成交额和成交量舍入范围，以及两份公告 PDF 的固定哈希；失败不更新当前快照。桌面开发窗口默认读取独立的 `.local-data/slice-002245-sina`，也可显式设置 `WOLF_SLICE_DATA_ROOT` 指向另一切片根。受保护 API 会话凭据仅由 Tauri 提供，普通浏览器不能直接查看真实切片。页面分别展示两份公告的本地原件，原始出处按钮调用系统浏览器打开对应的深交所 PDF。无快照时页面显示错误和重试。旧样本接口仍仅作为显式开发夹具，真实切片模式下禁用；合成冒烟不能替代上述真实来源验证。

前端依赖锁定在 [apps/desktop/package-lock.json](apps/desktop/package-lock.json)；Python 依赖声明及本机受测版本分别见 [python/pyproject.toml](python/pyproject.toml)、[python/requirements.lock](python/requirements.lock)。
