# Data Model V0.1

本文件为逻辑 schema 与约束设计，**不是已运行的数据库迁移**。P0 表在 V0.1 实现；P1/P2 仅预留契约，避免把整个未来平台一次建完。

## 1. 全局约定

- 内部 ID 使用无业务含义的 UUID；证券代码只是有时效的外部标识。公司主体 `issuer_id` 与上市证券 `instrument_id` 分离，转板/换代码不生成假公司。
- 时间戳以 UTC 保存，展示以 Asia/Shanghai 或指标原生时区；同时保留源字符串与时间精度。交易日、报告期用 DATE，不把它们直接当发布时间。
- 金额统一元，数量统一股，比率统一小数（5% 存 0.05），币种明确；指数点位单列。源单位与转换规则版本同时保留。原始价格/金额优先 decimal，派生分析可 float64，但保留计算精度说明。
- 缺值用 NULL + reason：not_disclosed、not_applicable、source_missing、not_yet_available、parse_failed。不得用 0、空串或 NaN 混淆语义。
- 时间区间统一左闭右开 `[valid_from, valid_to)`；日期类业务事件映射到其适用交易日。重复的业务键只有在不同 source/version 下才允许共存。
- 所有来源事实可追溯到 source_id、batch_id、record_version_id、获取时刻；所有计算可追溯到输入快照及算法版本。

## 2. 时间模型：不止 published_at

| 字段 | 含义 |
|---|---|
| `event_date` / `period_start,end` | 交易发生日/指标所描述的统计期 |
| `effective_from,to` | 股本、行业归类等实际生效区间 |
| `published_at` | 该具体版本的官方/供应商发布时间；更正值不能沿用初版时间 |
| `publication_precision` | second / minute / date / unknown |
| `public_available_at` | 可用于 PIT 的保守可知时刻，有证据或明确的可用规则 |
| `retrieved_at` | 某次请求实际取回时刻 |
| `first_seen_at` | 本机第一次见到这一内容版本的时刻 |
| `recorded_at` | 该版本提交到本地系统的时刻 |
| `supersedes_version_id` | 此版本替代哪个旧版本；旧版本保留 |
| `pit_grade` | verified_vintage / conservative / observed_only / latest_only |

仅有发布日期时，保守取来源当地下一日 00:00 为 `public_available_at`，并记录规则；因此不能把当天不知何时发布的公告用于当天收盘研究。发布时间完全未知时，最多将 first_seen_at 作为保守可用边界，不能推定早于采集日已存在。

`as_of` 必须是带时区的时间戳。UI 选择日期时，明确区分“交易日收盘视角”和“当日结束后视角”。日线供应商 18:00 才可完整获取的数据，不能无依据地放入 15:00 时刻的严格历史快照。

历史版本选择顺序：先用固定 source_policy 选择同口径来源，再筛 `public_available_at <= as_of`，最后在同一业务键内选该时刻最近可用的版本。`observed_local` 额外要求 first_seen_at 与 recorded_at 均不晚于 as_of；完整重放使用固定 snapshot_id。`latest_revised` 可用最新值，但返回中必须醒目标注事后修订视角。

示例：某 2024 年度利润在 2025-03-20 披露为 100，2025-06-01 更正为 80。查询 2025-04-01 的公开历史应选 100；今天查询最新值选 80。如果只拿到 80，不能给它贴 2025-03-20 的日期参与历史估值。2026 年才首次采集到的可验证原版资料可以用于公众信息重建，但不能称本机在 2025 年已经见过。

没有已验证历史版本的项目，PIT 返回缺失/限制，不能自动切到 latest_revised。历史研究可重建的深度由真实数据决定，schema 本身不能创造历史。

## 3. SQLite 控制与维度表（P0）

下表中 PK 为主键，UK 为唯一约束，FK 为逻辑外键；SQLite 内启用外键，跨 Parquet 引用由发布校验保证。

