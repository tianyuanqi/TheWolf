# TASK-20261005-01 沪深300价格首版有限补证 · r2

**当前状态：阻塞，尚不能进入独立审查。** 2026-10-06首次送审前补证：已同步获准的7job预算守卫并通过针对性验证，但唯一新增开发job6仍失败；M01-V01 / A04未通过，A05真实成功更新亦缺证据。已立即停止来源请求，恢复本次测试影响。当前授权、计数、问题及下一步仍以[status](../status.md)为唯一来源；本窗口未写status。

| 阻塞项 | 原因与影响 | 解除条件、负责人/下一步、用户操作 |
|---|---|---|
| M01-V01：环境与必要验证缺口 | job6东财请求再次RemoteDisconnected/ProxyError，正文0字节，中证未请求；新空根未发布快照，不能证明A04真实双源闭环或A05原生成功更新。此前两次CONNECT/TLS成功不能替代行情GET成功 | 协调者依据现有诊断材料确定新的定位方案及有限授权/预算，再安排开发或审查执行者完成新空根双源获取、校核、发布和原生成功证据。当前开发追加额度已用尽，不能重复原路线或挪用审查job；尚无已定位、可直接要求用户执行的修复操作，不需重复确认开发 |

## 1. 授权、差异与固定版本

任务：[TASK-20261005-01](../tasks/TASK-20261005-01-csi300-price-slice.md)，设计[§5.6](../Market-Dashboard-Design-V0.1.md#56-沪深300首版p02实施设计2026-10-05)，规则[AGENTS](../../AGENTS.md)、[代码规范](../Coding-Standards.md)、[Task-Workflow](../Task-Workflow.md#72-自动任务书模式固定快照审查与git待提交)，命令[README](../../README.md#验证入口)。完整实现/初始验收沿用[r0](TASK-20261005-01-implementation.md)，本地原生补证及恢复沿用[r1](TASK-20261005-01-r1-supplement.md)，连接诊断由协调者的[诊断报告](TASK-20261005-01-network-diagnosis.md)维护。原报告和固定归档未修改。

- 本轮为首次实现的有限补证，已授权自动模式，非复审修复。用户于2026-10-06在协调窗口明确批准“2次连接诊断＋1个补证job”，status登记后由协调者传入本窗口；两次诊断已由协调者完成，不再执行。开发窗口仍为 `01a10a98-c976-75d1-9315-ec9a7af16235`，请求配置 `gpt-6.1-sol/high`；运行时模型/档位无法独立核实。无新窗口、子Agent或跨窗口发送。
- 初始真实基线 `ff614e4e2605292a9a151ea38a752677f10cd7e7`；上次所审SHA不适用，独立审查尚未开始。本轮比较基线为r1固定快照 `TASK-20261005-01+r1+111422d71d067d764c6b3bf52a48baa5005b2f5c81e2198ea63481564ecb2173`。
- 本次待审提交SHA/父提交不适用：自动模式不暂存、不提交。HEAD与空索引保持；无amend、reset、push、merge、Tag、发布或正式根操作。
- r2固定快照 `TASK-20261005-01+r2+1b923bfc23521ad3eebc0d4213079075d85e99afb4a8e706c14780f7ec16ead0`；[清单](artifacts/TASK-20261005-01-r2-manifest.json)记录86份源码、测试、配置、规则、任务及历史/诊断报告依赖的哈希、模式和相对r1差异。这是文件快照指纹，不是Git提交SHA。
- [源码ZIP](artifacts/TASK-20261005-01-r2-source.zip) SHA-256 `1c8a18d63a4108aae0aa14fab884dc5846a08fa60a2b7b6392ab47f50bbf178c`；[证据ZIP](artifacts/TASK-20261005-01-r2-evidence.zip) SHA-256 `02c86c59a0bf67c1c3d9a0d211cac9510731fa08750b784098f168c49a25fa83`；[r1→r2开发差异](artifacts/TASK-20261005-01-r1-to-r2.patch)。本报告与交付索引单列，避免自引用哈希循环。

| 本轮写入 | 必要变化与消费者 |
|---|---|
| `python/src/pmi/index_update.py` | 仅把共用验证账本job上限6改7并同步说明；12次/64MiB/8MiB预留及账本锁、持久化、来源/代理/TLS/发布规则不变。只有配置共用验证账本时启用该守卫，正式产品行为边界保持 |
| `python/tests/test_index.py` | 新增3项无网络账本边界测试：第7可开始并继续第二源、第8拒绝且不改历史；第12可记录、第13拒绝；已完成和未完成预留合计64MiB后拒绝新增 |
| 任务书、README | 保留初始6job约定并追加2026-10-06有限授权；实际运行入口同步为7job，引用status中的实际授权/额度，不重置计数 |

以上4文件是本窗口r1→r2开发差异。status由协调者更新；协调者新诊断报告作为只读依赖固化，不算开发改动。固定时点后的协调文档可继续变化，接手不得把最新工作区内容混作固定快照代码。没有改前端、Rust、依赖、日历、来源、数据契约、鉴权或发布规则；无方案偏离。现有其他增量保留。

## 2. 真实job6及诊断边界

新空隔离根 `/private/tmp/thewolf-m01-r2-f3jpujgh/live-empty` 创建时无文件，未导入P01或旧样本。通过真实原生“检查更新”按钮发起唯一一次POST，正常本地API返回202；随后GET显示failed，页面保持无本地快照与ProxyError提示。`native.txt`核对只有1次指数POST；无自动重复POST。

| 项目 | 实际证据 |
|---|---|
| job / attempt | `beda26e25276410c91d2b2b3b3b370f1` / `9367184b91744b4fb405c496955b6ad8` |
| 时间 | 东财尝试UTC `2026-10-05T17:26:33.664628+00:00`—`17:26:34.743290+00:00`；北京时间10月6日01:26:33—34 |
| 固定目标 | 2025-09-04—2026-09-30，260完整交易日，服务端按已核验日历推导冻结；不是离线种子 |
| 终态 | failed / source network unavailable (ProxyError)，正文0字节；中证未请求、无SQLite/快照发布、last_success_at及previous_snapshot_id为null |
| 原生与API | `ui-before-real-job.*`、`ui-real-job-started.*`、`ui-real-job-failed.*`，`native.txt`及`live-job6-status.json`；`live-empty-result.json`核验未发布及唯一POST |

异常观察沿用r1脱敏脚本，仅在获取子进程的requests.get抛异常时保存类型、cause/context/reason/异常参数；没有改transport参数、关闭证书校验或重试。脚本为证据中的`diagnostics_observer.py`。真实异常链见`live-diagnostics.jsonl`：`requests.exceptions.ProxyError` → `urllib3.exceptions.MaxRetryError` → `urllib3.exceptions.ProxyError` → `http.client.RemoteDisconnected`，底层为“Remote end closed connection without response”。无HTTP响应、明确errno或TLS错误，**未记录真实traceback，不能定位CONNECT、TLS或后续哪一步断开**。MaxRetryError名称不代表多次真实请求。

协调者现有证据已只读复制进r2证据ZIP：

- `target-connection-ledger.jsonl`：北京时间01:20:38/39，两目标各一次CONNECT 200、TLSv1.3及证书校验成功，无行情GET；诊断2/2已用完。
- `target-log-matches.json`及`target-log-matches-after-job6.json`：上述两次和job6对应01:26:34.626的东财连接均匹配`GeoIP(CN) using DIRECT`。这支持所记录ClashX连接选DIRECT；HTTP代理参与不等于选VPN节点，不能将失败简单归因为VPN节点。未改NO_PROXY、全局代理或TLS。
- `offline-proxy-label-check.json`：协调者以假socket/空响应、无真实socket观察到RemoteDisconnected后代理连接标志清空。它只说明ProxyError包装标签不足以判断阶段，不能证明job6已到GET响应阶段，也不是新增连接探测。本窗口仅复制现成结果。

两次诊断的握手可达与job6实际请求失败同时成立；旧5次及本次失败根因均未确定。没有为补调用栈、验证标签或换来源追加任何请求。

## 3. 预算回执、验证与未执行项

仍使用原共用账本 `/private/tmp/thewolf-m01-implementation-3kyht073/evidence/network-ledger.jsonl`。r2开始副本与结束副本逐字节前缀比较，原5job/5次/0字节保持，本次只追加1个attempt及其finished；不能以新根作为新预算。两轮旧证据ZIP中的历史账本保持其原时点计数。

| 额度 | 本次结束实际值 |
|---|---|
| 来源任务 | 6/7，剩余1个仍保留独立审查；本次新增开发job额度已用尽 |
| 来源尝试 | 6/12，剩余6次；本job东财早失败，中证0次 |
| 正文 | 0/64MiB，剩余64MiB |
| 单列连接诊断 | 2/2，全部由协调者此前完成；本窗口没有追加 |

macOS arm64、既有Python 3.12.14/Node/Tauri环境。所测代码为本报告r2快照；命令从仓库根执行，日志在证据ZIP的`evidence/`下。

| 入口/命令 | 结果与边界 |
|---|---|
| V-PY `PYTHONPATH=python/src:python/tests python/.venv/bin/python -m unittest test_index.IndexBudgetTests -v`，旧守卫下 | 3项中正文边界通过，另2项在第7job处按旧6job上限拒绝；保留`budget-before-fix.txt`，证明需同步授权 |
| V-PY `PYTHONPATH=python/src:python/tests python/.venv/bin/python -m unittest test_index.IndexBudgetTests test_index.IndexStorageTests.test_start_update_and_budget -v`，同步后 | **4项通过**，`budget-after-fix.txt`；新增边界及既有更新/预算路径，全部独立合成账本，无金融出站 |
| V-UI/API 独立QA5174/8001、新空根、显式指数开关、原共用账本 | 实际POST202和GET200消费者可用，但真实job6失败；A04、受限A05**未通过**，失败后立即停止 |
| V-DOC `python/.venv/bin/python /private/tmp/thewolf-m01-r2-f3jpujgh/evidence/check_docs.py` | 通过：3份Markdown、48处本地链接/锚点、围栏、空白及Git差异检查；脚本和结果随证据固化 |
| 固定材料核对 | 86份SHA/模式与源码ZIP一致，r0/r1报告及固定归档保持；`snapshot-verification.json`、`verify_snapshot.py`及其结果。固化后的status/诊断报告已由协调者继续更新，清单保留固化时点版本，业务及开发文档仍匹配 |

没有机械重跑未受单一预算阈值影响的r0全量49项Python、36项前端、构建、原生矩阵、旧PDF或生命周期；已有有效证据沿用原所测版本，不宣称它们在r2重跑。预算行为变化的独立差异审查尚待后续，不能把本窗口自检当独立审查。真实成功K线、首末/跨年双源原生依据及成功后重启验证本轮未执行：新空根没有成功发布材料，不能导入P01来补成A04成功。r1的V02/V03关闭结论保持；本次无前端变化，不重开其矩阵。

## 4. 复现、恢复与交接

源码ZIP解压到新隔离目录，以`workspace/`为仓库根，先核对清单哈希/模式再运行上述无网络预算检查。README为已有完整入口。真实job命令只是执行记录，**不得以复现名义再执行来源请求**；最后额度仍归审查，须由协调者安排。

实际前端从`apps/desktop`执行 `WOLF_SERVICE_PORT=8001 npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`；原生复用r1已构建960×720 QA二进制的临时.app包装，无Rust重新编译或正式配置修改。运行环境为`PYTHONPATH=<r2临时观察脚本目录>:python/src`、`WOLF_QA_DIAGNOSTICS=1`、`WOLF_DEV_PORT=5174`、`WOLF_SERVICE_PORT=8001`、`WOLF_SLICE_DATA_ROOT=<r2/live-empty>`、`WOLF_ENABLE_INDEX_UPDATE=1`、`WOLF_ENABLE_DATA_UPDATE=0`及原`WOLF_INDEX_BUDGET_LEDGER`。脚本不匹配获取子进程时无API/POST拦截；本次POST为真实更新路径。正常执行权限、代理/TLS保持。临时包装与观察脚本已移除，必要脚本副本保留。

开始基线`baseline.json`记录HEAD/索引、候选文件哈希、六端口无监听、代理环境哈希、原账本哈希及预计4文件变化；`app-state-before.json`记录QA标识系统状态不存在。结束`restoration.json`、`cache-process-cleanup.json`核验：

- 原生、Vite、uvicorn及采集子进程无残留；5173/8000/5174/8001/5184/8014均无监听，与基线一致。
- 代理环境摘要保持；没有修改系统代理、VPN、NO_PROXY、日志级别或TLS配置。未操作正式金融根或再次读静态备份。
- QA WebKit/Caches出生时间晚于本次基线，按精确QA标识移除；Preferences/Saved State仍不存在。临时sitecustomize、QA.app及其字节码移除。
- 只保留已授权源码/文档差异、失败隔离根/原账本与必要证据、既有构建缓存；无活跃数据根指向，无已知未恢复项。失败根无金融快照，正式数据未打开，不声称检查了其他进程的正式数据变化。
- Git初始HEAD/空索引及r0/r1固定材料保持；既有其他修改保留，status只读。协调者后续文档写入不属于本窗口差异。

复审修复轮次0/3，已定位同根因代码修复失败0/2。六次来源失败现象保留，未定位根因，不冒充代码修复失败；新增有限开发额度已消费，已停止本路线请求，不清零或循环尝试。

接收者为原协调窗口。本窗口只返回材料，不发送跨窗口消息。下一步由协调者核验r2/恢复/预算、保留M01-V01并决定新的有依据诊断或补证安排；当前不创建独立审查、不提交Git，也不能标记用户验收或发布完成。
