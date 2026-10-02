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

上述 2026-09-18 设计包当时只核验了官方文档与公开页面。其后已完成本页下述 002245 真实切片和本地环境验证；完整历史覆盖、其他来源权限及分发打包仍待验证，进展以 [项目状态](docs/status.md) 为准。

## 最小本地验证

当前桌面页读取已归档的 002245 新浪未复权日线和两份深交所公告。早期 SQLite 样本仍保留为服务端开发夹具；样本 API 仅用于独立调试，不会出现在真实切片页面。

当前本地项目虚拟环境使用 Python 3.12。新建环境时在仓库根目录执行：

```bash
python3.12 -m venv python/.venv
python/.venv/bin/python -m pip install -r python/requirements.lock
python/.venv/bin/python -m pip install -e python
```

`python/requirements.lock` 记录本机 macOS arm64 / Python 3.12 的受测依赖组合；其他平台仍须验证适用 wheel。

只调试旧样本 API 时，可单独启动服务；普通浏览器中的页面不会显示受保护的真实切片：

```bash
WOLF_DATA_ROOT="$PWD/.local-data" python/.venv/bin/python -m uvicorn pmi.api:app --app-dir python/src --host 127.0.0.1 --port 8000
```

真实切片页面须用 Tauri 桌面开发窗口；它管理本地 Python 服务和会话凭据，无需先手工启动服务：

```bash
cd apps/desktop && npm run tauri -- dev
```

此命令依赖项目 `python/.venv`，默认占用本机 8000/5173 端口。同一配置只保留一个桌面进程；再次打开会唤起已有窗口。验证时复用该窗口，退出后再启动下一轮；端口仍被占用时先查明并退出占用者，再点“重试启动并读取”。当前 release 产物没有携带 Python 运行时，不能视为可分发安装包。

确需并行验证时，先准备各自的隔离数据目录，再为每个会话指定不同的前端及服务端口。以下脚本生成对应的临时 Tauri 配置与独立应用标识，不修改默认配置或已有数据：

```bash
python/.venv/bin/python apps/desktop/scripts/run_qa.py \
  --frontend-port 5174 --service-port 8001 --data-root /tmp/thewolf-qa-data
```

`--data-root` 必须指向已存在的隔离目录，且不能是项目原始 `.local-data`。脚本也为每组端口使用独立的 Cargo 构建目录，避免并行热重载互相覆盖可执行文件。任一端口已被占用时会停止启动并提示复用旧窗口或换端口；退出验证会话后，应确认两个端口均已释放。不要让不同会话共用同一数据目录。

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

此命令会核对完整 60 日、深交所同日 OHLC/成交额和成交量舍入范围，以及两份公告 PDF 的固定哈希；失败不更新当前快照。今后每份在线原件完整读取后会在数据根追加 `original-observations.jsonl`，记录原件哈希与各自的获取完成时刻；旧批次没有此日志，不能据批次时刻反推逐原件时间。桌面开发窗口默认读取独立的 `.local-data/slice-002245-sina`，也可显式设置 `WOLF_SLICE_DATA_ROOT` 指向另一切片根。受保护 API 会话凭据仅由 Tauri 提供，普通浏览器不能直接查看真实切片。页面分别展示两份公告的本地原件，原始出处按钮调用系统浏览器打开对应的深交所 PDF。无快照时页面显示错误和重试。旧样本接口仍仅作为显式开发夹具，真实切片模式下禁用；合成冒烟不能替代上述真实来源验证。

前端依赖锁定在 [apps/desktop/package-lock.json](apps/desktop/package-lock.json)；Python 依赖声明及本机受测版本分别见 [python/pyproject.toml](python/pyproject.toml)、[python/requirements.lock](python/requirements.lock)。

### 日线手动更新（隔离根）

在已准备两份公告的隔离根使用上方 `run_qa.py` 启动桌面，点击“更新日线”。QA 入口显式启用 `WOLF_ENABLE_DATA_UPDATE=1`；默认桌面服务不启用写入，原库切换须另行授权和完成一致性备份/恢复验证。空库先准备切片，不能用更新按钮发现或补下载公告。

更新只采集 002245 新浪未复权日线及深交所对照，按[官方日历](python/src/pmi/trading_calendar.py)展示最近 60 个完整开市日，不含上海时区当日。当前日历覆盖 2026 年，覆盖外或不足 60 日拒绝更新。旧快照和两份 PDF 保留，失败可继续离线阅读。每源一次请求、无自动重试，单源 45 秒硬截止，连接/读取超时 5/15 秒，原响应上限 1 MB；不会自动定时采集。客户端超时先“核对结果”，该操作只查询本地任务。

受保护接口为 `POST /api/slice/update`（空 JSON 对象）和 `GET /api/slice/update`。服务端固定证券、URL、时间与数据根；POST 禁止额外字段和查询参数。文件锁协调 CLI 与服务，启动时以本地观察索引核对未完成任务。

V-FE 的延迟 PDF 响应专项：在 `apps/desktop` 运行 `node --test scripts/evidence_read.test.mjs`，退出 0 验证旧快照响应不展示、新响应可读；无外部网络，临时模块自动清理。

V-PY 自动包含 `test_data_update` 与 API 更新反例。V-MIG 的新增旧代码合成库专项入口：从仓库根先导出真实旧版存储模块，再执行；脚本只使用自动清理的临时数据根，不联网、不写原库。

```bash
git show c39ee17514746e41b213b959f9a84417f0d61342:python/src/pmi/snapshot.py > /tmp/thewolf-legacy-snapshot.py
PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/legacy_update_smoke.py --legacy-snapshot /tmp/thewolf-legacy-snapshot.py
```

退出 0 且输出 `legacy code A/B same-time ... PASS` 表示旧代码建库、同刻重试、更新中断、固定视图及备份恢复断言通过。不存在旧提交/源码时记录材料缺失，不能用当前代码建库冒充。实际真实来源、桌面及原库切换证据仍须按任务单独核对。