| 表 | 核心字段与键 | 关键约束/索引 |
|---|---|---|
| `source` | PK source_id；name、type、base_url、authority_rank、terms_url、access_status、adapter_version | provider 与原始发布主体分开；不把第三方 SDK 视为官方来源 |
| `dataset_contract` | PK dataset_id+contract_version；fields、units、business_key、source_policy_version、pit_rules、calendar_id | schema 与口径版本不可原地改写 |
| `issuer` | PK issuer_id；legal_name、country | 名称历史另存版本，不以简称去重 |
| `instrument` | PK instrument_id；issuer_id FK、asset_type、currency | A 股/指数区分；代码不能做全库主键 |
| `instrument_identity_version` | PK version_id；instrument_id FK、exchange、symbol、name、list_date、delist_date、valid_from,to、时间字段 | 同来源同证券有效区间不重叠；历史代码解析带日期 |
| `trading_session` | PK calendar_id+trade_date+version_id；is_open、open_at、close_at、时间字段 | 周末/临时休市可版本化 |
| `instrument_status_version` | PK version_id；instrument_id、status、effective_from,to、时间字段 | suspended/delisted/ST 等分开；用于预期行数计算 |
| `taxonomy` / `sector` | PK taxonomy_id+version；sector_id、parent_id、classification_level | 行业/概念分类型；规则是否互斥明确 |
| `membership_version` | PK version_id；instrument_id、sector_id、effective_from,to、weight、时间字段 | 历史有效时间与何时公布分开；无历史则起于首次确认，不回填伪成员 |
| `focus_tag` | PK instrument_id+tag；created_at、updated_at | 标签集合，不存仓位成本 |
| `research_project` | PK project_id；issuer_id、status、questions、archive_policy、created_at | 一个主体可有多个研究主题 |
| `research_report` | PK report_id；project_id、content_path、context_json、snapshot_id、tool_registry_version、model_info、created_at | 保存 prompt 模板版本、运行参数、引用；报告不可被最新重生成静默覆盖 |

证券全集定义版本单独保存 `universe_definition` 与 `universe_snapshot`：按历史存续状态选成员并固定 instrument_id 集合。历史全市场不能使用今天的上市公司名单，尤其不能遗漏已经退市的样本。

## 4. 结构化金融事实（Parquet P0）

每条记录公共字段：`record_version_id, source_id, batch_id, published_at?, public_available_at?, first_seen_at, retrieved_at, pit_grade, contract_version, quality_flags`。记录更新采用 append 新版本，查询视图做版本选择。

| 数据集 | 业务键 | 核心字段 |
|---|---|---|
| `equity_daily` | instrument_id + trade_date + session_scope | open/high/low/close、reference_close、volume_shares、amount_cny、currency；raw 未复权 |
| `daily_metrics` | instrument_id + trade_date + metric_basis | turnover_float、turnover_free、total_shares、float_shares、free_shares、total_mv、float_mv、pe、pe_ttm、pb、dividend_yield_ttm |
| `adjustment_factor` | instrument_id + effective_date + method_id | factor、anchor_rule、provider_method_version；保留历史可用性 |
| `corporate_action` | instrument_id + action_id | action_type、announcement_at、record_date、ex_date、payment_date、cash_per_share、share_ratio、status；V0.1 接入可得事件以核验复权 |
| `index_daily` | instrument_id + trade_date | OHLC、amount（若支持）、return_type、currency |
| `market_metric`（派生） | universe_id + trade_date + metric_id + input_snapshot_id + algorithm_version | value、unit、eligible_count、observed_count、missing_count、params、pit_mode |
| `sector_metric`（派生） | sector_id + trade_date + metric_id + input_snapshot_id + membership_snapshot_id | value、denominator、coverage、taxonomy_version |

物理布局建议 dataset/year/month，内部按 trade_date、instrument_id 排序；单个版本文件目标 64–256 MiB，实际按回填基准调整。每日小增量允许小文件，后台合并；不为每只股票每天创建一个文件。修订只替换相关分区版本的有效清单，而非全库覆盖。

### 4.1 复权与价格

存未复权价格及独立因子，不永久保存三份全量 K 线。图表复权明确 method 和 anchor_date；例如供应商方法允许时，锚定价 `P(t) × F(t) / F(anchor)`。PIT 模式要求锚点不晚于 as_of 且因子版本本身可知，未来除权因子不能混入。

供应商因子可能有不同的现金分红再投资语义，不能跨源拼接。源 `reference_close` 可能已按除权处理，不能当作前一条 raw close；单日涨跌与宽度采用明确的可比昨收口径。复权后的价格用于趋势比较，不能无说明地代替真实成交价计算市值。

### 4.2 成交、宽度与行业口径

默认 universe 是指定日期存续的沪深京普通 A 股；ETF、B 股、债券、基金不纳入。成交口径 `session_scope` 明确是否包含盘后固定价格交易、大宗等；未实测前不将不同范围的供应商与交易所总额强制对齐。

- 全市场成交额：符合全集与同一交易口径的 amount 求和。展示 observed 与 expected；合法停牌单独计数，未知缺行不能当成停牌。
- 涨跌家数：有有效可比昨收且当日交易的证券分类；新股无可比昨收、停牌、缺数分别列出。分母必须展示。
- 成交相对强度：当日成交额 / 前 N 个有效交易日平均成交额，明确不含当日；缺失窗口不自动补零。
- 行业成交占比：行业成员成交额 / 同口径市场成交额。成员未知的证券进“未分类”，互斥一级行业加未分类才可做总和校验。
- 概念板块允许一股多概念，占比总和可能超过 100%，不能画成总和为 100% 的市场饼图，也不能推断净流入。
- 换手率区分无限售流通股与自由流通股口径，单位从源百分数转小数。没有分母不自行猜测。
- 历史分位显示窗口、有效样本量和统计定义。样本不足返回 insufficient_history；对负盈利的 PE 不做“越低越便宜”排序。

