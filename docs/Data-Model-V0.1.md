# Data Model V0.1

概念对齐：2026-10-04。本文件为逻辑 schema 与约束设计，**不是已运行的数据库迁移**。现有存储继续按已验收切片运行；下文旧 P0/P1/P2 表示原提案的能力分组，不再表示必须在某个 V0.x 一次建齐。实际所需结构按 [PRD](PRD-V0.1.md) 和 [路线图](Implementation-Plan-V0.1.md) 分阶段确定。

首批市场/指标需要的时间序列与未来论点概念在此说明语义；新字段、表、存储引擎和迁移方案须由对应实施设计确定。本轮不建立它们。

## 1. 全局约定

- 内部 ID 使用无业务含义的 UUID；证券代码只是有时效的外部标识。公司主体 `issuer_id` 与上市证券 `instrument_id` 分离，转板/换代码不生成假公司。
- 时间戳以 UTC 保存，展示以 Asia/Shanghai 或指标原生时区；同时保留源字符串与时间精度。交易日、报告期用 DATE，不把它们直接当发布时间。
- 金额记录原生币种与单位；股票数量按股，商品按明确克/千克/磅/桶或合约单位，禁止把所有资产统一当作股或人民币。比率统一小数（5% 存 0.05），收益率差显示百分点或基点，比值显示倍数；指数点位单列。源单位与转换规则版本同时保留。原始价格/金额优先 decimal，派生分析可 float64，但保留计算精度说明。
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
| `instrument` | PK instrument_id；issuer_id FK（适用时）、asset_type、currency | 区分A股、港股、指数、商品合约等；代码不能做全库主键，宏观统计序列不强造公司主体 |
| `instrument_identity_version` | PK version_id；instrument_id FK、exchange、symbol、name、list_date、delist_date、valid_from,to、时间字段 | 同来源同证券有效区间不重叠；历史代码解析带日期 |
| `trading_session` | PK calendar_id+trade_date+version_id；is_open、open_at、close_at、时间字段 | 周末/临时休市可版本化 |
| `instrument_status_version` | PK version_id；instrument_id、status、effective_from,to、时间字段 | suspended/delisted/ST 等分开；用于预期行数计算 |
| `taxonomy` / `sector` | PK taxonomy_id+version；sector_id、parent_id、classification_level | 行业/概念分类型；规则是否互斥明确 |
| `membership_version` | PK version_id；instrument_id、sector_id、effective_from,to、weight、时间字段 | 历史有效时间与何时公布分开；无历史则起于首次确认，不回填伪成员 |
| `focus_tag` | PK instrument_id+tag；created_at、updated_at | 标签集合，不存仓位成本 |
| `research_project` | PK project_id；issuer_id、status、questions、archive_policy、created_at | 一个主体可有多个研究主题 |
| `research_report` | PK report_id；project_id、content_path、context_json、snapshot_id、tool_registry_version、model_info、created_at | 保存 prompt 模板版本、运行参数、引用；报告不可被最新重生成静默覆盖 |

需要逐股计算市场统计时，按历史存续状态保存计算所需 `universe_definition` 与 `universe_snapshot`，不能以今天名单回算过去或遗漏退市样本。直接采用来源汇总时保存其统计范围与原始发布，不冒称已取得逐股全集。两种路径不要求先建设全市场长期个股库。

## 4. 结构化金融事实（逻辑契约，物理存储待按需选择）

每条记录公共字段：`record_version_id, source_id, batch_id, published_at?, public_available_at?, first_seen_at, retrieved_at, pit_grade, contract_version, quality_flags`。记录更新采用 append 新版本，查询视图做版本选择。

| 数据集 | 业务键 | 核心字段 |
|---|---|---|
| `equity_daily` | instrument_id + trade_date + session_scope | open/high/low/close、reference_close、volume_shares、amount_native、currency；raw 未复权，原金额单位另存；这是演进概念，不重命名现有字段 |
| `daily_metrics` | instrument_id + trade_date + metric_basis | turnover_float、turnover_free、total_shares、float_shares、free_shares、total_mv、float_mv、pe、pe_ttm、pb、dividend_yield_ttm |
| `adjustment_factor` | instrument_id + effective_date + method_id | factor、anchor_rule、provider_method_version；保留历史可用性 |
| `corporate_action` | instrument_id + action_id | action_type、announcement_at、record_date、ex_date、payment_date、cash_per_share、share_ratio、status；按所选证券需要接入可得事件以核验复权 |
| `index_daily` | instrument_id + trade_date | OHLC、amount（若支持）、return_type、currency |
| `market_metric`（派生） | universe_id + trade_date + metric_id + input_snapshot_id + algorithm_version | value、unit、eligible_count、observed_count、missing_count、params、pit_mode |
| `sector_metric`（派生） | sector_id + trade_date + metric_id + input_snapshot_id + membership_snapshot_id | value、denominator、coverage、taxonomy_version |

