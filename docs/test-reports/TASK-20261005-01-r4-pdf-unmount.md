# TASK-20261005-01 · r4 PDF卸载修复交接

**2026-10-06修复交付状态：待审就绪，可进入第1轮独立复审。** M01-R01已核实并完成最小修复：公告组件卸载时使PDF读取代次失效，迟到正文不再产生无人回收的对象URL。修复前失败证据、43项前端检查、构建、原生两PDF/切页/受影响路径及恢复核验已齐。M01-R01仍由原独立评审复核关闭；本文不宣布独立审查通过、用户验收或发布完成。第0轮“需要修改”结论及r0–r3材料保持。

本报告是本次修复唯一交接入口。适用[原任务书](../tasks/TASK-20261005-01-csi300-price-slice.md)、[审查§4关闭条件](TASK-20261005-01-review.md#4-发现及关闭条件)、[AGENTS](../../AGENTS.md)、[代码规范](../Coding-Standards.md)、[固定交付流程](../Task-Workflow.md#7-开发与修复的固定交付)、[README验证入口](../../README.md#验证入口)。当前授权与问题状态由协调者在[status](../status.md)维护，coding未写入该文件。

## 1. 固定版本与交接字段

| 字段 | 本轮值 |
|---|---|
| 任务/阶段/模式 | TASK-20261005-01；M01-R01范围内修复；已授权自动任务书模式 |
| 开发窗口 | `01a10a98-c976-75d1-9315-ec9a7af16235`，复用原窗口，无新Agent/聊天 |
| 模型与档位 | 请求配置 `gpt-6.1-sol/high`；运行时型号/档位未独立核实 |
| 初始真实Git基线 | `ff614e4e2605292a9a151ea38a752677f10cd7e7`，HEAD及空索引保持 |
| 上次所审版本/本轮比较基线 | `TASK-20261005-01+r3+af091e94fb4d228f187391f968cc9609017dc17b723ed30c9382dc5ec586a279` |
| 本次固定源码快照 | `TASK-20261005-01+r4+51a7ed70004a63f2a3e1fab60c4933e507879503892c2b96575139435ceebe7d`；内容清单身份，**不是Git提交SHA** |
| 待审SHA/父提交 | 不适用：自动模式未暂存、未提交 |
| 源码ZIP SHA-256 | `7128174f7c40c3663b9cbe51cee1635268f261a031897d4713fcec15ea0c244d` |
| 第0轮审查报告SHA-256 | `b864a2e39c10c83ac237de94bee8983dee65ddacf0d7e9ac44721ebcc1b699d5` |
| 第0轮审查证据ZIP SHA-256 | `f8ee7f671ccc702f34e0f74b033fa8e297ffd32e4894f366875845a8968686f5` |
| 修复计数/停止判断 | 本次实质交回复审计第1轮/上限3；同根因有依据修复失败0/2，未触发停止条件。正常编辑和r3基线预期失败不另计失败 |
| 接收者/发送状态 | 原协调者核验后交原独立评审 `01a11071-2602-77f1-a45c-ba32ec471bbc`；本窗口仅交回材料，未跨窗口发送 |

固定材料：[92文件清单](artifacts/TASK-20261005-01-r4-manifest.json)、[源码ZIP](artifacts/TASK-20261005-01-r4-source.zip)、[r3→r4差异](artifacts/TASK-20261005-01-r3-to-r4.patch)、[真实HEAD→r4业务差异](artifacts/TASK-20261005-01-head-to-r4-business.patch)、[证据ZIP](artifacts/TASK-20261005-01-r4-evidence.zip)、[交付索引及最终哈希](artifacts/TASK-20261005-01-r4-delivery.json)。报告与证据ZIP自身哈希集中于交付索引，避免循环自引用。

源码包在 `workspace/` 保存实际源码、测试、锁定依赖声明及适用只读材料；包含r3报告和第0轮审查报告，不包含真实库、金融原响应、凭据、缓存、依赖安装目录或整套运行环境。文件模式和逐文件哈希已核验；无删除或重命名。清单保留任务开始及r0/r1/r2/r3来源指纹。status相对r3和本轮开始的差异均来自协调者，本窗口只读并保留；其他规划文档增量继续按原归属处理，HEAD累计README差异不能全部归为本轮。

## 2. 根因与最小修复

M01-R01是累计首版增加导航、抽取旧资料组件后的生命周期回归。PDF正文读取中切离002245页，原清理闭包中的 `pdfUrl` 仍为空，卸载又未改变 `pdfGeneration`，于是正文完成后仍创建URL。已卸载组件不再运行下一次URL清理effect，资源继续持有。没有错版显示证据，也未测量原生堆增长数值。

本轮相对r3只修改三份开发文件：

- [LegacySliceView.tsx](../../apps/desktop/src/LegacySliceView.tsx)：新增独立挂载effect的卸载清理，递增PDF代次。保留现有URL所属effect、读取后的代次校验与回收、关闭和选择切换处理；不改导航、PDF来源或读取接口。
- [evidence_read.test.mjs](../../apps/desktop/scripts/evidence_read.test.mjs)：保留原迟到响应测试，新增4项真实生产组件回调/清理测试，使用标准可读且可撤销的Blob URL。卸载后不重新运行effect；断言先于夹具清理，夹具最终释放只用于测试恢复，不能替代产品回收。
- [README](../../README.md#验证入口)：沿用V-FE命令，补充PDF卸载、关闭和切换覆盖说明。

没有金融契约、Python、Rust、CSS、权限、依赖或其他业务改动，没有扩大需求。已有PDF的URL回收仍由原effect承担；新增卸载代次防护同时保护body完成前及URL创建后、组件接收前两个边界。

## 3. R01关闭条件证据

### 3.1 修复前失败与修复后通过

修改前使用第0轮审查探针读取原r3生产组件，源码SHA为 `fa5f9ab6d2855794f084eb000ae007957b3d3d088aa579877692759de1731e4d`。执行所有卸载清理后再完成正文，生产逻辑创建1个URL、回收0个，真实URL仍可读取。结果 `REPRODUCED` 见证据ZIP的 `probe-pdf-unmount-r3.cjs`、`probe-r3-result.json`；探针最终主动释放残留URL。

新增同一组回归再运行于从固定r3源码ZIP解压的副本，5项中3项通过、2项按预期失败，命令退出1。失败项为“body读取中卸载不创建URL”和“URL创建后接收前卸载立即回收”；日志 `r3-regression-expected-failure.log`。此副本使用旧生产组件、当前新增测试及既有依赖引用，未改r3归档；临时副本及依赖引用已清理。重建时从r3源码包解压、放入r4的该测试文件，再运行 `node --test scripts/evidence_read.test.mjs` 即可验证基线失败。

修复版V-FE共43项全部通过，其中PDF5项覆盖：正文读取中卸载后创建0个URL；已有URL卸载时实际撤销且不能继续读取；公告选择切换和关闭回收旧URL、当前原件仍可读；创建后接收前卸载立即撤销；原快照选择改变后拒绝迟到响应。其他市场迟到证据、更新不确定结果恢复、入口及K线几何检查保持。详见 `v-fe.log`。

### 3.2 原生消费者复核

隔离根 `/private/tmp/thewolf-m01-r4-78g9r4un`；Vite5174、本地Python8001、QA标识 `com.thewolf.qa.p5174.p8001`，520×560原生窗口。复用上轮已构建QA二进制与当前前端代码，无Rust变更。只复制获准旧测试根的两公告/60日日线及r3真实指数结果，未访问当前正式库。

本机临时ASGI测试层延迟PDF正文和市场证据，所有POST经鉴权后返回明确合成403且不转发。固定接口内容和两PDF来自获准原件；不伪造金融响应，不把合成拒绝当真实来源失败。注入源代码保存在证据 `local_ui_faults.py`，运行注入和配置已删除。

| 操作及观察 | 固定证据ZIP内文件 |
|---|---|
| 报告body延迟5.5秒，显示“正在读取原件…”时切至市场；本地市场GET发生在正文发送前；正文发送完再回002245页，无迟到原件视图 | `ui-pdf-body-pending-ax.txt`、`ui-pdf-unmounted-ax.txt`、`ui-pdf-reentered-ax.txt`、`local-ui-events.jsonl` |
| 半年度报告及业绩预告正常读取，实际PDF渲染可见，再点击关闭均移除原件视图 | `ui-report/forecast-open-ax.txt`、`ui-report/forecast-scroll-ax.txt`、`ui-report/forecast-closed-ax.txt`、`ui-report.png`、`ui-forecast.png` |
| 已打开PDF后切至市场，再回资料页，无旧原件视图 | `ui-existing-pdf-away-ax.txt`、`ui-existing-pdf-reentered-ax.txt` |
| 两源市场证据延迟5.5秒，在“读取固定原件…”时切至资料页；旧响应完成后返回市场，无迟到证据面板 | `ui-market-evidence-pending/away/reentered-ax.txt`、`local-ui-events.jsonl` |
| 旧更新收到本地合成拒绝后，仅GET核对；等待120秒截止仍禁止重复更新，点击“核对结果”得到“未发现新的更新任务”，恢复人工按钮；全程仅1个POST且未转发 | `ui-update-uncertain/deadline/resolved-ax.txt`、`local-ui-events.jsonl` |

表内斜杠表示同前缀各独立文件，实际文件名见ZIP。实际报告第7物理页和预告第1页可读，AX包含本地Blob地址及原文，截图已人工查看。两原件SHA分别为 `71409583d1d8ce18a49951d2d3079faea8e35a5df8473020f1723a3777eaefdc`、`d3a5bb349f74f1acb1da17607a877564a969d17eceb39d3d08bedd5bb7d3de51`。

`check_ui.py` 对保存的AX及请求时序断言通过，见 `ui-verification.json`。原生证据支持阅读/关闭及切页消费者行为；URL资源归属由上述确定性真实Blob URL回归证明，**没有原生heap测量**，不以“未显示迟到PDF”单独证明资源泄漏已修复。

## 4. 验证与未执行项

所测业务代码与r4固定快照匹配，使用项目已有锁定依赖；未安装或升级依赖。以下为coding自检，不是独立审查。

| 入口/工作目录/实际命令 | 结果 |
|---|---|
| 修复前复现，仓库根：`node /private/tmp/thewolf-m01-r4-78g9r4un/evidence/probe-pdf-unmount-r3.cjs` | 修改前退出0且结果为REPRODUCED，真实r3缺陷确认 |
| 固定r3对照，仓库根：`node --test /private/tmp/thewolf-m01-r4-78g9r4un/repro-r3/apps/desktop/scripts/evidence_read.test.mjs` | 预期退出1，5项3通过2失败；临时路径已清理，重建方法见§3.1 |
| V-FE，`apps/desktop`：`node --test scripts/evidence_read.test.mjs scripts/index_view.test.cjs scripts/update_recovery.test.cjs scripts/start_daily.test.mjs` | 43项通过，`v-fe.log` |
| V-FE构建，`apps/desktop`：`npm run build` | 类型检查及构建通过，`v-build.log` |
| V-UI，`apps/desktop`：`npm run dev -- --host 127.0.0.1 --port 5174 --strictPort`；临时QA包5174/8001及CUA原生操作 | §3.2全部观察通过，`vite.log`、`native.log`、AX/截图及 `ui-verification.json` |
| 原生证据自检，仓库根：`python3 /private/tmp/thewolf-m01-r4-78g9r4un/evidence/check_ui.py` | 时序、两个PDF、重入/迟到保护及唯一拦截POST通过 |
| 快照，仓库根：`python3 /private/tmp/thewolf-m01-r4-78g9r4un/evidence/verify_snapshot.py docs/test-reports/artifacts` | 92文件哈希/模式及ZIP CRC通过，最终结果见 `snapshot-verification.json` |
| V-DOC，仓库根：`python3 /private/tmp/thewolf-m01-r4-78g9r4un/evidence/check_docs.py` | README/本报告的本地链接、锚点、围栏、空白及Git工作区/暂存差异检查通过，`vdoc-result.json` |
| 恢复，仓库根：`python3 /private/tmp/thewolf-m01-r4-78g9r4un/evidence/restore.py` | 六端口、代理摘要、原输入、旧报告及HEAD/索引/账本保持，见 `restoration.json` |

没有重复57项Python、回环API/父EOF、金融真实采集/1040值校核、旧东财兼容与离线重启：本轮仅组件卸载防护和FE测试/说明，相关后端及金融内容未变；沿用[r3报告](TASK-20261005-01-r3-tencent.md)及[首次独立审查](TASK-20261005-01-review.md)对应固定版本证据。未重跑全部宽窗UI矩阵，局部修复无布局修改，本轮实际窄窗消费者已检查。Python分发、五年/估值/PIT、正式启用、用户验收及发布均未执行，保持原范围。

## 5. 恢复、预算与剩余事项

开始已记录HEAD、空索引、92份源码/依赖及旧报告和全部已有归档指纹、六端口、代理脱敏摘要、共享账本及QA持久路径不存在的基线。原输入根指纹在 `input-fingerprints.json`；测试只操作独立副本。上回合因用量限制中断，用户要求继续后从原现场接续，未重新采集或重复已通过前端检查，没有换模型或新建窗口。

完成后通过原生退出触发父EOF、停止本轮Vite；桌面/uvicorn/获取进程无残留，5173/8000/5174/8001/5184/8014均无监听。仅删除本轮开始不存在且创建时间匹配的QA专用WebKit/Caches，Preferences/SavedState仍不存在；临时QA包、sitecustomize、fault-mode、pycache、r3对照副本及其依赖引用均移除。代理/原输入根/旧报告和归档/HEAD及空索引保持；正式库未访问。仅保留无活动进程引用的测试数据副本与必要证据。**未恢复项：无。**

首次清理已完成，但恢复断言将协调者并发status更新误列为不允许差异；核对确认其归属后修正核验名单，再完整复核通过，不回退或写入status。最终快照重新收录该只读依赖，所测业务代码未变，不新增测试轮次。证据见 `restoration.json` 与最终 `snapshot-verification.json`。

共享账本字节保持，SHA `8010f55c7f05d850c6ab25331a45238ff1de863eab245ff52873e1a112adcc4a`，累计**7job/8次/158,887字节**。本轮新增金融来源请求0；最后1job/4次/66,949,977字节继续仅留独立审查。P01的28次、腾讯候选1次/71,252字节、诊断2/2及外部自述尝试另列，旧失败不清零。

必要脚本、摘要、日志及截图已归档，不承诺临时目录永久存在。重建时解压r4源码至新隔离目录，核对清单/模式，使用锁定依赖和README命令；证据脚本本机ROOT/测试路径须替换，原生复核需要与上述哈希匹配的获准测试输入。缺少原件时如实记录，不以合成文件顶替真实PDF。

本次开发侧没有剩余材料或环境阻塞，M01-R01待独立关闭。历史M01-V01已由协调者按r3关闭，V02/V03、ODATA01/OUI01原结论不改写；O01/O02/O04和用户验收保持各自边界。Git未暂存、未提交、未amend/reset/push/部署。

下一步一句话入口：**“按《TASK-20261005-01 · r4 PDF卸载修复交接》核对r4固定快照、r3新增差异和累计范围，执行第1轮独立复审并复核M01-R01全部关闭条件。”** 原协调者核验后复用原独立评审窗口，本窗口不自行发送、创建新审查或修改审查报告。