供应商 PE/PB/股息率作为 provider-reported 独立指标，不自动视作 PIT。以后本地重算需使用截至当时已披露财务版本、正确股本、分红状态与报告期间。

## 5. 文档与证据表（SQLite P0 + 文件对象）

| 表 | 核心字段/键 | 约束 |
|---|---|---|
| `document` | PK document_id；document_type、canonical_title | 公告逻辑身份，不随解析改变 |
| `document_subject` | PK document_id+issuer_id+relation | 一份资料可涉及多个公司 |
| `document_origin` | PK origin_id；document_id、source_id、source_document_id、source_url | UK source_id+source_document_id；多镜像可映射同逻辑文档，合并有记录 |
| `document_version` | PK document_version_id；document_id、origin_id、content_hash、published_at、public_available_at、first_seen_at、retrieved_at、report_period、supersedes_version_id | 日期精度、原件状态、时间证明字段不可丢 |
| `stored_object` | PK content_hash；relative_path、mime_type、size_bytes、checksum、created_at | 相同内容物理去重；读取验证；文件不存在即错误 |
| `archive_item` | PK document_version_id；target_level、actual_level、original_hash、text_hash、download_status、parse_status、error_code、pinned | 期望与实际等级独立；被引用版本不可自动降级 |
| `document_chunk` | PK chunk_id；document_version_id、parser_version、block_type、physical_page、printed_label、paragraph_id、offsets、table_coords、text、text_hash | 块属于唯一不可变解析版本；原文偏移与搜索分词偏移分开 |
| `document_search` | FTS5 rowid → chunk_id；title_tokens、body_tokens、entity_tokens | 是派生索引，可重建；过滤版本与时间后方可供 AI 使用 |
| `evidence` | PK evidence_id；kind、document_version_id?、chunk_id?、computation_id?、source_type、source_url、published_at、retrieved_at、locator_json、snippet、snippet_hash | kind 为 doc 时需文档+定位；calc 时需计算；至少一条有效支持路径 |
| `claim` | PK claim_id；project_id?、subject_id、claim_text、claim_type、period、status、supersedes_claim_id?、created_at | 已发布 claim 不可变；更正生成新 ID；关键事实必须关联 evidence；用户笔记单独标识 |
| `claim_evidence` | PK claim_id+evidence_id+relation；review_state | supports/contradicts/context；保留冲突 |
| `report_claim` | PK report_id+claim_id；display_order | 固定报告引用，不随最新 claim 覆盖 |
| `computation` | PK computation_id；tool_version、formula_version、parameters、context、snapshot_id、selection_spec、result_path/hash、unit、created_at | 可复算；涉及输入版本被快照保护 |

`document_version` 的索引入库阶段可能没有 content_hash，后续下载才补充；但必须保留索引观测记录 `document_observation`（origin_id、metadata_hash、observed_at、metadata_json）。若不能证明后来下载的内容就是早期发布版本，PIT 等级保持 observed_only。相同 URL 覆盖更新不能凭旧索引时间得到 verified_vintage。

## 6. 同步、快照与运行表（SQLite P0）

| 表 | 核心字段 | 用途 |
|---|---|---|
| `ingest_batch` | batch_id、dataset/source、slice、idempotency_key、state、row_count、started/committed_at、errors | 状态与发布审计 |
| `data_file` | file_id、path、hash、bytes、dataset_id、partition、schema_version、min/max_date、record_count | 不可变文件登记 |
| `data_snapshot` / `snapshot_file` | snapshot_id、parent_id、created_at、contract_versions；snapshot_id+file_id | 查询只通过 manifest；快照固定输入 |
| `snapshot_dimension` | snapshot_id+entity_type+version_id；source_policy_version | 固定 SQLite 中参与计算的证券、日历、成员及文档版本；避免只有 Parquet 固定而维度漂移 |
| `sync_cursor` | source_id+dataset_id+scope；cursor_json、last_success_at、lookback | 与批次成功发布同事务推进 |
| `coverage_slice` | dataset/source/date/exchange；expected、observed、suspended、missing、quality_state、batch_id | 区分合法无记录与未知缺失 |
| `quality_issue` | issue_id、batch_id、entity_key、check_id、severity、details、resolution | 可隔离与可重试 |
| `job_definition` | job_id、type、schedule、timezone、parameters、enabled | 持久调度配置 |
| `job_run` | run_id、job_id、idempotency_key、state、attempt、lease_until、heartbeat_at、checkpoint、trace_id | 任务恢复与租约 |
| `tool_run` | run_id、tool/version、arguments_hash、context、result_hash、evidence_ids、latency、status | 重放与审计，不默认存全文提示词 |
| `retention_reference` | owner_type/id + object_or_snapshot_id、reason | 保护报告、引用、活动查询、用户固定对象 |
| `schema_migration` | version、checksum、applied_at、backup_id | 迁移与回滚 |