若数据规模证明需要批量 Parquet，物理布局候选为 dataset/year/month，内部按 trade_date、instrument_id 排序；单个版本文件目标 64–256 MiB，实际按回填基准调整。每日小增量允许小文件，后台合并；不为每只股票每天创建一个文件。修订只替换相关分区版本的有效清单，而非全库覆盖。

### 4.1 复权与价格

存未复权价格及独立因子，不永久保存三份全量 K 线。图表复权明确 method 和 anchor_date；例如供应商方法允许时，锚定价 `P(t) × F(t) / F(anchor)`。PIT 模式要求锚点不晚于 as_of 且因子版本本身可知，未来除权因子不能混入。

供应商因子可能有不同的现金分红再投资语义，不能跨源拼接。源 `reference_close` 可能已按除权处理，不能当作前一条 raw close；单日涨跌与宽度采用明确的可比昨收口径。复权后的价格用于趋势比较，不能无说明地代替真实成交价计算市值。

### 4.2 成交、宽度与行业口径

默认 universe 是指定日期存续的沪深京普通 A 股；ETF、B 股、债券、基金不纳入。成交口径 `session_scope` 明确是否包含盘后固定价格交易、大宗等；未实测前不将不同范围的供应商与交易所总额强制对齐。

- 市场成交额：可保存可靠来源的同口径汇总及发布依据；本地计算时对同一全集和交易口径求和并保存必要输入。两者分清 provider-reported 与 computed。A股/港股分别计价；展示可核实覆盖，来源未提供的 expected 不伪造。
- 涨跌家数：有有效可比昨收且当日交易的证券分为上涨、下跌、平盘；新股无可比昨收、停牌、缺数分别列出。上涨占比以有效分类的证券数为分母，缺失不进入平盘。
- 涨跌停：按当日适用的证券/板块/状态规则及价格精度核验收盘状态，无涨跌幅限制的交易日不能套用固定比例。盘中触及与收盘封板分开；涨停/跌停不是与上涨/下跌可再相加的独立分类。
- 成交相对强度：当日成交额 / 前 N 个有效交易日平均成交额，明确不含当日；缺失窗口不自动补零。
- 行业成交占比：行业成员成交额 / 同口径市场成交额。成员未知的证券进“未分类”，互斥一级行业加未分类才可做总和校验。
- 概念板块允许一股多概念，占比总和可能超过 100%，不能画成总和为 100% 的市场饼图，也不能推断净流入。
- 换手率区分无限售流通股与自由流通股口径，单位从源百分数转小数。没有分母不自行猜测。
- 历史分位显示窗口、有效样本量和统计定义。样本不足返回 insufficient_history；对负盈利的 PE 不做“越低越便宜”排序。

供应商 PE/PB/股息率作为 provider-reported 独立指标，不自动视作 PIT。以后本地重算需使用截至当时已披露财务版本、正确股本、分红状态与报告期间。

### 4.3 首批指标与公共序列的语义

首批名单与观察窗口统一见 PRD §5，不在此维护第二份范围表。以下是计算和版本约束：

- 区间涨跌使用可比价格序列；个股复权方法和锚点固定，指数价格收益与全收益不能混接。窗口最高收盘价到当前的跌幅不等于窗口最大回撤，不以最低/最高区间位置替代历史分位。
- 五年估值分位按截至观察时点的同一指数、同一来源方法和有效样本计算，明确排序/并列值算法及实际覆盖。缺失不补零，负盈利或不适用PE不参与“低即便宜”解释。指数换样是历史指数的一部分，不能用当前成分倒算旧值。
- 股债比较：盈利收益率取 `1 / PE_TTM`（倍数PE转小数收益率），与中国10年期国债到期收益率相减；股息率为同口径过去12个月现金股息率，与该国债收益率相减或相除。差值存小数、展示百分点/基点；比值为倍数。PE非正、债券收益率为零等情况需返回不适用原因，不输出无穷大。
- 优先采用编制方的指数整体估值，固定计算用股本/权重、亏损剔除与分红统计方法；不能把个股PE简单平均后称为同一官方指数PE。港股股债比较另定适用债券/币种，不直接套人民币国债基准。
- 社融与M2使用同一统计月份的官方存量同比增速，差值为前者减后者；存量、增量、余额及同比分别识别。优先保留官方可比口径增速及其版本，不用不可比的修订余额自行重算冒充官方值。
- DR007使用日终加权利率，FDR007是另一指标；政策利率按生效区间，HIBOR按已选期限和 fixing 口径。每日收益率与价格、收盘价与结算价分别建序列。
- 参考序列概念记录 `series_id`、发布方、原标的、价格/收益率类型、频率、币种、报价单位、时区/日历与方法版本；观测记录所属日期/期间、值、发布时间、获取时间、修订版本及质量。月度数据不能从所属月末起回填为当时已知每日观测。
- 连续期货记录底层合约、主力/近月选择和换月/调整规则，未经定义的拼接跳变不能解释为真实现货变化。外汇区分在岸、离岸、中间价；黄金现货、基准价和期货不能混为一个字段。

