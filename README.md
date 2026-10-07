# TheWolf

面向个人中长线投资者的本地研究工作台：提供 A 股与港股市场、行情、公司及资料看板，并围绕投资论点记录研究依据、决定及后续复核。默认入口为收盘后使用的市场总览，海外与商品序列提供外部环境。

2026-10-04 已确认的产品范围见 [PRD](docs/PRD-V0.1.md)，交付顺序见 [路线图](docs/Implementation-Plan-V0.1.md)：先完成第一批市场与指标看板，再做论点—决策—复核闭环。当前可运行能力仍是下方单股日线与两份公告切片；新方向不表示上述功能已经实现。

协作规则见 [AGENTS.md](AGENTS.md)；当前阶段、授权、进展与下一步统一见 [项目状态](docs/status.md)。

## 验证入口

本节是当前验证命令的统一索引；按 [Task-Workflow 第 10 节](docs/Task-Workflow.md#10-稳定验证入口与证据)选取适用项，不要求每次全部执行。下列路径相对仓库根目录，工作目录另列；从固定导出验证时，路径应指向该导出，解释器可复用已核对的本地环境，源码导入必须固定到被测版本。

环境：Python 命令使用项目 `python/.venv`（当前受测组合为 macOS arm64 / Python 3.12，准备方式见下文）；前端需已安装锁文件对应依赖和 Node/npm；Rust 需工具链及本机 Tauri SDK，`--offline` 还需缓存依赖齐备。缺失时记录阻塞并按任务授权处理，不把环境失败算作业务断言失败。回环冒烟需要本机 socket 权限。

| ID / 范围 | 工作目录 | 实际入口 | 结果信号与边界 |
|---|---|---|---|
| V-DOC 文档 | 仓库根 | `git diff --check`；有暂存内容时另执行 `git diff --cached --check` | 退出 0 仅说明对应差异空白检查通过；另检查本轮全部候选 Markdown 的本地链接/锚点、围栏和引用，含未跟踪文件。当前无统一纳管 Markdown 检查器，须记录所用方法 |
| V-PY Python | 仓库根 | `PYTHONPATH=python/src:python/tests python/.venv/bin/python -m unittest discover -s python/tests -v` | 测试退出 0 且无失败；合成夹具与临时数据，覆盖范围以实际测试为准，不代表真实来源或原库迁移通过 |
| V-API 实际回环 API | 仓库根 | `PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/live_service_smoke.py` | 临时合成快照；health/snapshot/PDF 200、缺凭据 401、退出后端口关闭；不验证原生 UI |
| V-FE 前端 | `apps/desktop` | `npm run build` | `package.json` 实际执行 `tsc -b` 和 Vite 构建；退出 0，产物为构建输出，不代替 UI 检查 |
| V-RUST 桌面 Rust | `apps/desktop/src-tauri` | `cargo fmt --check`、`cargo check --locked --offline`、`cargo test --locked --offline`（按改动选择，分别记录结果） | 格式/编译/生命周期单测各有结果；会生成本地构建产物，不证明分发包可用 |
| V-LIFE 父进程退出 | 仓库根 | `PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/service_parent_smoke.py` | 临时隔离根与动态回环端口；父管道关闭后子服务退出、端口释放；不等同全部原生关闭路径 |
| V-UI 原生界面 | 仓库根 | [桌面隔离验证](#桌面隔离验证)中的 `run_qa.py` | 需要预先准备独立数据根；按任务操作检查加载/错误/恢复、受影响按钮、窗口及键盘路径，记录实测或用户反馈，退出后核对本次端口/进程 |
| V-MIG 存储与迁移 | 仓库根或固定隔离导出 | V-PY 中 `test_snapshot`、`test_sina_slice` 的适用测试；旧代码建库和完整适配器专项复现参考[已归档报告 §12](docs/test-reports/TASK-20260927-01-review.md#12-文档归档与临时证据重建--2026-09-29) | 检查旧固定视图、观察顺序、失败恢复；单元夹具不能代替真实旧版本建库的兼容验证。报告探针固定于其中 SHA，新任务须核对/适配目标版本；需真实原件时核对外部副本哈希，缺失如实记录 |

V-PY 可按影响选择模块，例如仅存储/适配器回归时，从仓库根运行：

```bash
PYTHONPATH=python/src:python/tests python/.venv/bin/python -m unittest test_snapshot test_sina_slice -v
```

选择子集时说明覆盖理由；修改公共基础、依赖或影响难以限定时运行全套。无论脚本是否正常退出，都按 [Task-Workflow 第 10.3 节](docs/Task-Workflow.md#103-测试结束后的配置与状态恢复)核验临时服务/数据清理及配置、代理、数据指向和应用状态恢复，不停止其他会话的服务。运行结果与恢复情况按 Task-Workflow 第 7/10 节记录，README 不维护实时通过状态。

以上入口在 2026-09-30 按现有源码、配置和脚本静态核对；既往运行证据见[评审报告](docs/test-reports/TASK-20260927-01-review.md)。本轮整理没有重新执行业务测试。文档检查器、通用旧库迁移测试入口仍有工具化空间，不能宣称已有统一脚本。

## 产品与设计文档

文档沿用原路径，2026-10-04 按方向讨论稿 v0.4 及后续确认修订；文件名 V0.1 和讨论稿 v0.4 都不能视为软件交付状态。

建议依次阅读：

1. [PRD V0.1](docs/PRD-V0.1.md)：产品目标、研究流程、页面、范围与验收。
2. [Architecture V0.1](docs/Architecture-V0.1.md)：模块、数据流、运行方式、AI、证据、同步与恢复。
3. [总体方向与分步开发计划 V0.1](docs/Implementation-Plan-V0.1.md)：后续开发的统一计划入口，包含 PLAN-P01/P02、M01–M08、R01–R03 的目标、依赖、交付物与完成条件；具体任务须关联相应步骤，计划本身不授权执行。

架构附录：

- [核心数据模型](docs/Data-Model-V0.1.md)：时间语义、核心 schema、指标口径和存储预算。
- [数据源与验证清单](docs/Data-Sources-V0.1.md)：来源优先级、fallback、调研依据和技术风险。

已确认范围包括 A 股与港股主要指数、少量长期公共序列、重点证券、首批七组指标和后续论点闭环。日线级别、历史最终至少五年、默认不滚动删除、取消自选保留历史、150 GB 软上限与证据/时间正确性分别落实到需求和数据文档；具体序列、视觉、更新触发及历史能力仍有待设计或验证的部分。

架构和数据模型包含演进候选，不能据表或目录存在认定已实现。旧路线完整保留作历史参考，旧任务书与审查结论不追溯改写；当前实现、授权和验证统一见项目状态。文档修订不启动开发任务、批量采集或数据库迁移。

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

日常使用从以下入口打开Tauri桌面窗口；它管理本地Python服务和会话凭据，无需先手工启动服务或设置数据环境变量：

```bash
cd apps/desktop && npm start
```

日常入口固定读取`.local-data/slice-002245-sina`，启用002245“更新日线”和沪深300“检查更新”，显式设置两个独立写开关为1，覆盖父环境中的关闭值。启动只读取本地快照，不请求行情来源、不复制测试库、不提前迁移；用户主动点击后才获取/校验/发布。首次指数采集由用户点击“检查更新”触发，结果保存到正式父根下的`indices/csi000300`。旧结构在首次成功发布事务中按已验证路径追加观察索引，旧快照和公告保留；首次启用前的一致性备份与恢复证据见[当前状态](docs/status.md)。独立QA入口仍只操作指定隔离根。

需要只读开发窗口时使用以下入口；默认不启用更新，显式传入`WOLF_ENABLE_DATA_UPDATE=0 WOLF_ENABLE_INDEX_UPDATE=0`可关闭两个独立写开关。这是`npm run tauri -- dev`入口的配置；日常`npm start`按上述约定启用手动更新：

```bash
cd apps/desktop && npm run tauri -- dev
```

此命令依赖项目 `python/.venv`，默认占用本机 8000/5173 端口。同一配置只保留一个桌面进程；再次打开会唤起已有窗口。验证时复用该窗口，退出后再启动下一轮；端口仍被占用时先查明并退出占用者，再点“重试启动并读取”。当前 release 产物没有携带 Python 运行时，不能视为可分发安装包。

### 桌面隔离验证

先准备本次验证的隔离数据目录；确需并行验证时，为每个会话指定不同的前端及服务端口。以下脚本生成对应的临时 Tauri 配置与独立应用标识，不修改默认配置或已有数据；从仓库根目录执行：

```bash
python/.venv/bin/python apps/desktop/scripts/run_qa.py \
  --frontend-port 5174 --service-port 8001 --data-root /tmp/thewolf-qa-data
```

`--data-root` 必须指向已存在的隔离目录，且不能是项目原始 `.local-data`。脚本也为每组端口使用独立的 Cargo 构建目录，避免并行热重载互相覆盖可执行文件。任一端口已被占用时会停止启动并提示复用旧窗口或换端口；退出验证会话后，应确认两个端口均已释放。不要让不同会话共用同一数据目录。

Python 测试和隔离回环冒烟统一见上方[验证入口](#验证入口) V-PY/V-API。

### 手动真实来源采集

以下是会请求外部来源并写入真实数据根的业务操作，不属于默认验证入口；执行前核对当前授权，涉及旧库升级时先落实一致性备份与恢复方案。

002245 的新浪未复权日线已在固定的 2026-07-03 至 2026-09-24 窗口按深交所官方接口逐日对账，并与 7 月业绩预告、8 月正式半年度报告存入独立的 `.local-data/slice-002245-sina`。旧单公告快照仍可按固定 ID 读取。手动重新获取并校验同一固定窗口的命令如下；新浪底层接口会返回该证券的完整历史响应，但只将目标 60 日标准化发布，原响应完整归档。新浪文档提示多次获取可能封禁 IP，不要频繁运行或设定时任务。

```bash
python/.venv/bin/python -m pmi.sina_slice --data-root "$PWD/.local-data/slice-002245-sina"
```

此命令会核对完整 60 日、深交所同日 OHLC/成交额和成交量舍入范围，以及两份公告 PDF 的固定哈希；失败不更新当前快照。今后每份在线原件完整读取后会在数据根追加 `original-observations.jsonl`，记录原件哈希与各自的获取完成时刻；旧批次没有此日志，不能据批次时刻反推逐原件时间。桌面开发窗口默认读取独立的 `.local-data/slice-002245-sina`，也可显式设置 `WOLF_SLICE_DATA_ROOT` 指向另一切片根。受保护 API 会话凭据仅由 Tauri 提供，普通浏览器不能直接查看真实切片。页面分别展示两份公告的本地原件，原始出处按钮调用系统浏览器打开对应的深交所 PDF。无快照时页面显示错误和重试。旧样本接口仍仅作为显式开发夹具，真实切片模式下禁用；合成冒烟不能替代上述真实来源验证。

前端依赖锁定在 [apps/desktop/package-lock.json](apps/desktop/package-lock.json)；Python 依赖声明及本机受测版本分别见 [python/pyproject.toml](python/pyproject.toml)、[python/requirements.lock](python/requirements.lock)。

### 日线手动更新（隔离根）

在已准备两份公告的隔离根使用上方 `run_qa.py` 启动桌面，点击“更新日线”。QA入口显式启用`WOLF_ENABLE_DATA_UPDATE=1`；只读开发入口默认不启用写入，日常`npm start`入口启用正式库手动更新。空库先准备切片，不能用更新按钮发现或补下载公告。

更新只采集 002245 新浪未复权日线及深交所对照，按[官方日历](python/src/pmi/trading_calendar.py)展示最近 60 个完整开市日，不含上海时区当日。当前日历覆盖 2026 年，覆盖外或不足 60 日拒绝更新。旧快照和两份 PDF 保留，失败可继续离线阅读。每源一次请求、无自动重试，单源 45 秒硬截止，连接/读取超时 5/15 秒，原响应上限 1 MB；不会自动定时采集。客户端超时先“核对结果”，该操作只查询本地任务。

受保护接口为 `POST /api/slice/update`（空 JSON 对象）和 `GET /api/slice/update`。服务端固定证券、URL、时间与数据根；POST 禁止额外字段和查询参数。文件锁协调 CLI 与服务，启动时以本地观察索引核对未完成任务。

V-FE 的延迟 PDF 响应专项：在 `apps/desktop` 运行 `node --test scripts/evidence_read.test.mjs`，退出 0 验证旧快照响应不展示、body读取中卸载后不遗留对象URL、已有PDF卸载/关闭/选择切换回收，以及新响应仍可读；使用真实Blob URL，网络全部隔离替代，临时模块与对象URL在测试结束时清理。

V-FE 的真实React PDF资源专项：使用已有浏览器测试运行时，设置 `WOLF_PLAYWRIGHT_MODULE` 为其Playwright包的绝对目录，在 `apps/desktop` 运行 `node --test scripts/pdf_ownership.test.mjs`。退出0验证URL已接受但状态尚未提交时的普通导航/关闭、替换原件及StrictMode；标准浏览器Blob URL实际读回确认撤销，所有外部路由阻断，浏览器/上下文和夹具URL在结束或失败时清理。入口使用既有Vite/React，不安装依赖；可通过桌面 `load_workspace_dependencies` 获取已配置运行时路径。此项合成时序测试不代替真实PDF原生阅读验证。

V-FE 的更新恢复专项：在 `apps/desktop` 运行 `node --test scripts/update_recovery.test.cjs`，退出 0 验证真实 LegacySliceView 回调在请求未送达、响应丢失、拒绝和查询失败时的恢复；只替代 React 调度、时钟及网络，无真实数据写入或外部请求。请求结果不确定时先进行约 120 秒的有界核对；之后人工“核对结果”若成功读到相同旧闲置/终态，明确提示未发现新任务并恢复手动更新入口，不自动重发，也不把旧完成结果当作本次成功。运行中或查询失败继续保守核对；原生界面仍须按 V-UI 验证。

V-FE的日常启动入口专项：在`apps/desktop`运行`node --test scripts/start_daily.test.mjs`，以临时npm替身核对父环境指数开关0被覆盖为1、固定正式根/端口/构建目录、不增加采集参数，以及非零退出/终止信号。替身不启动真实Tauri、不读取或写入正式数据、不请求来源；实际桌面启动和正式库保持按任务另外核验。

V-PY 自动包含 `test_data_update` 与 API 更新反例。V-MIG 的新增旧代码合成库专项入口：从仓库根先导出真实旧版存储模块，再执行；脚本只使用自动清理的临时数据根，不联网、不写原库。

```bash
git show c39ee17514746e41b213b959f9a84417f0d61342:python/src/pmi/snapshot.py > /tmp/thewolf-legacy-snapshot.py
PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/legacy_update_smoke.py --legacy-snapshot /tmp/thewolf-legacy-snapshot.py
```

退出 0 且输出 `legacy code A/B same-time ... PASS` 表示旧代码建库、同刻重试、更新中断、固定视图及备份恢复断言通过。不存在旧提交/源码时记录材料缺失，不能用当前代码建库冒充。实际真实来源、桌面及原库切换证据仍须按任务单独核对。

### 沪深300价格首版隔离验证

本入口对应[任务 TASK-20261005-01](docs/tasks/TASK-20261005-01-csi300-price-slice.md)。指数写入由独立开关控制：QA追加 `--enable-index-update` 才启用，数据根由上述隔离参数指定；日常`npm start`已按任务书使用衔接增补启用正式根的手动指数更新，不把QA数据导入正式根。仍只在点击时更新，启动和GET不采集。指数位于所选父根的 `indices/csi000300`，与002245共用父根写锁，原002245接口和写开关保留。

从仓库根执行专项检查：

```bash
PYTHONPATH=python/src:python/tests python/.venv/bin/python -m unittest test_index test_index_tencent -v
PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/index_service_smoke.py
```

第一条使用合成双源反例及真实中断子进程；第二条使用隔离合成库与真实回环服务，检查指数当前/固定视图、证据、旧切片和权限，并核验父管道退出及端口释放。均不访问金融来源、不操作正式库。前端在 `apps/desktop` 执行 `node --test scripts/index_view.test.cjs scripts/evidence_read.test.mjs scripts/update_recovery.test.cjs scripts/start_daily.test.mjs`，覆盖实际组件回调、绘图范围、迟到证据、更新结果及旧行为；React调度/传输替身不能代替原生界面验收。

腾讯候选及P01中证原件离线重放使用下列命令；替换为本机真实证据根与新空隔离根。脚本校验固定两源/日历哈希及原始获取记录，保留原时间，不联网；材料缺失时失败，不补造原件或时间。此检查不代表新鲜手动更新成功。新发布只使用腾讯day分支和中证；旧东财契约快照及证据按原策略只读核验，不迁移或重写。

```bash
PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/index_replay_smoke.py \
  --p01-root /absolute/path/to/p01-evidence \
  --tencent-root /absolute/path/to/tencent-candidate-evidence \
  --data-root /absolute/path/to/new-empty-isolated-root
```

原生UI沿用上方QA入口，可用成对 `--window-width 520 --window-height 560` 或 `1280/720` 覆盖本次临时窗口尺寸；不改正式Tauri配置。真实更新验证必须遵守任务书2026-10-06腾讯换源增补后的合计8个job/12次尝试/64 MiB预算，实际授权与剩余额度见[status](docs/status.md)；通过本次QA进程环境 `WOLF_INDEX_BUDGET_LEDGER=/absolute/path/to/shared-network-ledger.jsonl` 共用账本，换窗口继续原计数。该环境值仅供受控验证；每源单次请求、无重定向/重试、8 MiB正文上限、45秒硬截止及5/15秒连接/读取超时，保留代理/TLS。新鲜来源不可用时记录阻塞，不把离线重放改判A04成功。