高频索引：job_run(state,next_retry_at)、document_version(document_id,public_available_at)、document_subject(issuer_id)、claim(subject_id)、membership(instrument_id,effective_from)、data_file(dataset_id,partition)。复合唯一和外键是正式实现必需项，不能只依赖应用层判断。

`job_run` 正式字段还包括 `next_retry_at`。已发布 claim 的证据关系也不可原地替换，更正随新 claim ID 保存。快照的文件清单和维度版本在同一控制库事务中发布；报告重放只读取固定版本，不能从“最新公司画像”旁路补充信息。

## 7. 后续扩展 schema（P1/P2，不在 V0.1 全建）

- `financial_fact`：issuer_id、statement_type、metric_id、period_start/end、period_kind（单季/累计/年度/TTM）、consolidation_scope、currency、unit、value、document_version_id、版本时间。重述前后独立，单季从累计差分需两个可知版本且口径一致。
- `revenue_segment`：issuer_id、period、segment_dimension（产品/地区/行业）、segment_name、revenue、share、currency、scope、evidence_id。不同维度不混合加总；未披露占比留空。
- `macro_series` / `macro_observation`：series_id、定义/频率/季调/单位/发布机构；series_id+period+vintage_id、value、发布时间与修订链。累计值、同比、环比各为不同 series。
- `global_series` / `global_observation`：市场/交易时区、当地交易日、实际可用时刻、currency、close/value、source、revision。中国收盘研究不能用其后才形成的美股当日收盘。
- `valuation_profile`：profile_id、version、适用行业/公司类型、required_metrics、rule_definition、validation_state。缺行业专属数据时禁用对应解释。
- `event` / `event_study_run`：事件首次公开时刻、研究窗口、证券历史全集、基准、输入快照、算法版本与偏差诊断。
- `trade_import_batch` / `trade_record`（更后期）：导入身份、时区、证券映射、费用、数量与成交价、去重键；仅用于行为分析，不对应交易执行接口。

## 8. 150 GB 预算与生命周期

以下均为十进制 GB 的规划额度，**不是已经实测的占用或容量承诺**。

| 类别 | 规划额度 | 保留规则 |
|---|---:|---|
| A 股、指数、财务、宏观、全球结构化及版本 | 30 GB | 长期保留；去重压缩，不丢历史事实 |
| 文档索引、项目、引用与控制库 | 8 GB | 长期保留；审计归档有清单 |
| 官方与重点公司原件 | 45 GB | 引用/重点保护；项目体积可配 |
| 解析正文、表格和搜索索引 | 12 GB | 正文引用版本保护；搜索索引可重建 |
| 派生缓存、短期原响应、日志 | 5 GB | 限额轮转；必要计算输入仍保护 |
| staging、合并与升级临时峰值 | 10 GB | 作业前检查；发布完成后清理 |
| 本机增量备份 | 20 GB | 固定清单+增量对象；不得无限复制全库 |
| 增长与紧急余量 | 20 GB | 提前预警 |
| 合计 | **150 GB** | 软上限，满时停采集而非破坏证据 |

容量估算方法：例如用 6,000 只证券作为规划样本数量（不是当前数量声明），每年 250 个交易日，20 年约 3,000 万条股日记录；按每条 150–400 字节仅估日线主表未压缩载荷约 4.5–12 GB。每日指标、历史版本、主键、索引及压缩率需另算；不能据此认定全部数据只占这个体积。

前置验证实际采样至少 30 个交易日全市场及 2 家公司文档，测每条字节数、压缩比、文档均值/长尾、解析膨胀率、版本频率，再以真实记录数估初次回填、日增量和年增量。报告 p50/p95 文档体积，避免少数大型扫描 PDF 冲垮预算。

原始结构化响应默认短期保留供排错；用于关键口径判断的原响应和全部标准化历史版本长期保留。目录扫描总量与对象清单定期对账，索引/WAL/临时文件也要计入。压缩合并至少需要输入和输出并存的空间，不能在满盘时启动合并救急。