选定序列的五年行情、五年估值和原始发布版本能力分别验证；`latest_revised` 可用于明确标注的历史描述，但不能进入严格当时可知的决定重放。

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

### 5.1 论点与决策对象的演进边界

以下是概念关系与不可变性要求，具体字段、状态机和表结构尚待论点阶段设计：

| 对象 | 最小语义与关系 | 历史约束 |
|---|---|---|
| 原始表达 / Thesis版本 | 原话、作者与记录时间；AI结构化文本另有版本和用户确认状态 | AI不覆盖原话；修订追加；事后回忆标注记录时点 |
| 子问题 / Hypothesis | 分别表达行业、公司受益、估值等可检验判断及竞争解释 | 时间窗口、关键变量、削弱/重研条件可未知；不能强造数值阈值 |
| Evidence关系 | 一证据多判断、支持/反对/背景；来源性质、预测属性、依赖原始来源、冲突与时效 | AI推断不作为独立外部证据；可复算计算保留输入；关联版本固定 |
| Strategy/Policy | 个人规则版本和变更原因 | 已使用旧版本不可覆盖；不预填未经用户确认的仓位上限 |
| State Snapshot | 决策相关资金、持仓/暴露、现金与流动性需求，按实际必要程度记录 | 手工数据来源、记录/适用时点和缺项明确；不是完整账户账本 |
| Decision Snapshot | 多条论点版本、证据/反证/未知、数据快照、规则/状态、备选和不操作、参考基线、AI分析、用户决定、复核安排 | 数据快照只是其中一部分；AI分析与用户决定分开，固定后更正另存 |
| Monitoring Variable | 变量与论点关系，自动/人工/不可观测，更新状态 | 未取得值与论点未变化不同，过期不能当作正常 |
| Review | 与论点版本/决定关联的维持、修改或放弃理由和遗漏 | 当时记录与事后解释分开；不从收益倒推原判断正确 |

既有设计中的 `research_project.issuer_id` 是旧公司研究候选，不能限制跨行业、多公司论点；`claim` 也不等于完整 Thesis。Decision 可以关联多个 Thesis，Thesis 可以经历多次 Decision，Evidence 可以服务多个 Hypothesis。多对多关系的实际实现待设计，不在本轮创建兼容层或迁移。

固定决定所需原话、AI分析、规则/状态和证据依赖进入保护集；运行日志不保存全文提示词的原则，不等于可以丢弃决定中明确需要留存的AI分析。必要内容最小化、发送远程模型的边界在对应阶段确认。

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

## 7. 按阶段选用的扩展概念（不预建全部 schema）

- `financial_fact`：issuer_id、statement_type、metric_id、period_start/end、period_kind（单季/累计/年度/TTM）、consolidation_scope、currency、unit、value、document_version_id、版本时间。重述前后独立，单季从累计差分需两个可知版本且口径一致。
- `revenue_segment`：issuer_id、period、segment_dimension（产品/地区/行业）、segment_name、revenue、share、currency、scope、evidence_id。不同维度不混合加总；未披露占比留空。
- `macro_series` / `macro_observation`（已选序列支持首批看板，更广覆盖后续）：series_id、定义/频率/季调/单位/发布机构；series_id+period+vintage_id、value、发布时间与修订链。累计值、同比、环比各为不同 series。
- `global_series` / `global_observation`（按已选白名单，不整体后置）：市场/交易时区、当地交易日、实际可用时刻、currency、close/value、source、revision。中国收盘研究不能用其后才形成的美股当日收盘。
- `valuation_profile`：profile_id、version、适用行业/公司类型、required_metrics、rule_definition、validation_state。缺行业专属数据时禁用对应解释。
- `event` / `event_study_run`：事件首次公开时刻、研究窗口、证券历史全集、基准、输入快照、算法版本与偏差诊断。
- `trade_import_batch` / `trade_record`（更后期）：导入身份、时区、证券映射、费用、数量与成交价、去重键；仅用于行为分析，不对应交易执行接口。

## 8. 150 GB 预算与生命周期

150 GB 是已确认的本地金融数据软上限。原提案按全市场估算的类别额度、6000只证券示例、全市场30日采样与固定文件大小，不再作为当前容量承诺或前置采集要求。

按已选参考序列、重点证券、来源响应、历史修订、用户研究资料和必要计算输入实测增长；把SQLite/索引、不可变对象、暂存峰值、派生缓存及本机备份一起计算。采样范围随对应任务授权确定，不为估容量先启动全市场采集。

原始结构化响应按用途分类：被固定决定/报告引用、用于来源核验、支持唯一历史版本或计算重放的长期保护；只有可丢弃的诊断响应才适用短期回收。已保存长期历史默认不滚动删除，取消自选不改变该原则。

容量紧张先提示并暂停非必要新增，再由用户决定存储或范围调整；不删除保护依据达标。压缩合并保留内容语义、引用和发布原子性，并预留新旧文件同时存在的空间。具体预警阈值、分类配额与空间性能指标仍待实测和设计。
