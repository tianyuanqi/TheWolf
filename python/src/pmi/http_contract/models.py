# 自动生成：只修改 contracts/openapi.yaml，禁止手工修补。

from __future__ import annotations

from typing import Dict, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    StrictStr,
)


class Health(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    status: Literal['ok']
    service: Literal['thewolf-local-service']
    storage: Literal['sqlite']


class ObjectId(RootModel[StrictStr]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: StrictStr = Field(
        ...,
        description='内容或观察SHA-256；不是job ID或Git提交。',
        pattern='^[0-9a-f]{64}$(?![\\s\\S])',
    )


class Day(RootModel[StrictStr]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: StrictStr = Field(..., pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}$(?![\\s\\S])')


class Point(RootModel[StrictStr]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: StrictStr = Field(
        ...,
        description='原十进制点位字符串；单位与精度引用既有指数数据约定，不作浮点转换。',
        pattern='^[0-9]+\\.[0-9]{2}$(?![\\s\\S])',
    )


class Percent(RootModel[StrictStr]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: StrictStr = Field(..., pattern='^-?[0-9]+\\.[0-9]{2}$(?![\\s\\S])')


class EvidenceRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    object_id: ObjectId
    locator: StrictStr


class Bar(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    open: Point
    high: Point
    low: Point
    close: Point
    evidence_refs: list[EvidenceRef] = Field(..., max_length=2, min_length=2)


class RawValues(BaseModel):
    model_config = ConfigDict(
        extra='allow',
    )
    __annotations__ = {
        '__pydantic_extra__': Dict[str, StrictStr],
    }
    open: StrictStr
    high: StrictStr
    low: StrictStr
    close: StrictStr


class SourceRow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    open: Point
    high: Point
    low: Point
    close: Point
    locator: StrictStr
    raw_values: RawValues


class Source(RootModel[Literal['eastmoney', 'tencent', 'csindex']]):
    root: Literal['eastmoney', 'tencent', 'csindex']


class Evidence(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: Source
    object_id: ObjectId
    url: StrictStr
    rows: list[SourceRow] = Field(..., max_length=260, min_length=260)


class Sources(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    csindex: StrictStr
    tencent: StrictStr


class TencentSourceContract(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    date_selection: Literal[
        'exclude earlier rows; reject later, duplicate or unordered dates; retain original array index'
    ]
    identity_basis: Literal['PLAN-P01 official factsheet; H00300/N00300 excluded']
    normalization: Literal['decimal-two-places-v1']
    publication_time: Literal['unknown']
    request_qfq_semantics: Literal['SDK compatibility parameter; price index day only']
    sources: Sources
    tencent_branch: Literal['day']
    unused_fields: list[StrictStr]
    version: Literal['csi300-tencent-exact-ohlc-v2']


class SourceContract(RootModel[TencentSourceContract]):
    root: TencentSourceContract


class InputRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    close: Point
    trade_date: Day
    evidence_refs: list[EvidenceRef] = Field(..., max_length=2, min_length=2)


class Summary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    close: Point
    trade_date: Day
    daily_change_pct: Percent | None
    reason: Literal['first_row_without_previous_close'] | None
    formula_version: Literal['adjacent-expected-close-pct-half-up-v1']
    input_refs: list[InputRef] = Field(..., max_length=2, min_length=1)


class RetrievalSource(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: Source
    object_id: ObjectId
    url: StrictStr
    started_at: StrictStr
    completed_at: StrictStr
    published_at: None


class Retrieval(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    observed_at: StrictStr
    snapshot_id: ObjectId
    sources: list[RetrievalSource] = Field(..., max_length=2, min_length=2)


class Source1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    sha256: StrictStr
    url: StrictStr


class CompletionBasis(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    coverage: list[StrictStr]
    limits: StrictStr
    rule: StrictStr
    sources: list[Source1]
    version: StrictStr


class Instrument(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['000300']
    frequency: Literal['daily']
    id: Literal['csi:000300:price']
    name: Literal['沪深300']
    provider: Literal['中证']
    return_type: Literal['price']


class Window(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    start: Day
    end: Day
    expected_count: Literal[260]
    actual_count: Literal[260]


class IndexView(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    bars: list[Bar] = Field(..., max_length=260, min_length=260)
    calendar_dates: list[Day] = Field(..., max_length=260, min_length=260)
    completion_basis: CompletionBasis
    evidence: list[Evidence] = Field(..., max_length=2, min_length=2)
    instrument: Instrument
    pit_grade: Literal['latest_only']
    schema_version: Literal['csi300-price-snapshot-v1']
    source_contract: SourceContract
    summary: Summary
    timezone: Literal['Asia/Shanghai']
    unit: Literal['点']
    window: Window
    snapshot_id: ObjectId
    observation_id: ObjectId
    retrieval: Retrieval


class UpdateRequest(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )


class InternalError(RootModel[Literal['Internal Server Error']]):
    root: Literal['Internal Server Error']


class IndexEvidence(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    snapshot_id: ObjectId
    observation_id: ObjectId
    source: Source
    object_id: ObjectId
    url: StrictStr
    rows: list[SourceRow] = Field(..., max_length=260, min_length=260)
    retrieval: RetrievalSource
    verification: StrictStr
    unused_fields: list[StrictStr]
    text_preview: StrictStr
    preview_truncated: StrictBool


class PublicInstanceId(RootModel[StrictStr]):
    root: StrictStr = Field(
        ...,
        pattern='^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    )


class PublicDigest(RootModel[StrictStr]):
    root: StrictStr = Field(..., pattern='^[0-9a-f]{64}$')


class RequestId(RootModel[StrictStr]):
    root: StrictStr = Field(
        ..., max_length=128, min_length=1, pattern='^[A-Za-z0-9._:-]+$'
    )


class Detail(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal[
        'invalid_headers',
        'connection_context_required',
        'connection_context_invalid',
        'invalid_preflight',
    ]
    message: StrictStr


class BoundaryError400(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail


class Detail1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal[
        'bad_host',
        'bad_origin',
        'bad_fetch_metadata',
        'client_marker_required',
        'update_disabled',
        'index_update_disabled',
    ]
    message: StrictStr


class BoundaryError403(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail1


class Detail2(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['route_not_found']
    message: StrictStr


class BoundaryError404(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail2


class Detail3(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['method_not_allowed']
    message: StrictStr


class BoundaryError405(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail3


class Detail4(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['connection_context_mismatch', 'request_id_conflict']
    message: StrictStr


class BoundaryError409(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail4


class Detail5(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['unsupported_media_type']
    message: StrictStr


class BoundaryError415(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail5


class Detail6(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['invalid_request']
    message: StrictStr


class BoundaryError422(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail6


class Detail7(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal['operation_capacity_exceeded']
    message: StrictStr


class BoundaryError503(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail7


class IndexSeriesId(
    RootModel[
        Literal[
            'csi:000300:price',
            'sse:000001:price',
            'csi:000852:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
        ]
    ]
):
    root: Literal[
        'csi:000300:price',
        'sse:000001:price',
        'csi:000852:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
    ]


class IndexSeriesSource(RootModel[Literal['csindex', 'cnindex', 'eastmoney']]):
    root: Literal['csindex', 'cnindex', 'eastmoney']


class IndexSeriesSourcePolicy(
    RootModel[
        Literal[
            'index-csindex-eastmoney-exact-v1',
            'index-cnindex-eastmoney-rounding-aware-v1',
        ]
    ]
):
    root: Literal[
        'index-csindex-eastmoney-exact-v1', 'index-cnindex-eastmoney-rounding-aware-v1'
    ]


class IndexSeriesPoint(RootModel[StrictStr]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: StrictStr = Field(
        ...,
        description='官方原值以十进制字符串保留两位或四位；深圳四位值仅核验时HALF_UP到两位，不改写存储或计算输入。',
        pattern='^(?:0|[1-9][0-9]*)\\.[0-9]{2}(?:[0-9]{2})?$(?![\\s\\S])',
    )


class IndexSeriesRawPoint(RootModel[StrictStr]):
    model_config = ConfigDict(
        regex_engine="python-re",
    )
    root: StrictStr = Field(
        ..., max_length=40, pattern='^(?:0|[1-9][0-9]*)(?:\\.[0-9]+)?$(?![\\s\\S])'
    )


class IndexSeriesRawPriceFields(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    open: IndexSeriesRawPoint
    high: IndexSeriesRawPoint
    low: IndexSeriesRawPoint
    close: IndexSeriesRawPoint


class IndexSeriesComparisonFields(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    open: Point
    high: Point
    low: Point
    close: Point


class IndexSeriesField(RootModel[Literal['open', 'high', 'low', 'close']]):
    root: Literal['open', 'high', 'low', 'close']


class IndexSeriesNetworkPolicy(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    max_attempts: StrictInt
    max_bytes: StrictInt
    max_response_bytes: Literal[1048576]
    min_host_interval_seconds: Literal[5]
    deadline_seconds: Literal[45]


class Alias(RootModel[StrictStr]):
    root: StrictStr = Field(..., min_length=1)


class Capabilities(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    ohlc: Literal['available']
    amount: Literal['unavailable']
    valuation: Literal['unavailable']


class IndexSeriesCatalogEntry(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        regex_engine="python-re",
    )
    index_id: IndexSeriesId
    code: StrictStr = Field(..., pattern='^[0-9]{6}$(?![\\s\\S])')
    name: StrictStr = Field(..., min_length=1)
    full_name: StrictStr | None
    provider: Literal['csindex', 'cnindex']
    return_type: Literal['price']
    frequency: Literal['daily']
    aliases: list[Alias]
    storage_decimals: Literal[2, 4]
    source_policy_version: IndexSeriesSourcePolicy
    capabilities: Capabilities
    limitations: list[StrictStr]
    writable: StrictBool


class Query(RootModel[StrictStr]):
    root: StrictStr = Field(..., max_length=160)


class IndexSeriesCatalog(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    catalog_version: Literal['index-catalog-v1']
    query: Query | None
    resolved_index_id: IndexSeriesId | None
    indices: list[IndexSeriesCatalogEntry] = Field(..., max_length=6)


class IndexSeriesInstrument(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
        regex_engine="python-re",
    )
    id: IndexSeriesId
    code: StrictStr = Field(..., pattern='^[0-9]{6}$(?![\\s\\S])')
    name: StrictStr = Field(..., min_length=1)
    full_name: StrictStr | None
    provider: Literal['csindex', 'cnindex']
    return_type: Literal['price']
    frequency: Literal['daily']


class IndexSeriesWindow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    version: Literal['three-natural-years-before-shanghai-day-v1']
    anchor_date: Day
    natural_start: Day
    start: Day
    end: Day
    expected_count: StrictInt
    actual_count: StrictInt


class IndexSeriesCalendarSource(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    year: Literal[2023, 2024, 2025, 2026]
    exchange: Literal['sse', 'szse']
    url: StrictStr
    evidence_kind: Literal['web_tool_text', 'http_original']
    evidence_sha256: ObjectId


class IndexSeriesCompletionBasis(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    rule: Literal[
        'exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today'
    ]
    timezone: Literal['Asia/Shanghai']
    exclude_anchor_day: Literal[True]
    supported_years: list[Literal[2023, 2024, 2025, 2026]] = Field(
        ..., max_length=4, min_length=4
    )
    sources: list[IndexSeriesCalendarSource] = Field(..., max_length=8, min_length=8)
    limitations: list[StrictStr]


class IndexSeriesVerification(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    mode: Literal['exact', 'rounding_aware']
    primary_source: Literal['csindex', 'cnindex']
    verification_source: Literal['eastmoney']
    comparison_decimals: Literal[2]
    comparison_rounding: Literal['ROUND_HALF_UP'] | None
    result: Literal['matched']
    limitations: list[StrictStr]


class IndexSeriesEvidenceRef(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: IndexSeriesSource
    object_id: ObjectId
    locator: StrictStr = Field(..., min_length=1)


class IndexSeriesBar(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    open: IndexSeriesPoint
    high: IndexSeriesPoint
    low: IndexSeriesPoint
    close: IndexSeriesPoint
    evidence_refs: list[IndexSeriesEvidenceRef] = Field(..., max_length=2, min_length=2)


class IndexSeriesSourceRow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    open: IndexSeriesPoint
    high: IndexSeriesPoint
    low: IndexSeriesPoint
    close: IndexSeriesPoint
    locator: StrictStr = Field(..., min_length=1)
    raw_values: IndexSeriesRawPriceFields
    comparison_values: IndexSeriesComparisonFields


class IndexSeriesEvidence(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: IndexSeriesSource
    object_id: ObjectId
    url: StrictStr
    rows: list[IndexSeriesSourceRow] = Field(..., min_length=1)


class IndexSeriesSummaryInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    close: IndexSeriesPoint
    evidence_refs: list[IndexSeriesEvidenceRef] = Field(..., max_length=2, min_length=2)


class IndexSeriesSummary(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    close: IndexSeriesPoint
    daily_change_pct: Percent | None
    reason: Literal['first_row_without_previous_close'] | None
    formula_version: Literal['adjacent-expected-close-pct-half-up-v1']
    input_refs: list[IndexSeriesSummaryInput] = Field(..., max_length=2, min_length=1)


class IndexSeriesRetrievalSource(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: IndexSeriesSource
    object_id: ObjectId
    url: StrictStr
    started_at: StrictStr
    completed_at: StrictStr
    published_at: None


class IndexSeriesRetrieval(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    snapshot_id: ObjectId
    sources: list[IndexSeriesRetrievalSource] = Field(..., max_length=2, min_length=2)
    observed_at: StrictStr


class IndexSeriesSnapshot(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    schema_version: Literal['index-series-price-snapshot-v2']
    catalog_version: Literal['index-catalog-v1']
    instrument: IndexSeriesInstrument
    source_policy_version: IndexSeriesSourcePolicy
    calendar_version: Literal['cn-indices-sse-szse-2023-2026-v1']
    unit: Literal['点']
    timezone: Literal['Asia/Shanghai']
    pit_grade: Literal['latest_only']
    storage_decimals: Literal[2, 4]
    window: IndexSeriesWindow
    calendar_dates: list[Day] = Field(..., min_length=1)
    completion_basis: IndexSeriesCompletionBasis
    verification: IndexSeriesVerification
    bars: list[IndexSeriesBar] = Field(..., min_length=1)
    summary: IndexSeriesSummary
    evidence: list[IndexSeriesEvidence] = Field(..., max_length=2, min_length=2)
    snapshot_id: ObjectId
    observation_id: ObjectId
    retrieval: IndexSeriesRetrieval


class IndexSeriesView1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    format: Literal['v2']
    snapshot: IndexSeriesSnapshot


class IndexSeriesView2(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: Literal['csi:000300:price']
    format: Literal['legacy_v1']
    snapshot: IndexView


class IndexSeriesView(RootModel[IndexSeriesView1 | IndexSeriesView2]):
    root: IndexSeriesView1 | IndexSeriesView2


class IndexSeriesEvidenceDetail(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    snapshot_id: ObjectId
    observation_id: ObjectId
    source: IndexSeriesSource
    object_id: ObjectId
    url: StrictStr
    rows: list[IndexSeriesSourceRow] = Field(..., min_length=1)
    retrieval: IndexSeriesRetrievalSource
    verification: IndexSeriesVerification
    text_preview: StrictStr
    preview_truncated: StrictBool


class IndexSeriesEvidenceView1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    format: Literal['v2']
    evidence: IndexSeriesEvidenceDetail


class IndexSeriesEvidenceView2(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: Literal['csi:000300:price']
    format: Literal['legacy_v1']
    evidence: IndexEvidence


class IndexSeriesEvidenceView(
    RootModel[IndexSeriesEvidenceView1 | IndexSeriesEvidenceView2]
):
    root: IndexSeriesEvidenceView1 | IndexSeriesEvidenceView2


class Values(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    open: IndexSeriesPoint | None = None
    high: IndexSeriesPoint | None = None
    low: IndexSeriesPoint | None = None
    close: IndexSeriesPoint | None = None


class IndexSeriesRangeRow(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: Day
    values: Values


class Coverage(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    start: Day
    end: Day


class IndexSeriesRange(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    format: Literal['v2', 'legacy_v1']
    snapshot_id: ObjectId
    start: Day
    end: Day
    fields: list[IndexSeriesField] = Field(..., max_length=4, min_length=1)
    unit: Literal['点']
    pit_grade: Literal['latest_only']
    storage_decimals: Literal[2, 4]
    coverage: Coverage
    rows: list[IndexSeriesRangeRow]


class IndexSeriesDifference(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    date: Day
    field: IndexSeriesField
    official_raw: IndexSeriesRawPoint
    comparison_value: Point
    eastmoney_raw: IndexSeriesRawPoint


class JobId(RootModel[StrictStr]):
    root: StrictStr = Field(..., min_length=1)


class IndexSeriesUpdateStatus(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    job_id: JobId | None
    trigger: Literal['manual', 'startup'] | None
    stage: Literal[
        'idle',
        'preparing',
        'fetching_csindex',
        'fetching_cnindex',
        'fetching_eastmoney',
        'validating',
        'publishing',
        'completed',
        'failed',
        'interrupted',
    ]
    result: (
        Literal[
            'business_changed',
            'evidence_changed',
            'unchanged',
            'source_not_ready',
            'failed',
            'interrupted',
        ]
        | None
    )
    started_at: StrictStr | None
    finished_at: StrictStr | None
    last_success_at: StrictStr | None
    message: StrictStr | None
    target_start: Day | None
    target_end: Day | None
    previous_snapshot_id: ObjectId | None
    snapshot_id: ObjectId | None
    observation_id: ObjectId | None
    added_dates: list[Day]
    revised_dates: list[Day]
    differences: list[IndexSeriesDifference]
    enabled: StrictBool


class Detail8(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal[
        'index_series_empty',
        'index_series_snapshot_not_found',
        'index_series_unavailable',
        'index_series_invalid',
        'index_series_evidence_not_found',
        'index_range_invalid',
        'coverage_insufficient',
    ]
    message: StrictStr


class IndexSeriesError(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail8


class IndexSeriesRecordedRejection(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    status: Literal[409]
    body: IndexSeriesError


class IndexSeriesOperationKind(RootModel[Literal['index.series.update']]):
    root: Literal['index.series.update']


class IndexSeriesAcceptedOperation(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    instance_id: PublicInstanceId
    config_id: PublicDigest
    request_id: RequestId
    operation: IndexSeriesOperationKind
    state: Literal['accepted', 'running']
    job_id: StrictStr = Field(..., min_length=1)
    reused_job: StrictBool
    business_status: IndexSeriesUpdateStatus
    rejection: None
    index_id: IndexSeriesId


class IndexSeriesOperationResult(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    instance_id: PublicInstanceId
    config_id: PublicDigest
    request_id: RequestId
    operation: IndexSeriesOperationKind
    state: Literal[
        'accepted',
        'running',
        'completed',
        'failed',
        'interrupted',
        'rejected',
        'unknown',
    ]
    job_id: JobId | None
    reused_job: StrictBool | None
    business_status: IndexSeriesUpdateStatus | None
    rejection: IndexSeriesRecordedRejection | None
    index_id: IndexSeriesId


class IndexSeriesCalculationInput(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    snapshot_id: ObjectId
    start: Day | None
    end: Day


class IndexSeriesCalculationParameters(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    frequency: Literal['daily', 'weekly', 'monthly']
    period: Literal['1', '5', '10', '20', '30', '60', '120', '180', '250', '1y']


class Value(RootModel[StrictStr]):
    root: StrictStr = Field(
        ..., max_length=64, pattern='^-?[0-9]+\\.[0-9]{2}([0-9]{2})?$'
    )


class IndexSeriesCalculationScalar(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    value: Value | None
    reason: (
        Literal[
            'insufficient_samples', 'missing_previous_close', 'missing_year_baseline'
        ]
        | None
    )
    unit: Literal['%', '点']
    formula_version: Literal[
        'adjacent-expected-close-pct-half-up-v1',
        'period-close-pct-half-up-v1',
        'trading-window-close-pct-v1',
        'natural-year-close-pct-v1',
        'close-sma-half-up-4-v1',
    ]
    parameters: IndexSeriesCalculationParameters
    input_ref: IndexSeriesCalculationInput


class IndexSeriesCalculationBar(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    period_start: Day
    period_end: Day
    start: Day
    end: Day
    open: StrictStr = Field(
        ..., max_length=45, pattern='^[0-9]+\\.[0-9]{2}([0-9]{2})?$'
    )
    high: StrictStr = Field(
        ..., max_length=45, pattern='^[0-9]+\\.[0-9]{2}([0-9]{2})?$'
    )
    low: StrictStr = Field(..., max_length=45, pattern='^[0-9]+\\.[0-9]{2}([0-9]{2})?$')
    close: StrictStr = Field(
        ..., max_length=45, pattern='^[0-9]+\\.[0-9]{2}([0-9]{2})?$'
    )
    sample_count: StrictInt
    complete: StrictBool
    incomplete_reasons: list[
        Literal['window_start_truncated', 'period_in_progress', 'calendar_unknown']
    ] = Field(..., max_length=3)
    formula_version: Literal['raw-daily-price-v1', 'calendar-ohlc-v1']
    input_ref: IndexSeriesCalculationInput
    change_pct: IndexSeriesCalculationScalar
    ma: list[IndexSeriesCalculationScalar] = Field(..., max_length=8)


class IndexSeriesCalculationAvailability(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    period: Literal[5, 10, 20, 30, 60, 120, 180, 250]
    available: StrictBool
    sample_count: StrictInt
    required_count: Literal[5, 10, 20, 30, 60, 120, 180, 250]
    reason: Literal['insufficient_samples'] | None


class IndexSeriesCalculationSeries(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    frequency: Literal['daily', 'weekly', 'monthly']
    ma_availability: list[IndexSeriesCalculationAvailability] = Field(..., max_length=8)
    rows: list[IndexSeriesCalculationBar] = Field(..., max_length=1100)


class Performance(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    day_5: IndexSeriesCalculationScalar
    day_20: IndexSeriesCalculationScalar
    day_60: IndexSeriesCalculationScalar
    year_1: IndexSeriesCalculationScalar


class IndexSeriesCalculations(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    index_id: IndexSeriesId
    snapshot_id: ObjectId
    formula_version: Literal['index-price-calculations-v1']
    calendar_version: Literal['cn-indices-sse-szse-2023-2026-v1']
    anchor_date: Day
    pit_grade: Literal['latest_only']
    unit: Literal['点']
    daily: IndexSeriesCalculationSeries
    weekly: IndexSeriesCalculationSeries
    monthly: IndexSeriesCalculationSeries
    performance: Performance


class Detail9(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: Literal[
        'index_series_empty',
        'index_series_snapshot_not_found',
        'index_series_unavailable',
        'index_series_invalid',
        'index_series_evidence_not_found',
        'index_range_invalid',
        'coverage_insufficient',
        'calculation_parameters_invalid',
    ]
    message: StrictStr


class IndexSeriesCalculationError(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail9


class Source2(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series: StrictStr
    source: StrictStr
    amount_unit: StrictStr
    amount_quantum: StrictStr
    volume_unit: StrictStr | None
    scope: StrictStr
    gaps: list[StrictStr]
    admitted: StrictBool
    version: StrictStr


class Network(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    max_attempts: StrictInt
    max_bytes: StrictInt
    max_response_bytes: StrictInt
    timeout_seconds: StrictInt
    deadline_seconds: StrictInt
    minimum_interval_seconds: StrictInt
    redirects: StrictBool
    retries: StrictInt
    max_operation_requests: StrictInt
    budget_cycle: StrictStr
    ledger_version: StrictStr
    ledger_scope: ObjectId | None


class Parser(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    version: StrictStr
    max_rows: StrictInt
    xlsx_members: StrictInt
    xlsx_expanded_bytes: StrictInt
    xlsx_cells: StrictInt


class MarketActivityPolicy(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    version: StrictStr
    binding_version: StrictStr
    window_years: StrictInt
    sources: list[Source2]
    network: Network
    parser: Parser


class MarketActivityFact(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    value: StrictStr | None
    unit: Literal['股', '元']
    reason: StrictStr | None
    raw_value: StrictStr | None
    raw_unit: StrictStr
    source_quantum: StrictStr
    object_id: ObjectId | None
    locator: StrictStr | None


class MissingDate(RootModel[StrictStr]):
    root: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')


class MarketActivityCurrent(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    activity_id: ObjectId
    price_snapshot_id: ObjectId | None
    anchor_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    coverage_start: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    coverage_end: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    missing_dates: list[MissingDate]
    observation_id: ObjectId


class Parameters(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    field: StrictStr
    frequency: StrictStr
    operation: StrictStr
    period: StrictStr


class Start(RootModel[StrictStr]):
    root: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')


class InputRef1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    activity_id: ObjectId
    price_snapshot_id: ObjectId | None
    start: Start | None
    end: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')


class MarketActivityScalar(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    value: StrictStr | None
    reason: StrictStr | None
    unit: StrictStr
    formula_version: Literal[
        'market-activity-calculations-v1', 'market-activity-calculations-sse-szse-v1'
    ]
    parameters: Parameters
    input_ref: InputRef1
    complete: StrictBool
    incomplete_reasons: list[StrictStr]


class Row(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    start: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    end: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    period_start: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    period_end: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    sample_count: StrictInt
    total: MarketActivityScalar
    change_pct: MarketActivityScalar
    ma: list[MarketActivityScalar]


class MaAvailabilityItem(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    period: StrictInt
    available: StrictBool
    sample_count: StrictInt
    required_count: StrictInt
    reason: StrictStr | None


class Series(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    frequency: Literal['daily', 'weekly', 'monthly']
    field: Literal['volume', 'amount']
    rows: list[Row]
    ma_availability: list[MaAvailabilityItem]


class Day5(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    baseline: MarketActivityScalar
    comparison: MarketActivityScalar
    sample_count: StrictInt


class Day20(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    baseline: MarketActivityScalar
    comparison: MarketActivityScalar
    sample_count: StrictInt


class Day60(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    baseline: MarketActivityScalar
    comparison: MarketActivityScalar
    sample_count: StrictInt


class Year1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    baseline: MarketActivityScalar
    comparison: MarketActivityScalar
    sample_count: StrictInt


class Comparisons(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    day_5: Day5
    day_20: Day20
    day_60: Day60
    year_1: Year1


class MarketActivityCalculations(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    activity_id: ObjectId
    price_snapshot_id: ObjectId | None
    formula_version: Literal[
        'market-activity-calculations-v1', 'market-activity-calculations-sse-szse-v1'
    ]
    pit_grade: Literal['latest_only']
    series: list[Series]
    comparisons: Comparisons | None


class MarketActivityOperation(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    request_id: RequestId
    config_id: PublicDigest
    instance_id: PublicInstanceId
    target: StrictStr
    signature: ObjectId
    state: Literal['preparing', 'completed', 'failed', 'interrupted']
    activity_id: ObjectId | None
    reason: StrictStr | None
    recovered_from_instance: PublicInstanceId | None
    observation_id: ObjectId | None


class MarketActivityUpdateBody1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    price_snapshot_id: ObjectId
    expected_activity_id: ObjectId | None


class MarketActivityUpdateBody2(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    anchor_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    expected_activity_id: ObjectId | None


class MarketActivityUpdateBody(
    RootModel[MarketActivityUpdateBody1 | MarketActivityUpdateBody2]
):
    root: MarketActivityUpdateBody1 | MarketActivityUpdateBody2


class Detail10(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    code: StrictStr
    message: StrictStr


class MarketActivityError(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail10


class BlockedSery(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    evidence_id: ObjectId
    reason: Literal['source_withdrawn']


class CalendarDate(RootModel[StrictStr]):
    root: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')


class Row1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    price_locator: StrictStr
    activity_locator: StrictStr


class Binding(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    version: StrictStr
    price_object_id: ObjectId
    activity_object_id: ObjectId
    relation: Literal['same_source_object', 'different_source_objects']
    comparison: Literal['exact_available_values_match']
    rows: list[Row1]


class Source3(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: StrictStr
    object_id: ObjectId
    url: StrictStr


class Row2(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    volume: MarketActivityFact
    amount: MarketActivityFact


class Row3(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    price_locator: StrictStr
    activity_locator: StrictStr


class Binding1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    version: StrictStr
    price_object_id: ObjectId
    activity_object_id: ObjectId
    relation: Literal['same_source_object', 'different_source_objects']
    comparison: Literal['exact_available_values_match']
    rows: list[Row3]


class Components(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    sse: list[MarketActivityFact] = Field(..., max_length=2, min_length=1)
    szse: list[MarketActivityFact] = Field(..., max_length=2, min_length=1)
    bse: list[MarketActivityFact] = Field(..., max_length=2, min_length=1)


class Row4(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    components: Components


class MarketCalendars(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    sse: list[StrictStr] | None
    szse: list[StrictStr] | None
    bse: list[StrictStr] | None


class MarketActivityObservedSource(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    source: StrictStr
    object_id: ObjectId
    url: StrictStr
    started_at: StrictStr = Field(
        ...,
        pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$',
    )
    completed_at: StrictStr = Field(
        ...,
        pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:Z|[+-]\\d{2}:\\d{2})$',
    )
    published_at: None


class MarketActivityObservation(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    activity_id: ObjectId
    price_snapshot_id: ObjectId | None
    observation_id: ObjectId
    request_id: RequestId
    sources: list[MarketActivityObservedSource] = Field(
        ..., max_length=2200, min_length=1
    )


class Components1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    sse: list[MarketActivityFact] = Field(..., max_length=2, min_length=1)
    szse: list[MarketActivityFact] = Field(..., max_length=2, min_length=1)


class Row5(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    trade_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    components: Components1


class MarketCalendars1(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    sse: list[StrictStr] | None
    szse: list[StrictStr] | None


class MarketActivityTwoMarketSnapshot(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    schema_version: Literal['activity-facts-v1']
    series_id: Literal['cn-a-turnover-sse-szse']
    activity_id: ObjectId
    price_snapshot_id: None
    anchor_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    window: IndexSeriesWindow
    calendar_version: StrictStr
    calendar_dates: list[CalendarDate]
    source_policy_version: StrictStr
    parser_version: StrictStr
    pit_grade: Literal['latest_only']
    currency: Literal['CNY']
    source_scope: StrictStr
    source_revision_relation: Literal['unknown']
    source_revision_id: None
    binding: None
    sources: list[Source3]
    rows: list[Row5]
    completion_basis: IndexSeriesCompletionBasis
    market_calendars: MarketCalendars1
    observations: list[MarketActivityObservation] = Field(..., min_length=1)


class OverviewPeriodicPolicy(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    version: Literal['overview-periodic-v1']
    timezone: Literal['Asia/Shanghai']
    check_time: Literal['07:00']
    daily_requests: StrictInt
    daily_bytes: StrictInt
    monthly_requests: StrictInt
    monthly_bytes: StrictInt
    charging: Literal['response-limit-no-refund']
    ledger_version: Literal['overview-periodic-ledger-v1']
    scope_id: StrictStr = Field(..., pattern='^[a-f0-9]{64}$')


class ThreeMarketCalendarSource(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    year: Literal[2023, 2024, 2025, 2026]
    exchange: Literal['sse', 'szse', 'bse']
    url: StrictStr
    evidence_kind: Literal['web_tool_text', 'http_original']
    evidence_sha256: ObjectId


class ThreeMarketCompletionBasis(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    rule: Literal[
        'exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today'
    ]
    timezone: Literal['Asia/Shanghai']
    exclude_anchor_day: Literal[True]
    supported_years: list[Literal[2023, 2024, 2025, 2026]] = Field(
        ..., max_length=4, min_length=4
    )
    sources: list[ThreeMarketCalendarSource] = Field(..., max_length=12, min_length=12)
    limitations: list[StrictStr]


class MarketActivityAnchors(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    sse_szse: StrictStr | None = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    sse_szse_bse: StrictStr | None = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')


class MarketActivitySeriesId(
    RootModel[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ]
):
    root: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]


class BusinessError(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    detail: Detail10


class OverviewBudgetCounter(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    requests: StrictInt
    bytes: StrictInt


class MarketActivityDescriptor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    endpoint: StrictStr = Field(..., min_length=1)
    service_id: Literal['thewolf-local-service']
    service_version: StrictStr = Field(..., min_length=1)
    contract_version: Literal['2.0.0']
    contract_sha256: PublicDigest
    data_scope_id: PublicDigest
    identity_format: Literal['wolf-activity-config-v1']
    feature_version: Literal['market-activity-v1']
    config_id: PublicDigest
    price_index_config_id: PublicDigest
    activity_scope_id: PublicDigest
    series: list[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ]
    write_series: list[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ]
    startup_series: list[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ] = Field(..., max_length=6)
    blocked_series: list[BlockedSery]
    policy: MarketActivityPolicy


class Ready(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    status: Literal['ready']
    service_id: Literal['thewolf-local-service']
    service_version: StrictStr = Field(..., min_length=1)
    contract_version: Literal['2.0.0']
    contract_sha256: PublicDigest
    instance_id: PublicInstanceId
    data_scope_id: PublicDigest
    config_id: PublicDigest
    identity_format: Literal['wolf-config-v2']


class IndexSeriesPolicy(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    feature_version: Literal['index-series-v2']
    catalog_version: Literal['index-catalog-v1']
    calendar_version: Literal['cn-indices-sse-szse-2023-2026-v1']
    window_years: Literal[3]
    source_policy_versions: list[IndexSeriesSourcePolicy] = Field(
        ..., max_length=2, min_length=2
    )
    network: IndexSeriesNetworkPolicy
    periodic: OverviewPeriodicPolicy | None = None


class IndexSeriesReady(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    status: Literal['ready']
    service_id: Literal['thewolf-local-service']
    service_version: StrictStr = Field(..., min_length=1)
    contract_version: Literal['2.0.0']
    contract_sha256: PublicDigest
    instance_id: PublicInstanceId
    data_scope_id: PublicDigest
    config_id: PublicDigest
    identity_format: Literal['wolf-index-config-v2']
    feature_version: Literal['index-series-v2']
    write_indices: list[IndexSeriesId] = Field(..., max_length=6)
    startup_indices: list[IndexSeriesId] = Field(..., max_length=6)
    policy: IndexSeriesPolicy


class MarketActivityEvidence(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
        'cn-a-turnover-sse-szse',
    ]
    activity_id: ObjectId
    object_id: ObjectId
    source: StrictStr
    url: StrictStr
    published_at: None
    content_base64: StrictStr
    byte_length: StrictInt
    price_snapshot_id: ObjectId | None
    observations: list[MarketActivityObservation] = Field(..., min_length=1)


class MarketActivityReady(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    service_id: Literal['thewolf-local-service']
    service_version: StrictStr = Field(..., min_length=1)
    contract_version: Literal['2.0.0']
    contract_sha256: PublicDigest
    data_scope_id: PublicDigest
    identity_format: Literal['wolf-activity-config-v1']
    feature_version: Literal['market-activity-v1']
    config_id: PublicDigest
    price_index_config_id: PublicDigest
    activity_scope_id: PublicDigest
    series: list[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ]
    write_series: list[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ]
    startup_series: list[
        Literal[
            'sse:000001:price',
            'szse:399001:price',
            'szse:399006:price',
            'sse:000688:price',
            'cn-a-turnover',
            'cn-a-turnover-sse-szse',
        ]
    ] = Field(..., max_length=6)
    blocked_series: list[BlockedSery]
    policy: MarketActivityPolicy
    instance_id: PublicInstanceId
    status: Literal['ready']
    market_anchor_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    market_anchors: MarketActivityAnchors | None = None


class MarketActivityIndexSnapshot(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    schema_version: Literal['activity-facts-v1']
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
    ]
    activity_id: ObjectId
    price_snapshot_id: ObjectId | None
    anchor_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    window: IndexSeriesWindow
    calendar_version: StrictStr
    calendar_dates: list[CalendarDate]
    source_policy_version: StrictStr
    parser_version: StrictStr
    pit_grade: Literal['latest_only']
    currency: Literal['CNY']
    source_scope: StrictStr
    source_revision_relation: Literal['unknown']
    source_revision_id: None
    binding: Binding | None
    sources: list[Source3]
    rows: list[Row2]
    completion_basis: IndexSeriesCompletionBasis
    observations: list[MarketActivityObservation] = Field(..., min_length=1)


class MarketActivityMarketSnapshot(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    schema_version: Literal['activity-facts-v1']
    series_id: Literal[
        'sse:000001:price',
        'szse:399001:price',
        'szse:399006:price',
        'sse:000688:price',
        'cn-a-turnover',
    ]
    activity_id: ObjectId
    price_snapshot_id: ObjectId | None
    anchor_date: StrictStr = Field(..., pattern='^\\d{4}-\\d{2}-\\d{2}$')
    window: IndexSeriesWindow
    calendar_version: StrictStr
    calendar_dates: list[CalendarDate]
    source_policy_version: StrictStr
    parser_version: StrictStr
    pit_grade: Literal['latest_only']
    currency: Literal['CNY']
    source_scope: StrictStr
    source_revision_relation: Literal['unknown']
    source_revision_id: None
    binding: Binding1 | None
    sources: list[Source3]
    rows: list[Row4]
    completion_basis: IndexSeriesCompletionBasis | ThreeMarketCompletionBasis
    market_calendars: MarketCalendars
    observations: list[MarketActivityObservation] = Field(..., min_length=1)


class OverviewUpdateStatus(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    revision: StrictInt
    state: Literal['idle', 'running', 'failed', 'blocked']
    reason: StrictStr | None = Field(..., max_length=100, pattern='^[a-z_]+$')
    market_anchor_date: StrictStr = Field(..., pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    server_day: StrictStr = Field(..., pattern='^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    next_check_at: StrictStr = Field(
        ..., pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$'
    )
    resume_at: StrictStr | None = Field(
        ..., pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$'
    )
    daily: OverviewBudgetCounter
    monthly: OverviewBudgetCounter
    reserved: OverviewBudgetCounter
    warning: StrictBool
    daily_resets_at: StrictStr = Field(
        ..., pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$'
    )
    monthly_resets_at: StrictStr = Field(
        ..., pattern='^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$'
    )
    market_anchors: MarketActivityAnchors | None = None


class IndexSeriesDescriptor(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    endpoint: StrictStr = Field(..., min_length=1)
    service_id: Literal['thewolf-local-service']
    service_version: StrictStr = Field(..., min_length=1)
    contract_version: Literal['2.0.0']
    contract_sha256: PublicDigest
    data_scope_id: PublicDigest
    config_id: PublicDigest
    identity_format: Literal['wolf-index-config-v2']
    feature_version: Literal['index-series-v2']
    write_indices: list[IndexSeriesId] = Field(..., max_length=6)
    startup_indices: list[IndexSeriesId] = Field(..., max_length=6)
    policy: IndexSeriesPolicy


class MarketActivitySnapshot(
    RootModel[
        MarketActivityIndexSnapshot
        | MarketActivityMarketSnapshot
        | MarketActivityTwoMarketSnapshot
    ]
):
    root: (
        MarketActivityIndexSnapshot
        | MarketActivityMarketSnapshot
        | MarketActivityTwoMarketSnapshot
    )
