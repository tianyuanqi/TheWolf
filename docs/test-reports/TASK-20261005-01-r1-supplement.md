# TASK-20261005-01 沪深300价格首版实施补证 · r1

**当前状态：阻塞，尚不能进入独立审查。** 本报告为2026-10-06首次实现、首次送审前补证的交付快照。M01-V02、M01-V03所缺本地原生场景已补齐；M01-V01 / A04新空根真实双源获取、校核和发布仍未通过。当前授权、开放问题及后续处置以[status](../status.md)为唯一来源；本执行者未写status，也未启动独立审查。

| 阻塞项 | 原因与影响 | 解除条件、负责人及下一步 | 是否需要用户操作 |
|---|---|---|---|
| M01-V01：环境与必要验证缺口 | 第5个真实job仍在东财获取阶段失败，0正文，中证未请求。异常链显示连接代理时远端关闭连接，具体责任端未定；无法证明A04新鲜两源闭环及其原生成功更新结果 | 协调者安排定位和恢复连接条件，再安排有限A04补证；开发/审查执行者使用新空隔离根，保留真实账本、哈希、发布和原生证据。不改来源、代理或TLS，不重置预算，不继续同类探测 | 无需重复确认开发；目前不能给出已定位、可由用户直接执行的修复操作 |

## 1. 任务与固定版本

