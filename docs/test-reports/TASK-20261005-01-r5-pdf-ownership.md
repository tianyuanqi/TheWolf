# TASK-20261005-01 · r5 PDF同步资源归属修复交接

**2026-10-06修复交付状态：待审就绪，可进入第2轮独立复审。** M01-R01的“URL已接受、React尚未提交状态时普通导航卸载”反例已在固定r4复现，重新构建指向r5生产组件的同一探针通过：创建1个URL、撤销1个，不能继续读回正文。原43项前端、新增5项真实React检查、构建、最小原生阅读/切换/关闭/重入及恢复通过。M01-R01仍待独立复核关闭；不宣布独立审查通过、用户验收或发布完成。第0轮、第1轮“需要修改”全文和r0–r4归档保持。

本报告是本次修复唯一交接入口，适用[原任务书](../tasks/TASK-20261005-01-csi300-price-slice.md)、[第1轮复审§6](TASK-20261005-01-review.md#6-第1轮独立复审--r4--2026-10-06)、[AGENTS](../../AGENTS.md)、[代码规范](../Coding-Standards.md)、[固定交付流程](../Task-Workflow.md#7-开发与修复的固定交付)及[README验证入口](../../README.md#验证入口)。授权和当前问题由协调者在[status](../status.md)维护，coding未写入status或审查报告。

## 1. 固定版本与交接字段

| 字段 | 本轮值 |
|---|---|
| 任务/阶段/模式 | TASK-20261005-01；M01-R01有界最小修复；已授权自动任务书模式 |
| 开发窗口/配置 | `01a10a98-c976-75d1-9315-ec9a7af16235`；请求 `gpt-6.1-sol/high`，运行时未独立核实；复用原窗口，无新Agent/聊天 |
| 初始真实Git基线 | `ff614e4e2605292a9a151ea38a752677f10cd7e7`，HEAD和空索引保持 |
| 上次所审版本/比较基线 | `TASK-20261005-01+r4+51a7ed70004a63f2a3e1fab60c4933e507879503892c2b96575139435ceebe7d` |
| 本次固定源码快照 | `TASK-20261005-01+r5+1592a1fceb7aac187d8602e31f70f27ddcccc4ab1f67c41cc83142c42511eda8`；清单身份，**不是Git提交SHA** |
| 待审SHA/父提交 | 不适用：自动模式未暂存、未提交 |
| 源码ZIP SHA-256 | `114ff5552671bdfecd4cbd56f968a74c0bf8d94260d34f712a77641c6d8791ed` |
| 第1轮审查报告SHA-256 | `1443d018caf82594d49b0edcc0bd1e87f0c310a151007fed11be9821928f4c24` |
| 第1轮审查证据SHA-256 | `384a24c3fabbba815b6226a723d6502c32c3827fd4ac391d78c42e7ab9151123` |
| 修复计数/停止判断 | 已完成复审1/3；本次实质交回复审计第2轮。同根因有依据修复失败保持1/2，未触发停止；若再次失败达到2/2，停止叠加修复并交根因诊断，不清零 |
| 接收者/发送状态 | 原协调者核验后交原独立评审 `01a11071-2602-77f1-a45c-ba32ec471bbc`；本窗口仅交回材料，未跨窗口发送 |

固定材料：[95文件清单](artifacts/TASK-20261005-01-r5-manifest.json)、[源码ZIP](artifacts/TASK-20261005-01-r5-source.zip)、[r4→r5差异](artifacts/TASK-20261005-01-r4-to-r5.patch)、[真实HEAD→r5业务差异](artifacts/TASK-20261005-01-head-to-r5-business.patch)、[证据ZIP](artifacts/TASK-20261005-01-r5-evidence.zip)、[交付索引及最终哈希](artifacts/TASK-20261005-01-r5-delivery.json)。报告自身和证据ZIP最终哈希集中在索引，避免循环自引用。

源码包 `workspace/` 保留所测源码、测试、锁定依赖声明、规则、任务及只读报告，文件模式/哈希/CRC已核验；无删除或重命名，无凭据、真实库、金融原响应、缓存或整个运行环境。清单保留任务开始及r0–r4指纹。r4→r5的status和审查报告差异为协调者/评审所有的只读依赖，新增r4报告也是只读材料；coding未改它们。HEAD累计README差异含此前规划增量，不能全归本轮。

## 2. 根因与同步归属

r4在卸载时改变读取代次，覆盖了body尚未完成及URL创建后接收前卸载；但回调通过代次校验并排入 `setPdfUrl` 后，React仍可能先处理普通导航。最后提交的清理闭包没有新URL，单靠状态所属effect不能覆盖已接受但未提交的资源。这是同一R01完整归属问题，不新增ID，不把有效原验证判为无效，也不改金融或产品约定。

本轮只修改两份既有开发文件，新增两个测试文件：

- [LegacySliceView.tsx](../../apps/desktop/src/LegacySliceView.tsx)：以 `ownedPdfUrl` ref同步持有已接受URL，接受新URL前释放旧所有者，随后先记录新所有者再排入状态。统一释放函数先清空所有者再撤销URL。卸载同时使读取失效并释放所有者；关闭及快照替换也同步释放，关闭使正在读取的结果失效。移除依赖 `pdfUrl` 状态提交的回收effect，避免旧清理释放错误对象。接口、页面结构、金融契约和来源保持。
- [pdf_ownership.fixture.tsx](../../apps/desktop/scripts/pdf_ownership.fixture.tsx)、[pdf_ownership.test.mjs](../../apps/desktop/scripts/pdf_ownership.test.mjs)：真实React `createRoot`、普通按钮事件和标准浏览器Blob URL；两次microtask控制接受后、提交前的相邻窗口，不使用flushSync或替代React调度。显式合成传输只控制正文时机，所有外部路由阻断。
- [README](../../README.md#验证入口)：增加真实React专项及既有Playwright运行时参数；不安装依赖。原r4 PDF测试保持字节不变。

同步所有者覆盖已展示和待展示资源；失效代次继续拦截未接受的迟到结果。回收不再等下一次effect提交，关闭/替换/卸载后旧对象实际不能读取；正常切换后新对象保持可读。

## 3. 同一反例与新增回归

先从固定r4源码包解压隔离副本，核对Legacy源码SHA `afa4fa323f7407668ef404ba1183f4e0000d3ba12ff196f1a81f17b02df4fd78`。复用第1轮证据的 `review-react-entry.tsx`、`build-react-probe.mjs`、`run-real-react-probe.cjs`，只替换本机路径、重新构建。普通导航后创建1个URL、撤销0个，仍可读 `explicit synthetic PDF bytes`；结果REPRODUCED见 `r4-real-react-before-commit.json`。

修复后同一entry不改时序，重新构建指向r5源码SHA `311a61c1db73493c3ae73e3b82a18c8e157490e73a9b35a8e7c9fb320df2086e`，执行脚本将断言改为撤销且读回失败。结果PASS：创建1个、撤销1个、读回为null、iframe为0、无页面错误。见 `r5-real-react-before-commit.json`；事件为旧页提交→URL创建→普通导航→URL撤销→市场提交。r4/r5的bundle分别重新生成并保存，未将r4 bundle当r5。

新增稳定真实React专项共5项：普通导航的首次待提交URL（普通模式、StrictMode各1项）；替换原件状态待提交时导航释放旧/新两个URL；待提交时关闭释放旧/新两个URL；正常读取/选择切换/关闭/重开/卸载，切换后只旧URL失效、新URL可读。测试显式使用React开发态，StrictMode用例实际观察至少两次初始effect提交，覆盖重放。相同新增测试在固定r4是1通过、4按预期失败，修复版5项全通过；日志为 `r4-new-regression-expected-failure.log`、`v-fe-real-react.log`。预期基线失败不增加修复失败计数。

原43项专项全部通过，保留body读取中卸载、创建后接收前卸载、已有URL卸载、正常关闭/选择切换、旧响应选择改变，以及市场迟到证据和旧更新不确定恢复。断言先于夹具最终清理；夹具释放用于环境恢复，不计作生产回收。浏览器测试失败或成功均关闭上下文、浏览器并释放夹具URL，不保留活动依赖引用。

## 4. 最小原生验证与沿用边界

隔离根 `/private/tmp/thewolf-m01-r5-6vaviqqf`；Vite5174、本地Python8001、QA标识 `com.thewolf.qa.p5174.p8001`，520×560。复用原QA二进制，当前前端生产组件；仅复制获准r4隔离测试库，两写入开关均为0，无故障注入、POST或来源请求，未访问正式根。

实际原生操作：报告第7物理页和预告第1页正常渲染；报告关闭移除原件；预告已打开时选择报告，新报告正常且旧预告iframe移除，随后关闭；重新打开预告后切市场并重入资料页，无旧原件显示。截图 `ui-report.png`、`ui-forecast.png`已人工查看；实际本地Blob地址/原文在 `ui-report-read-ax.txt`、`ui-forecast-read-ax.txt`，操作结果在 `ui-report-closed-ax.txt`、`ui-selected-report-ax.txt`、`ui-selection-closed-ax.txt`、`ui-pdf-away-ax.txt`、`ui-pdf-reentered-ax.txt`。本地GET记录为 `native.log`。

两原件SHA为 `71409583d1d8ce18a49951d2d3079faea8e35a5df8473020f1723a3777eaefdc`、`d3a5bb349f74f1acb1da17607a877564a969d17eceb39d3d08bedd5bb7d3de51`，测试输入和原来源根指纹核对保持。原生不显示旧PDF支持消费者行为；资源释放以真实React/标准URL读回反例证明，未测量原生heap或声称内存增量数值。

沿用[r4报告§3.2](TASK-20261005-01-r4-pdf-unmount.md#32-原生消费者复核)及第1轮独立核验的body延迟切页、市场迟到证据、两PDF原直接关闭和旧更新120秒人工只读恢复证据。市场证据和旧更新控制逻辑未变；body迟到/创建前后保护的原专项已重跑，原生流程不变，故不再重复120秒原生等待、全部宽窗矩阵、57项Python/回环/父EOF、金融获取/1040值与旧源兼容。相关金融/后端代码不变，原r3及首次独立证据继续适用。Python分发、五年/估值/PIT、正式启用、用户验收和发布仍未执行。

## 5. 实际命令与证据

项目沿用已有锁定Vite/React/Node依赖、桌面 `load_workspace_dependencies` 返回的已有Playwright包 `/Users/yuanqi/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright`。所测业务代码对应r5固定快照，以下为coding自检，不是独立审查。

| 工作目录/实际命令 | 结果/证据ZIP内文件 |
|---|---|
| 仓库根：`node <r5根>/r4/evidence/build-react-probe.mjs`，随后 `node <r5根>/r4/evidence/run-real-react-probe.cjs` | 固定r4反例REPRODUCED，`r4-react-build.log`、`r4-real-react-probe.log`、结果JSON及bundle |
| 仓库根：`node <r5根>/r5/evidence/build-react-probe.mjs`，随后 `node <r5根>/r5/evidence/run-real-react-probe.cjs` | 同一时序指向r5，PASS；`r5-react-build.log`、`r5-real-react-probe.log`、结果JSON及bundle |
| 仓库根：设置上述 `WOLF_PLAYWRIGHT_MODULE`，运行 `node --test <r5根>/r4/workspace/apps/desktop/scripts/pdf_ownership.test.mjs` | 同一新测试对固定r4，5项1通过4预期失败，退出1 |
| `apps/desktop`：`node --test scripts/evidence_read.test.mjs scripts/index_view.test.cjs scripts/update_recovery.test.cjs scripts/start_daily.test.mjs` | 43项通过，`v-fe.log` |
| 仓库根：设置上述 `WOLF_PLAYWRIGHT_MODULE`，运行 `node --test apps/desktop/scripts/pdf_ownership.test.mjs` | 最终开发态5项通过，`v-fe-real-react.log` |
| `apps/desktop`：`npm run build` | 类型及构建通过，`v-build.log` |
| `apps/desktop`：`WOLF_SERVICE_PORT=8001 WOLF_DEV_PORT=5174 npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`；只读QA包及CUA操作 | §4原生检查通过，`vite.log`、`native.log`及AX/截图 |
| 仓库根：`python3 <r5根>/evidence/verify_snapshot.py docs/test-reports/artifacts` 及 `python3 <r5根>/evidence/final_check.py` | 95文件/模式/CRC、所测工作区一致及历史保全通过，`snapshot-verification.json` |
| 仓库根：`python3 <r5根>/evidence/check_docs.py` | README/本报告链接、锚点、围栏、空白及Git差异通过，`vdoc-result.json` |
| 仓库根：`python3 <r5根>/evidence/restore.py` | 恢复核验通过，`restoration.json` |

`<r5根>`为上方实际临时根；完整构建/运行脚本固定在证据ZIP，原临时探针目录已清理。第一版新增测试使用生产React，随后明确切为开发态并对固定r4/修复r5重新执行，最终日志有实际StrictMode重放证据；未据此改业务代码或重复无关检查。汇总为 `verification-summary.json`。

## 6. 恢复、预算与复审入口

开发前记录已有源码/规则/报告/全部归档指纹、真实HEAD/空索引、六端口、代理摘要、账本；启动原生前追加四处QA持久路径仍不存在的基线。原输入副本指纹也在启动前保存。原生退出使本轮父服务结束，停止唯一拥有的Vite；QA专用WebKit/Caches恢复不存在，Preferences/SavedState也不存在。临时QA包、r4/r5探针副本、依赖引用已移除，浏览器上下文/无头进程无残留；本轮未启用sitecustomize或运行故障注入。六端口5173/8000/5174/8001/5184/8014均无监听，代理摘要/原输入/旧报告和归档/HEAD及索引保持。只保留无进程引用的测试数据副本与必要证据。**未恢复项：无。**

相对本轮开始仅Legacy和README两份既有开发文件变化，另新增上述两个测试及本次报告/归档；协调status、评审报告保持开始版本。原规划和业务已有增量按归属保全，无正式库操作、暂存、提交、amend/reset/push或部署。

共享账本SHA保持 `8010f55c7f05d850c6ab25331a45238ff1de863eab245ff52873e1a112adcc4a`，仍**7job/8次/158,887字节**；本轮外部金融请求0，最后1job/4次/66,949,977字节保留独立审查。P01、候选、诊断和外部自述尝试分别沿用，未重置失败和预算。

证据归档可重建：解压固定r4/r5源码至不同隔离目录、核对清单/模式，使用既有锁定依赖及上述运行时；原评审entry导入路径应放在 `apps/desktop`，构建/执行脚本的本机root须替换并分别重新构建。稳定专项入口已经在r5源码内，不依赖临时副本。原生复核须取得上述哈希匹配的获准真实PDF/指数副本，缺失时如实记录，不能用合成内容替代真实阅读证据。

没有剩余开发材料或环境阻塞；M01-R01待独立关闭。旧第1轮修复失败1/2保持，本次交回记第2轮，尚未触发停止。M01-V01/V02/V03、ODATA01/OUI01及范围外问题结论不重写。

下一步一句话入口：**“按《TASK-20261005-01 · r5 PDF同步资源归属修复交接》核对r5固定快照、r4新增差异及累计范围，执行第2轮独立复审并复核M01-R01全部关闭条件；若同根因再次失败达到2/2，停止继续修补并交根因诊断。”** 原协调者核验后复用原独立评审窗口，本窗口不自行发送或创建窗口。