任务书：[TASK-20261005-01](../tasks/TASK-20261005-01-csi300-price-slice.md)。设计：[§5.6](../Market-Dashboard-Design-V0.1.md#56-沪深300首版p02实施设计2026-10-05)。适用规则：[AGENTS](../../AGENTS.md)、[代码规范](../Coding-Standards.md)、[Task-Workflow](../Task-Workflow.md#72-自动任务书模式固定快照审查与git待提交)；验证入口：[README](../../README.md#验证入口)。实现说明、完整A01–A12初始判断和已有自动化证据保留在[r0实施交接](TASK-20261005-01-implementation.md)，本报告只追加补证，不改写r0结论。

- 阶段/模式：首次实现，已授权自动任务书模式；补证延续协调者原指令及10月6日用户“继续”。开发窗口 `01a10a98-c976-75d1-9315-ec9a7af16235`；请求配置 `gpt-6.1-sol/high`，运行时模型/档位仍无法独立核实。没有创建窗口或子Agent，没有跨窗口发送消息。
- 初始真实Git基线：`ff614e4e2605292a9a151ea38a752677f10cd7e7`；首次审查比较基线为该SHA加r0清单记录的既有增量。上次所审SHA不适用，尚无独立审查；本轮比较版本为r0固定快照。
- 本次待审提交SHA/父提交：不适用，自动模式未暂存或提交；HEAD与空索引保持。无amend、reset、push、merge、Tag或发布。
- r1固定快照：`TASK-20261005-01+r1+111422d71d067d764c6b3bf52a48baa5005b2f5c81e2198ea63481564ecb2173`。84份源码、测试、配置、任务/规则及r0报告依赖；[清单](artifacts/TASK-20261005-01-r1-manifest.json)逐文件记录SHA-256、模式、归属及相对r0差异。此指纹不是Git提交。
- [r1源码ZIP](artifacts/TASK-20261005-01-r1-source.zip) SHA-256：`0479908b967369652b5b944b0d79ff965601e382f54e08b259c5a24c8cc3b88c`；[r1证据ZIP](artifacts/TASK-20261005-01-r1-evidence.zip) SHA-256：`b54aa44612bd9c6266e80426df6764b6488190b3cda3d313d28d75d9de96a16b`。本报告和交付索引单列，不进入自身快照或哈希循环。

r0报告SHA-256 `7d26875420e6285eafe036ca4655472f17f5175c82e258aabca9cec6145d536d`；r0清单/源码ZIP/证据ZIP均逐文件核验未变，其指纹仍为r0报告所列值。本轮业务与测试源码**零差异**；源码依赖仅status被协调者更新，清单另纳入r0报告。新增本报告、r1固定材料；临时故障/诊断脚本只进入证据，不进入产品源码。开始已有文档和代码增量完整保留，无方案偏离或依赖升级。

## 2. 第5个真实job与累计预算

已授权的恢复后复查于2026-10-05 UTC执行：job `40a64843d509430a8574622bbf6b80e0`，东财attempt `77be3d872b35499186fab6ac12d4882f`；开始 `11:43:50.121592`、结束 `11:43:50.422957`，正文0字节，终态failed。新空根为 `/private/tmp/thewolf-m01-r1-6psh4p0j/live-empty`，当前指针未发布。证据：`live-job5-status.json`、`live-job5-*.png`、AX、`live-native.txt`及共享账本副本。

仅给真实获取子进程增加异常观察包装，原requests调用、代理、TLS校验及正常执行权限保持。包装在异常时遍历cause/context/reason/异常参数，限制12节点并脱敏，不重试、不新增网络请求。`diagnostic-redaction-test.jsonl`为无网络合成异常的脱敏检查，与真实失败分开。

`live-diagnostics.jsonl`真实链：`requests.exceptions.ProxyError` → `urllib3.exceptions.MaxRetryError` → `urllib3.exceptions.ProxyError`（Unable to connect to proxy）→ `http.client.RemoteDisconnected`（Remote end closed connection without response）。没有HTTP响应、明确errno或TLS错误，不能归责于代理配置、转发链或来源服务器中的某一端。MaxRetryError是异常类名称，不能据此宣称发生了多次HTTP重试。

本任务累计**5个真实job / 5次尝试 / 0正文字节**，五次均在东财阶段失败，中证未请求。总上限6个job / 12次 / 64MiB，剩余**1个job / 7次 / 64MiB保留给独立审查**。账本不清零，job6未执行；没有额外外网诊断、替代来源、估值或发现请求。本地UI注入的两次POST不调用更新器，不计作真实上游job。M01-V01未关闭，A04未通过；A05原生新鲜成功更新的结果仍受其限制。

## 3. 原生补证及验收变化

环境为既有macOS arm64、Python 3.12.14、Node/Vite/Tauri开发态。隔离根 `/private/tmp/thewolf-m01-r1-6psh4p0j/ui-data`；原生窗口960×720，独立QA标识 `com.thewolf.qa.p5174.p8001`，端口5174/8001。数据读取使用真实本地API、鉴权、固定存储及原生WebKit；金融价格种子是P01固定原件离线重放，不作为新鲜获取。原生截图为Retina像素尺寸。

| 条目 | 实际操作及观察 | 证据 / 判断 |
|---|---|---|
| A09加载 | 本地指数GET延迟4秒，切入市场页显示“正在读取本地指数”，未显示伪造零点位 | `ui-loading.png`及AX；M01-V02该场景补齐 |
| A09读取超时与恢复 | GET延迟12秒，原客户端8秒Abort显示错误；移除延迟，点击“重试启动并读取”，恢复4357.62、+0.29%及K线 | `ui-read-timeout.*`、`local-ui-events.jsonl`含ready/重读，后续正常页面截图；恢复由执行者实际观察 |
| A09指数POST不确定结果 | POST被本地拦截且延迟12秒；8秒客户端超时后旧图保留、更新按钮禁用并轮询GET。120秒后停止轮询，手动核对显示“未发现新的更新任务，已结束等待”，重新开放按钮 | `ui-index-post-timeout.*`、`ui-index-manual-recovery.*`；事件日志只有一次指数POST，无自动再次POST。跨用量中断后继续核验，等待期限仍有效 |
| A09选日与迟到证据 | 7月8日双源证据延迟6秒，选7月9日后清除旧面板并取得新四值；另在7月8日请求未完成时连续切旧页→总览，6秒旧响应完成后当前仍选9月30日，无7月8日面板；再打开新依据，显示两源行259及正确四值 | `ui-new-selection-ax.txt`、`ui-day-pending-ax.txt`、`ui-evidence-continuous-switch-ax.txt`、`ui-after-late-responses.*`、`ui-new-evidence-after-switch.*`；按事件时间核对响应晚于重入页 |
| A11真实PDF加载/切换 | 两原件本地读取延迟6秒，显示加载并禁用重复读取；半年度报告渲染第7页，会计数据页和收入与卡片相符；切业绩预告渲染第1页，发行人、标题和公告编号相符 | `ui-pdf-loading.*`、`ui-pdf-report.*`、`ui-pdf-forecast.*`；实际AX含blob iframe和PDF正文，截图肉眼核验 |
| A11迟到PDF与页面切换 | 报告PDF读取未完成时切到总览，迟到200响应未在总览显示旧PDF | `ui-pdf-pending-page-switch-ax.txt`、`ui-after-late-responses.*`、事件日志；未打开外部出处按钮 |
| A11旧更新恢复 | 旧POST同样拦截延迟；8秒超时→120秒等待→手动核对结束，恢复“更新日线”按钮；60行、单位、两公告及已打开预告仍保留 | `ui-old-post-timeout.*`、`ui-old-manual-recovery.*`；只有一次旧POST，无自动再次POST |
| A12恢复 | 原生/Vite/子服务退出，端口及代理回到开始基线；静态备份及隔离旧副本7文件保持，DB完整性ok；故障包和QA系统缓存移除 | `local-assertions.json`、`local-db-check.json`、`cache-cleanup.json`、`restoration.json` |

本地纯ASGI包装只延迟GET的response.start；两更新POST先执行原鉴权，再记录`post_not_forwarded`并返回明确合成idle/job_id=null，**绝不转发到真实更新器**。GET业务内容及原件字节保持，前端超时/120秒期限未改。测试脚本 `local_fault_and_diagnostics.py`、末态模式和事件时间保留在证据ZIP；这是受控传输场景，不能判为真实来源更新成功。

本报告判断M01-V02、M01-V03的原生补证条件已满足，交协调者据证据更新status；A09本地状态矩阵和A11旧行为回归补齐。A01–A03、A06–A08、A10的已有有效自测沿用r0相同源码，不重复执行；r0的49项Python、36项前端、构建、真实回环与生命周期检查没有被重新声称为独立审查。尚无用户验收、发布或独立审查结论。

## 4. 静态备份原件与复现入口

协调者明确授权只读复制静态归档 `.local-data/backups/002245-before-daily-20261003T075241Z`；未打开当前正式slice根。复制后固定旧快照 `2efb50784685da0d0576e723b64b65d1a7692f73521a979bc8f1ec8e1b076884`，60日2026-07-03—09-24。PDF原件如下：

| 原件 | SHA-256 | 字节数 |
|---|---|---|
| 半年度报告 | `71409583d1d8ce18a49951d2d3079faea8e35a5df8473020f1723a3777eaefdc` | 901598 |
| 半年度业绩预告 | `d3a5bb349f74f1acb1da17607a877564a969d17eceb39d3d08bedd5bb7d3de51` | 59581 |

`backup-before.json`与结束重新哈希比较，7文件全部相同；`legacy-fixed.json`记录固定视图、文档和原件。真实PDF、原行情及DB不纳管。跨机器重放须取得匹配哈希的授权副本；缺失时报告材料不足，不生成替代金融事实。

命令均采用r1快照中的原实现。仓库根以`PYTHONPATH=python/src:python/tests python/.venv/bin/python python/tests/index_replay_smoke.py --p01-root /private/tmp/thewolf-p01-csi300-qkuqgt8q --data-root <隔离ui-data>`准备价格种子，输出`index-seed.txt`。在`apps/desktop`以`WOLF_SERVICE_PORT=8001 npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`运行前端；`run_qa.py`用独立根、5174/8001、960×720及显式开关构建QA二进制，日志`qa-build.txt`。为原生操作绑定，仅把该二进制包装为临时QA.app；之后以`PYTHONPATH=<临时故障脚本目录>:python/src WOLF_QA_LOCAL_FAULTS=1 WOLF_DEV_PORT=5174 WOLF_SERVICE_PORT=8001 WOLF_SLICE_DATA_ROOT=<隔离ui-data> WOLF_ENABLE_INDEX_UPDATE=1 WOLF_ENABLE_DATA_UPDATE=1 <QA.app二进制>`运行。复现前将证据脚本ROOT改为新的隔离目录、复制为`sitecustomize.py`并创建模式JSON；两POST拦截是该命令的必要前置条件，不能移除包装后随意点击更新。

源码ZIP解压到新目录，以`workspace/`为仓库根；先核对清单84份SHA及模式，再使用README入口。r1的V-DOC从仓库根执行`python/.venv/bin/python /private/tmp/thewolf-m01-r1-6psh4p0j/evidence/check_docs.py`；脚本和结果打包，可调整仓库常量重跑。源码清单/ZIP/工作区核对脚本及结果为`freeze_r1.py`、`snapshot-verification.json`。V-DOC通过：5份Markdown、62处本地链接/锚点、围栏与空白；84份源码SHA及模式全部匹配。此步骤只是文档、差异与交付自检。

## 5. 恢复、计数及交接

r1开始基线见`baseline.json`：HEAD、空索引、候选文件指纹、六端口无监听、代理环境哈希；正式数据边界为仅授权静态备份。结束核验5173/8000/5174/8001/5184/8014全部无监听，自有native/Vite/uvicorn无残留。代理摘要保持；两副本DB完整性ok，旧原件/DB7文件逐字节保持；ui-data未产生真实更新任务或出站账本，仅离线重放产生既有指数committed_job。QA WebKit/Caches的出生时间晚于r1基线，按精确标识清理并确认不存在；Preferences/Saved State原本不存在。临时sitecustomize、模式文件、QA.app移除，必要脚本副本和证据保留。未安装依赖或改系统/日常配置，无已知未恢复项。

保留r1隔离数据及证据和既有构建缓存，均无运行环境指向；P01原件仍沿用r0登记的外部临时根，不承诺临时文件永久存在。未读正式当前根，不能声称核验了其他进程期间的正式数据变化。与r1开始指纹比较只有协调者status改变；所有原业务/测试文件、r0报告和三个固定归档保持。

复审修复轮次0/默认上限3；已定位同根因代码修复失败0次。五次来源连接失败及用量中断计数如实保留，不清零，也不冒充已定位代码修复失败。已停止同类出站；当前因A04必要验证受阻，不能据此改判待审就绪。

接收者为原协调窗口。本窗口只返回报告与固定材料路径，实际跨窗口发送未执行。下一步：协调者核验r1及恢复证据，登记V02/V03补齐；保留V01，先安排恢复连接条件和有限A04补证，材料齐备后再按自动模式创建独立评审。当前r1不能作为审查通过、用户验收通过或允许提交/上线的依据。
