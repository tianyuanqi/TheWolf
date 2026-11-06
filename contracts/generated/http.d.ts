/** 自动生成：只修改 contracts/openapi.yaml，禁止手工修补。 */
export interface paths {
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["health"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflighthealth"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/session/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["sessionReady"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightsessionReady"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["indexSeriesReady"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightindexSeriesReady"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["indexSeriesCatalog"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightindexSeriesCatalog"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/operations/{request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: components["schemas"]["RequestId"];
            };
            cookie?: never;
        };
        get: operations["indexSeriesOperationResult"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightindexSeriesOperationResult"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/{index_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        get: operations["currentIndexSeries"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightcurrentIndexSeries"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/{index_id}/snapshots/{snapshot_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        get: operations["fixedIndexSeries"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightfixedIndexSeries"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/{index_id}/snapshots/{snapshot_id}/evidence/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
                object_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        get: operations["indexSeriesEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightindexSeriesEvidence"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/{index_id}/range": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        get: operations["indexSeriesRange"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightindexSeriesRange"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/{index_id}/update": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        get: operations["indexSeriesStatus"];
        put?: never;
        /** @description POST必须携带精确许可Origin；空JSON对象且最多4096字节。五元身份(instance/config/request/operation/index)重复只回放首次回执，跨身份复用409，不透明重试写入。 */
        post: operations["startIndexSeries"];
        delete?: never;
        options: operations["preflightindexSeriesStatus"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/index-series/{index_id}/snapshots/{snapshot_id}/calculations": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        get: operations["indexSeriesCalculations"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightindexSeriesCalculations"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["marketActivityReady"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightmarketActivityReady"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/operations/{request_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: components["schemas"]["RequestId"];
            };
            cookie?: never;
        };
        get: operations["marketActivityOperation"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightmarketActivityOperation"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/{series_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            cookie?: never;
        };
        get: operations["currentMarketActivity"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightcurrentMarketActivity"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/{series_id}/snapshots/{activity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        get: operations["fixedMarketActivity"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightfixedMarketActivity"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/{series_id}/snapshots/{activity_id}/calculations": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        get: operations["marketActivityCalculations"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightmarketActivityCalculations"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/{series_id}/snapshots/{activity_id}/evidence/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
                object_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        get: operations["marketActivityEvidence"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightmarketActivityEvidence"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/market-activity/{series_id}/update": {
        parameters: {
            query?: never;
            header?: never;
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            cookie?: never;
        };
        get?: never;
        put?: never;
        post: operations["startMarketActivity"];
        delete?: never;
        options: operations["preflightstartMarketActivity"];
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/overview-update/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get: operations["overviewUpdateStatus"];
        put?: never;
        post?: never;
        delete?: never;
        options: operations["preflightOverviewUpdateStatus"];
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        Health: {
            /** @constant */
            status: "ok";
            /** @constant */
            service: "thewolf-local-service";
            /** @constant */
            storage: "sqlite";
        };
        /** @description 内容或观察SHA-256；不是job ID或Git提交。 */
        ObjectId: string;
        Day: string;
        /** @description 原十进制点位字符串；单位与精度引用既有指数数据约定，不作浮点转换。 */
        Point: string;
        Percent: string;
        EvidenceRef: {
            object_id: components["schemas"]["ObjectId"];
            locator: string;
        };
        Bar: {
            trade_date: components["schemas"]["Day"];
            open: components["schemas"]["Point"];
            high: components["schemas"]["Point"];
            low: components["schemas"]["Point"];
            close: components["schemas"]["Point"];
            evidence_refs: components["schemas"]["EvidenceRef"][];
        };
        SourceRow: {
            trade_date: components["schemas"]["Day"];
            open: components["schemas"]["Point"];
            high: components["schemas"]["Point"];
            low: components["schemas"]["Point"];
            close: components["schemas"]["Point"];
            locator: string;
            raw_values: {
                open: string;
                high: string;
                low: string;
                close: string;
            } & {
                [key: string]: string;
            };
        };
        /** @enum {string} */
        Source: "eastmoney" | "tencent" | "csindex";
        Evidence: {
            source: components["schemas"]["Source"];
            object_id: components["schemas"]["ObjectId"];
            url: string;
            rows: components["schemas"]["SourceRow"][];
        };
        TencentSourceContract: {
            /** @constant */
            date_selection: "exclude earlier rows; reject later, duplicate or unordered dates; retain original array index";
            /** @constant */
            identity_basis: "PLAN-P01 official factsheet; H00300/N00300 excluded";
            /** @constant */
            normalization: "decimal-two-places-v1";
            /** @constant */
            publication_time: "unknown";
            /** @constant */
            request_qfq_semantics: "SDK compatibility parameter; price index day only";
            sources: {
                csindex: string;
                tencent: string;
            };
            /** @constant */
            tencent_branch: "day";
            unused_fields: string[];
            /** @constant */
            version: "csi300-tencent-exact-ohlc-v2";
        };
        SourceContract: components["schemas"]["TencentSourceContract"];
        Summary: {
            close: components["schemas"]["Point"];
            trade_date: components["schemas"]["Day"];
            daily_change_pct: components["schemas"]["Percent"] | null;
            reason: "first_row_without_previous_close" | null;
            /** @constant */
            formula_version: "adjacent-expected-close-pct-half-up-v1";
            input_refs: {
                close: components["schemas"]["Point"];
                trade_date: components["schemas"]["Day"];
                evidence_refs: components["schemas"]["EvidenceRef"][];
            }[];
        };
        RetrievalSource: {
            source: components["schemas"]["Source"];
            object_id: components["schemas"]["ObjectId"];
            url: string;
            started_at: string;
            completed_at: string;
            published_at: null;
        };
        Retrieval: {
            observed_at: string;
            snapshot_id: components["schemas"]["ObjectId"];
            sources: components["schemas"]["RetrievalSource"][];
        };
        CompletionBasis: {
            coverage: string[];
            limits: string;
            rule: string;
            sources: {
                sha256: string;
                url: string;
            }[];
            version: string;
        };
        Instrument: {
            /** @constant */
            code: "000300";
            /** @constant */
            frequency: "daily";
            /** @constant */
            id: "csi:000300:price";
            /** @constant */
            name: "沪深300";
            /** @constant */
            provider: "中证";
            /** @constant */
            return_type: "price";
        };
        Window: {
            start: components["schemas"]["Day"];
            end: components["schemas"]["Day"];
            /** @constant */
            expected_count: 260;
            /** @constant */
            actual_count: 260;
        };
        IndexView: {
            bars: components["schemas"]["Bar"][];
            calendar_dates: components["schemas"]["Day"][];
            completion_basis: components["schemas"]["CompletionBasis"];
            evidence: components["schemas"]["Evidence"][];
            instrument: components["schemas"]["Instrument"];
            /** @constant */
            pit_grade: "latest_only";
            /** @constant */
            schema_version: "csi300-price-snapshot-v1";
            source_contract: components["schemas"]["SourceContract"];
            summary: components["schemas"]["Summary"];
            /** @constant */
            timezone: "Asia/Shanghai";
            /** @constant */
            unit: "点";
            window: components["schemas"]["Window"];
            snapshot_id: components["schemas"]["ObjectId"];
            observation_id: components["schemas"]["ObjectId"];
            retrieval: components["schemas"]["Retrieval"];
        };
        UpdateRequest: Record<string, never>;
        Ready: {
            /** @constant */
            status: "ready";
            /** @constant */
            service_id: "thewolf-local-service";
            service_version: string;
            /** @constant */
            contract_version: "2.0.0";
            contract_sha256: components["schemas"]["PublicDigest"];
            instance_id: components["schemas"]["PublicInstanceId"];
            data_scope_id: components["schemas"]["PublicDigest"];
            config_id: components["schemas"]["PublicDigest"];
            /** @constant */
            identity_format: "wolf-config-v2";
        };
        /** @constant */
        InternalError: "Internal Server Error";
        IndexEvidence: {
            snapshot_id: components["schemas"]["ObjectId"];
            observation_id: components["schemas"]["ObjectId"];
            source: components["schemas"]["Source"];
            object_id: components["schemas"]["ObjectId"];
            url: string;
            rows: components["schemas"]["SourceRow"][];
            retrieval: components["schemas"]["RetrievalSource"];
            verification: string;
            unused_fields: string[];
            text_preview: string;
            preview_truncated: boolean;
        };
        PublicInstanceId: string;
        PublicDigest: string;
        RequestId: string;
        BoundaryError400: {
            detail: {
                /** @enum {string} */
                code: "invalid_headers" | "connection_context_required" | "connection_context_invalid" | "invalid_preflight";
                message: string;
            };
        };
        BoundaryError403: {
            detail: {
                /** @enum {string} */
                code: "bad_host" | "bad_origin" | "bad_fetch_metadata" | "client_marker_required" | "update_disabled" | "index_update_disabled";
                message: string;
            };
        };
        BoundaryError404: {
            detail: {
                /** @enum {string} */
                code: "route_not_found";
                message: string;
            };
        };
        BoundaryError405: {
            detail: {
                /** @enum {string} */
                code: "method_not_allowed";
                message: string;
            };
        };
        BoundaryError409: {
            detail: {
                /** @enum {string} */
                code: "connection_context_mismatch" | "request_id_conflict";
                message: string;
            };
        };
        BoundaryError415: {
            detail: {
                /** @enum {string} */
                code: "unsupported_media_type";
                message: string;
            };
        };
        BoundaryError422: {
            detail: {
                /** @enum {string} */
                code: "invalid_request";
                message: string;
            };
        };
        BoundaryError503: {
            detail: {
                /** @enum {string} */
                code: "operation_capacity_exceeded";
                message: string;
            };
        };
        /** @enum {string} */
        IndexSeriesId: "csi:000300:price" | "sse:000001:price" | "csi:000852:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price";
        /** @enum {string} */
        IndexSeriesSource: "csindex" | "cnindex" | "eastmoney";
        /** @enum {string} */
        IndexSeriesSourcePolicy: "index-csindex-eastmoney-exact-v1" | "index-cnindex-eastmoney-rounding-aware-v1";
        /** @description 官方原值以十进制字符串保留两位或四位；深圳四位值仅核验时HALF_UP到两位，不改写存储或计算输入。 */
        IndexSeriesPoint: string;
        IndexSeriesRawPoint: string;
        IndexSeriesRawPriceFields: {
            open: components["schemas"]["IndexSeriesRawPoint"];
            high: components["schemas"]["IndexSeriesRawPoint"];
            low: components["schemas"]["IndexSeriesRawPoint"];
            close: components["schemas"]["IndexSeriesRawPoint"];
        };
        IndexSeriesComparisonFields: {
            open: components["schemas"]["Point"];
            high: components["schemas"]["Point"];
            low: components["schemas"]["Point"];
            close: components["schemas"]["Point"];
        };
        /** @enum {string} */
        IndexSeriesField: "open" | "high" | "low" | "close";
        IndexSeriesNetworkPolicy: {
            max_attempts: number;
            max_bytes: number;
            /** @constant */
            max_response_bytes: 1048576;
            /** @constant */
            min_host_interval_seconds: 5;
            /** @constant */
            deadline_seconds: 45;
        };
        IndexSeriesPolicy: {
            /** @constant */
            feature_version: "index-series-v2";
            /** @constant */
            catalog_version: "index-catalog-v1";
            /** @constant */
            calendar_version: "cn-indices-sse-szse-2023-2026-v1";
            /** @constant */
            window_years: 3;
            source_policy_versions: components["schemas"]["IndexSeriesSourcePolicy"][];
            network: components["schemas"]["IndexSeriesNetworkPolicy"];
            periodic?: components["schemas"]["OverviewPeriodicPolicy"];
        };
        IndexSeriesReady: {
            /** @constant */
            status: "ready";
            /** @constant */
            service_id: "thewolf-local-service";
            service_version: string;
            /** @constant */
            contract_version: "2.0.0";
            contract_sha256: components["schemas"]["PublicDigest"];
            instance_id: components["schemas"]["PublicInstanceId"];
            data_scope_id: components["schemas"]["PublicDigest"];
            config_id: components["schemas"]["PublicDigest"];
            /** @constant */
            identity_format: "wolf-index-config-v2";
            /** @constant */
            feature_version: "index-series-v2";
            write_indices: components["schemas"]["IndexSeriesId"][];
            startup_indices: components["schemas"]["IndexSeriesId"][];
            policy: components["schemas"]["IndexSeriesPolicy"];
        };
        IndexSeriesCatalogEntry: {
            index_id: components["schemas"]["IndexSeriesId"];
            code: string;
            name: string;
            full_name: string | null;
            /** @enum {string} */
            provider: "csindex" | "cnindex";
            /** @constant */
            return_type: "price";
            /** @constant */
            frequency: "daily";
            aliases: string[];
            /** @enum {integer} */
            storage_decimals: 2 | 4;
            source_policy_version: components["schemas"]["IndexSeriesSourcePolicy"];
            capabilities: {
                /** @constant */
                ohlc: "available";
                /** @constant */
                amount: "unavailable";
                /** @constant */
                valuation: "unavailable";
            };
            limitations: string[];
            writable: boolean;
        };
        IndexSeriesCatalog: {
            /** @constant */
            catalog_version: "index-catalog-v1";
            query: string | null;
            resolved_index_id: components["schemas"]["IndexSeriesId"] | null;
            indices: components["schemas"]["IndexSeriesCatalogEntry"][];
        };
        IndexSeriesInstrument: {
            id: components["schemas"]["IndexSeriesId"];
            code: string;
            name: string;
            full_name: string | null;
            /** @enum {string} */
            provider: "csindex" | "cnindex";
            /** @constant */
            return_type: "price";
            /** @constant */
            frequency: "daily";
        };
        IndexSeriesWindow: {
            /** @constant */
            version: "three-natural-years-before-shanghai-day-v1";
            anchor_date: components["schemas"]["Day"];
            natural_start: components["schemas"]["Day"];
            start: components["schemas"]["Day"];
            end: components["schemas"]["Day"];
            expected_count: number;
            actual_count: number;
        };
        IndexSeriesCalendarSource: {
            /** @enum {integer} */
            year: 2023 | 2024 | 2025 | 2026;
            /** @enum {string} */
            exchange: "sse" | "szse";
            url: string;
            /** @enum {string} */
            evidence_kind: "web_tool_text" | "http_original";
            evidence_sha256: components["schemas"]["ObjectId"];
        };
        IndexSeriesCompletionBasis: {
            /** @constant */
            rule: "exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today";
            /** @constant */
            timezone: "Asia/Shanghai";
            /** @constant */
            exclude_anchor_day: true;
            supported_years: (2023 | 2024 | 2025 | 2026)[];
            sources: components["schemas"]["IndexSeriesCalendarSource"][];
            limitations: string[];
        };
        IndexSeriesVerification: {
            /** @enum {string} */
            mode: "exact" | "rounding_aware";
            /** @enum {string} */
            primary_source: "csindex" | "cnindex";
            /** @constant */
            verification_source: "eastmoney";
            /** @constant */
            comparison_decimals: 2;
            comparison_rounding: "ROUND_HALF_UP" | null;
            /** @constant */
            result: "matched";
            limitations: string[];
        };
        IndexSeriesEvidenceRef: {
            source: components["schemas"]["IndexSeriesSource"];
            object_id: components["schemas"]["ObjectId"];
            locator: string;
        };
        IndexSeriesBar: {
            trade_date: components["schemas"]["Day"];
            open: components["schemas"]["IndexSeriesPoint"];
            high: components["schemas"]["IndexSeriesPoint"];
            low: components["schemas"]["IndexSeriesPoint"];
            close: components["schemas"]["IndexSeriesPoint"];
            evidence_refs: components["schemas"]["IndexSeriesEvidenceRef"][];
        };
        IndexSeriesSourceRow: {
            trade_date: components["schemas"]["Day"];
            open: components["schemas"]["IndexSeriesPoint"];
            high: components["schemas"]["IndexSeriesPoint"];
            low: components["schemas"]["IndexSeriesPoint"];
            close: components["schemas"]["IndexSeriesPoint"];
            locator: string;
            raw_values: components["schemas"]["IndexSeriesRawPriceFields"];
            comparison_values: components["schemas"]["IndexSeriesComparisonFields"];
        };
        IndexSeriesEvidence: {
            source: components["schemas"]["IndexSeriesSource"];
            object_id: components["schemas"]["ObjectId"];
            url: string;
            rows: components["schemas"]["IndexSeriesSourceRow"][];
        };
        IndexSeriesSummaryInput: {
            trade_date: components["schemas"]["Day"];
            close: components["schemas"]["IndexSeriesPoint"];
            evidence_refs: components["schemas"]["IndexSeriesEvidenceRef"][];
        };
        IndexSeriesSummary: {
            trade_date: components["schemas"]["Day"];
            close: components["schemas"]["IndexSeriesPoint"];
            daily_change_pct: components["schemas"]["Percent"] | null;
            reason: "first_row_without_previous_close" | null;
            /** @constant */
            formula_version: "adjacent-expected-close-pct-half-up-v1";
            input_refs: components["schemas"]["IndexSeriesSummaryInput"][];
        };
        IndexSeriesRetrievalSource: {
            source: components["schemas"]["IndexSeriesSource"];
            object_id: components["schemas"]["ObjectId"];
            url: string;
            started_at: string;
            completed_at: string;
            published_at: null;
        };
        IndexSeriesRetrieval: {
            index_id: components["schemas"]["IndexSeriesId"];
            snapshot_id: components["schemas"]["ObjectId"];
            sources: components["schemas"]["IndexSeriesRetrievalSource"][];
            observed_at: string;
        };
        IndexSeriesSnapshot: {
            /** @constant */
            schema_version: "index-series-price-snapshot-v2";
            /** @constant */
            catalog_version: "index-catalog-v1";
            instrument: components["schemas"]["IndexSeriesInstrument"];
            source_policy_version: components["schemas"]["IndexSeriesSourcePolicy"];
            /** @constant */
            calendar_version: "cn-indices-sse-szse-2023-2026-v1";
            /** @constant */
            unit: "点";
            /** @constant */
            timezone: "Asia/Shanghai";
            /** @constant */
            pit_grade: "latest_only";
            /** @enum {integer} */
            storage_decimals: 2 | 4;
            window: components["schemas"]["IndexSeriesWindow"];
            calendar_dates: components["schemas"]["Day"][];
            completion_basis: components["schemas"]["IndexSeriesCompletionBasis"];
            verification: components["schemas"]["IndexSeriesVerification"];
            bars: components["schemas"]["IndexSeriesBar"][];
            summary: components["schemas"]["IndexSeriesSummary"];
            evidence: components["schemas"]["IndexSeriesEvidence"][];
            snapshot_id: components["schemas"]["ObjectId"];
            observation_id: components["schemas"]["ObjectId"];
            retrieval: components["schemas"]["IndexSeriesRetrieval"];
        };
        IndexSeriesView: {
            index_id: components["schemas"]["IndexSeriesId"];
            /** @constant */
            format: "v2";
            snapshot: components["schemas"]["IndexSeriesSnapshot"];
        } | {
            /** @constant */
            index_id: "csi:000300:price";
            /** @constant */
            format: "legacy_v1";
            snapshot: components["schemas"]["IndexView"];
        };
        IndexSeriesEvidenceDetail: {
            snapshot_id: components["schemas"]["ObjectId"];
            observation_id: components["schemas"]["ObjectId"];
            source: components["schemas"]["IndexSeriesSource"];
            object_id: components["schemas"]["ObjectId"];
            url: string;
            rows: components["schemas"]["IndexSeriesSourceRow"][];
            retrieval: components["schemas"]["IndexSeriesRetrievalSource"];
            verification: components["schemas"]["IndexSeriesVerification"];
            text_preview: string;
            preview_truncated: boolean;
        };
        IndexSeriesEvidenceView: {
            index_id: components["schemas"]["IndexSeriesId"];
            /** @constant */
            format: "v2";
            evidence: components["schemas"]["IndexSeriesEvidenceDetail"];
        } | {
            /** @constant */
            index_id: "csi:000300:price";
            /** @constant */
            format: "legacy_v1";
            evidence: components["schemas"]["IndexEvidence"];
        };
        IndexSeriesRangeRow: {
            trade_date: components["schemas"]["Day"];
            values: {
                open?: components["schemas"]["IndexSeriesPoint"];
                high?: components["schemas"]["IndexSeriesPoint"];
                low?: components["schemas"]["IndexSeriesPoint"];
                close?: components["schemas"]["IndexSeriesPoint"];
            };
        };
        IndexSeriesRange: {
            index_id: components["schemas"]["IndexSeriesId"];
            /** @enum {string} */
            format: "v2" | "legacy_v1";
            snapshot_id: components["schemas"]["ObjectId"];
            start: components["schemas"]["Day"];
            end: components["schemas"]["Day"];
            fields: components["schemas"]["IndexSeriesField"][];
            /** @constant */
            unit: "点";
            /** @constant */
            pit_grade: "latest_only";
            /** @enum {integer} */
            storage_decimals: 2 | 4;
            coverage: {
                start: components["schemas"]["Day"];
                end: components["schemas"]["Day"];
            };
            rows: components["schemas"]["IndexSeriesRangeRow"][];
        };
        IndexSeriesDifference: {
            date: components["schemas"]["Day"];
            field: components["schemas"]["IndexSeriesField"];
            official_raw: components["schemas"]["IndexSeriesRawPoint"];
            comparison_value: components["schemas"]["Point"];
            eastmoney_raw: components["schemas"]["IndexSeriesRawPoint"];
        };
        IndexSeriesUpdateStatus: {
            index_id: components["schemas"]["IndexSeriesId"];
            job_id: string | null;
            trigger: ("manual" | "startup") | null;
            /** @enum {string} */
            stage: "idle" | "preparing" | "fetching_csindex" | "fetching_cnindex" | "fetching_eastmoney" | "validating" | "publishing" | "completed" | "failed" | "interrupted";
            result: ("business_changed" | "evidence_changed" | "unchanged" | "source_not_ready" | "failed" | "interrupted") | null;
            started_at: string | null;
            finished_at: string | null;
            last_success_at: string | null;
            message: string | null;
            target_start: components["schemas"]["Day"] | null;
            target_end: components["schemas"]["Day"] | null;
            previous_snapshot_id: components["schemas"]["ObjectId"] | null;
            snapshot_id: components["schemas"]["ObjectId"] | null;
            observation_id: components["schemas"]["ObjectId"] | null;
            added_dates: components["schemas"]["Day"][];
            revised_dates: components["schemas"]["Day"][];
            differences: components["schemas"]["IndexSeriesDifference"][];
            enabled: boolean;
        };
        IndexSeriesError: {
            detail: {
                /** @enum {string} */
                code: "index_series_empty" | "index_series_snapshot_not_found" | "index_series_unavailable" | "index_series_invalid" | "index_series_evidence_not_found" | "index_range_invalid" | "coverage_insufficient";
                message: string;
            };
        };
        IndexSeriesRecordedRejection: {
            /** @constant */
            status: 409;
            body: components["schemas"]["IndexSeriesError"];
        };
        /** @constant */
        IndexSeriesOperationKind: "index.series.update";
        IndexSeriesAcceptedOperation: {
            instance_id: components["schemas"]["PublicInstanceId"];
            config_id: components["schemas"]["PublicDigest"];
            request_id: components["schemas"]["RequestId"];
            operation: components["schemas"]["IndexSeriesOperationKind"];
            /** @enum {string} */
            state: "accepted" | "running";
            job_id: string;
            reused_job: boolean;
            business_status: components["schemas"]["IndexSeriesUpdateStatus"];
            rejection: null;
            index_id: components["schemas"]["IndexSeriesId"];
        };
        IndexSeriesOperationResult: {
            instance_id: components["schemas"]["PublicInstanceId"];
            config_id: components["schemas"]["PublicDigest"];
            request_id: components["schemas"]["RequestId"];
            operation: components["schemas"]["IndexSeriesOperationKind"];
            /** @enum {string} */
            state: "accepted" | "running" | "completed" | "failed" | "interrupted" | "rejected" | "unknown";
            job_id: string | null;
            reused_job: boolean | null;
            business_status: components["schemas"]["IndexSeriesUpdateStatus"] | null;
            rejection: components["schemas"]["IndexSeriesRecordedRejection"] | null;
            index_id: components["schemas"]["IndexSeriesId"];
        };
        IndexSeriesCalculationInput: {
            index_id: components["schemas"]["IndexSeriesId"];
            snapshot_id: components["schemas"]["ObjectId"];
            start: components["schemas"]["Day"] | null;
            end: components["schemas"]["Day"];
        };
        IndexSeriesCalculationParameters: {
            /** @enum {string} */
            frequency: "daily" | "weekly" | "monthly";
            /** @enum {string} */
            period: "1" | "5" | "10" | "20" | "30" | "60" | "120" | "180" | "250" | "1y";
        };
        IndexSeriesCalculationScalar: {
            value: string | null;
            reason: ("insufficient_samples" | "missing_previous_close" | "missing_year_baseline") | null;
            /** @enum {string} */
            unit: "%" | "点";
            /** @enum {string} */
            formula_version: "adjacent-expected-close-pct-half-up-v1" | "period-close-pct-half-up-v1" | "trading-window-close-pct-v1" | "natural-year-close-pct-v1" | "close-sma-half-up-4-v1";
            parameters: components["schemas"]["IndexSeriesCalculationParameters"];
            input_ref: components["schemas"]["IndexSeriesCalculationInput"];
        };
        IndexSeriesCalculationBar: {
            period_start: components["schemas"]["Day"];
            period_end: components["schemas"]["Day"];
            start: components["schemas"]["Day"];
            end: components["schemas"]["Day"];
            open: string;
            high: string;
            low: string;
            close: string;
            sample_count: number;
            complete: boolean;
            incomplete_reasons: ("window_start_truncated" | "period_in_progress" | "calendar_unknown")[];
            /** @enum {string} */
            formula_version: "raw-daily-price-v1" | "calendar-ohlc-v1";
            input_ref: components["schemas"]["IndexSeriesCalculationInput"];
            change_pct: components["schemas"]["IndexSeriesCalculationScalar"];
            ma: components["schemas"]["IndexSeriesCalculationScalar"][];
        };
        IndexSeriesCalculationAvailability: {
            /** @enum {integer} */
            period: 5 | 10 | 20 | 30 | 60 | 120 | 180 | 250;
            available: boolean;
            sample_count: number;
            /** @enum {integer} */
            required_count: 5 | 10 | 20 | 30 | 60 | 120 | 180 | 250;
            reason: "insufficient_samples" | null;
        };
        IndexSeriesCalculationSeries: {
            /** @enum {string} */
            frequency: "daily" | "weekly" | "monthly";
            ma_availability: components["schemas"]["IndexSeriesCalculationAvailability"][];
            rows: components["schemas"]["IndexSeriesCalculationBar"][];
        };
        IndexSeriesCalculations: {
            index_id: components["schemas"]["IndexSeriesId"];
            snapshot_id: components["schemas"]["ObjectId"];
            /** @constant */
            formula_version: "index-price-calculations-v1";
            /** @constant */
            calendar_version: "cn-indices-sse-szse-2023-2026-v1";
            anchor_date: components["schemas"]["Day"];
            /** @constant */
            pit_grade: "latest_only";
            /** @constant */
            unit: "点";
            daily: components["schemas"]["IndexSeriesCalculationSeries"];
            weekly: components["schemas"]["IndexSeriesCalculationSeries"];
            monthly: components["schemas"]["IndexSeriesCalculationSeries"];
            performance: {
                day_5: components["schemas"]["IndexSeriesCalculationScalar"];
                day_20: components["schemas"]["IndexSeriesCalculationScalar"];
                day_60: components["schemas"]["IndexSeriesCalculationScalar"];
                year_1: components["schemas"]["IndexSeriesCalculationScalar"];
            };
        };
        IndexSeriesCalculationError: {
            detail: {
                /** @enum {string} */
                code: "index_series_empty" | "index_series_snapshot_not_found" | "index_series_unavailable" | "index_series_invalid" | "index_series_evidence_not_found" | "index_range_invalid" | "coverage_insufficient" | "calculation_parameters_invalid";
                message: string;
            };
        };
        MarketActivityPolicy: {
            version: string;
            binding_version: string;
            window_years: number;
            sources: {
                series: string;
                source: string;
                amount_unit: string;
                amount_quantum: string;
                volume_unit: string | null;
                scope: string;
                gaps: string[];
                admitted: boolean;
                version: string;
            }[];
            network: {
                max_attempts: number;
                max_bytes: number;
                max_response_bytes: number;
                timeout_seconds: number;
                deadline_seconds: number;
                minimum_interval_seconds: number;
                redirects: boolean;
                retries: number;
                max_operation_requests: number;
                budget_cycle: string;
                ledger_version: string;
                ledger_scope: components["schemas"]["ObjectId"] | null;
            };
            parser: {
                version: string;
                max_rows: number;
                xlsx_members: number;
                xlsx_expanded_bytes: number;
                xlsx_cells: number;
            };
        };
        MarketActivityFact: {
            value: string | null;
            /** @enum {string} */
            unit: "股" | "元";
            reason: string | null;
            raw_value: string | null;
            raw_unit: string;
            source_quantum: string;
            object_id: components["schemas"]["ObjectId"] | null;
            locator: string | null;
        };
        MarketActivitySnapshot: components["schemas"]["MarketActivityIndexSnapshot"] | components["schemas"]["MarketActivityMarketSnapshot"] | components["schemas"]["MarketActivityTwoMarketSnapshot"];
        MarketActivityCurrent: {
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            activity_id: components["schemas"]["ObjectId"];
            price_snapshot_id: components["schemas"]["ObjectId"] | null;
            anchor_date: string;
            coverage_start: string;
            coverage_end: string;
            missing_dates: string[];
            observation_id: components["schemas"]["ObjectId"];
        };
        MarketActivityScalar: {
            value: string | null;
            reason: string | null;
            unit: string;
            /** @enum {string} */
            formula_version: "market-activity-calculations-v1" | "market-activity-calculations-sse-szse-v1";
            parameters: {
                field: string;
                frequency: string;
                operation: string;
                period: string;
            };
            input_ref: {
                /** @enum {string} */
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
                price_snapshot_id: components["schemas"]["ObjectId"] | null;
                start: string | null;
                end: string;
            };
            complete: boolean;
            incomplete_reasons: string[];
        };
        MarketActivityCalculations: {
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            activity_id: components["schemas"]["ObjectId"];
            price_snapshot_id: components["schemas"]["ObjectId"] | null;
            /** @enum {string} */
            formula_version: "market-activity-calculations-v1" | "market-activity-calculations-sse-szse-v1";
            /** @constant */
            pit_grade: "latest_only";
            series: {
                /** @enum {string} */
                frequency: "daily" | "weekly" | "monthly";
                /** @enum {string} */
                field: "volume" | "amount";
                rows: {
                    start: string;
                    end: string;
                    period_start: string;
                    period_end: string;
                    sample_count: number;
                    total: components["schemas"]["MarketActivityScalar"];
                    change_pct: components["schemas"]["MarketActivityScalar"];
                    ma: components["schemas"]["MarketActivityScalar"][];
                }[];
                ma_availability: {
                    period: number;
                    available: boolean;
                    sample_count: number;
                    required_count: number;
                    reason: string | null;
                }[];
            }[];
            comparisons: {
                day_5: {
                    baseline: components["schemas"]["MarketActivityScalar"];
                    comparison: components["schemas"]["MarketActivityScalar"];
                    sample_count: number;
                };
                day_20: {
                    baseline: components["schemas"]["MarketActivityScalar"];
                    comparison: components["schemas"]["MarketActivityScalar"];
                    sample_count: number;
                };
                day_60: {
                    baseline: components["schemas"]["MarketActivityScalar"];
                    comparison: components["schemas"]["MarketActivityScalar"];
                    sample_count: number;
                };
                year_1: {
                    baseline: components["schemas"]["MarketActivityScalar"];
                    comparison: components["schemas"]["MarketActivityScalar"];
                    sample_count: number;
                };
            } | null;
        };
        MarketActivityEvidence: {
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            activity_id: components["schemas"]["ObjectId"];
            object_id: components["schemas"]["ObjectId"];
            source: string;
            url: string;
            published_at: null;
            content_base64: string;
            byte_length: number;
            price_snapshot_id: components["schemas"]["ObjectId"] | null;
            observations: components["schemas"]["MarketActivityObservation"][];
        };
        MarketActivityOperation: {
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            request_id: components["schemas"]["RequestId"];
            config_id: components["schemas"]["PublicDigest"];
            instance_id: components["schemas"]["PublicInstanceId"];
            target: string;
            signature: components["schemas"]["ObjectId"];
            /** @enum {string} */
            state: "preparing" | "completed" | "failed" | "interrupted";
            activity_id: components["schemas"]["ObjectId"] | null;
            reason: string | null;
            recovered_from_instance: components["schemas"]["PublicInstanceId"] | null;
            observation_id: components["schemas"]["ObjectId"] | null;
        };
        MarketActivityUpdateBody: {
            price_snapshot_id: components["schemas"]["ObjectId"];
            expected_activity_id: components["schemas"]["ObjectId"] | null;
        } | {
            anchor_date: string;
            expected_activity_id: components["schemas"]["ObjectId"] | null;
        };
        MarketActivityError: {
            detail: {
                code: string;
                message: string;
            };
        };
        MarketActivityReady: {
            /** @constant */
            service_id: "thewolf-local-service";
            service_version: string;
            /** @constant */
            contract_version: "2.0.0";
            contract_sha256: components["schemas"]["PublicDigest"];
            data_scope_id: components["schemas"]["PublicDigest"];
            /** @constant */
            identity_format: "wolf-activity-config-v1";
            /** @constant */
            feature_version: "market-activity-v1";
            config_id: components["schemas"]["PublicDigest"];
            price_index_config_id: components["schemas"]["PublicDigest"];
            activity_scope_id: components["schemas"]["PublicDigest"];
            series: ("sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse")[];
            write_series: ("sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse")[];
            startup_series: ("sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse")[];
            blocked_series: {
                /** @enum {string} */
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                evidence_id: components["schemas"]["ObjectId"];
                /** @constant */
                reason: "source_withdrawn";
            }[];
            policy: components["schemas"]["MarketActivityPolicy"];
            instance_id: components["schemas"]["PublicInstanceId"];
            /** @constant */
            status: "ready";
            market_anchor_date: string;
            market_anchors?: components["schemas"]["MarketActivityAnchors"];
        };
        MarketActivityIndexSnapshot: {
            /** @constant */
            schema_version: "activity-facts-v1";
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover";
            activity_id: components["schemas"]["ObjectId"];
            price_snapshot_id: components["schemas"]["ObjectId"] | null;
            anchor_date: string;
            window: components["schemas"]["IndexSeriesWindow"];
            calendar_version: string;
            calendar_dates: string[];
            source_policy_version: string;
            parser_version: string;
            /** @constant */
            pit_grade: "latest_only";
            /** @constant */
            currency: "CNY";
            source_scope: string;
            /** @constant */
            source_revision_relation: "unknown";
            source_revision_id: null;
            binding: {
                version: string;
                price_object_id: components["schemas"]["ObjectId"];
                activity_object_id: components["schemas"]["ObjectId"];
                /** @enum {string} */
                relation: "same_source_object" | "different_source_objects";
                /** @constant */
                comparison: "exact_available_values_match";
                rows: {
                    trade_date: string;
                    price_locator: string;
                    activity_locator: string;
                }[];
            } | null;
            sources: {
                source: string;
                object_id: components["schemas"]["ObjectId"];
                url: string;
            }[];
            rows: {
                trade_date: string;
                volume: components["schemas"]["MarketActivityFact"];
                amount: components["schemas"]["MarketActivityFact"];
            }[];
            completion_basis: components["schemas"]["IndexSeriesCompletionBasis"];
            observations: components["schemas"]["MarketActivityObservation"][];
        };
        MarketActivityMarketSnapshot: {
            /** @constant */
            schema_version: "activity-facts-v1";
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover";
            activity_id: components["schemas"]["ObjectId"];
            price_snapshot_id: components["schemas"]["ObjectId"] | null;
            anchor_date: string;
            window: components["schemas"]["IndexSeriesWindow"];
            calendar_version: string;
            calendar_dates: string[];
            source_policy_version: string;
            parser_version: string;
            /** @constant */
            pit_grade: "latest_only";
            /** @constant */
            currency: "CNY";
            source_scope: string;
            /** @constant */
            source_revision_relation: "unknown";
            source_revision_id: null;
            binding: {
                version: string;
                price_object_id: components["schemas"]["ObjectId"];
                activity_object_id: components["schemas"]["ObjectId"];
                /** @enum {string} */
                relation: "same_source_object" | "different_source_objects";
                /** @constant */
                comparison: "exact_available_values_match";
                rows: {
                    trade_date: string;
                    price_locator: string;
                    activity_locator: string;
                }[];
            } | null;
            sources: {
                source: string;
                object_id: components["schemas"]["ObjectId"];
                url: string;
            }[];
            rows: {
                trade_date: string;
                components: {
                    sse: components["schemas"]["MarketActivityFact"][];
                    szse: components["schemas"]["MarketActivityFact"][];
                    bse: components["schemas"]["MarketActivityFact"][];
                };
            }[];
            completion_basis: components["schemas"]["IndexSeriesCompletionBasis"] | components["schemas"]["ThreeMarketCompletionBasis"];
            market_calendars: {
                sse: string[] | null;
                szse: string[] | null;
                bse: string[] | null;
            };
            observations: components["schemas"]["MarketActivityObservation"][];
        };
        MarketActivityObservedSource: {
            source: string;
            object_id: components["schemas"]["ObjectId"];
            url: string;
            started_at: string;
            completed_at: string;
            published_at: null;
        };
        MarketActivityObservation: {
            /** @enum {string} */
            series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            activity_id: components["schemas"]["ObjectId"];
            price_snapshot_id: components["schemas"]["ObjectId"] | null;
            observation_id: components["schemas"]["ObjectId"];
            request_id: components["schemas"]["RequestId"];
            sources: components["schemas"]["MarketActivityObservedSource"][];
        };
        MarketActivityTwoMarketSnapshot: {
            /** @constant */
            schema_version: "activity-facts-v1";
            /** @constant */
            series_id: "cn-a-turnover-sse-szse";
            activity_id: components["schemas"]["ObjectId"];
            price_snapshot_id: null;
            anchor_date: string;
            window: components["schemas"]["IndexSeriesWindow"];
            calendar_version: string;
            calendar_dates: string[];
            source_policy_version: string;
            parser_version: string;
            /** @constant */
            pit_grade: "latest_only";
            /** @constant */
            currency: "CNY";
            source_scope: string;
            /** @constant */
            source_revision_relation: "unknown";
            source_revision_id: null;
            binding: null;
            sources: {
                source: string;
                object_id: components["schemas"]["ObjectId"];
                url: string;
            }[];
            rows: {
                trade_date: string;
                components: {
                    sse: components["schemas"]["MarketActivityFact"][];
                    szse: components["schemas"]["MarketActivityFact"][];
                };
            }[];
            completion_basis: components["schemas"]["IndexSeriesCompletionBasis"];
            market_calendars: {
                sse: string[] | null;
                szse: string[] | null;
            };
            observations: components["schemas"]["MarketActivityObservation"][];
        };
        OverviewPeriodicPolicy: {
            /** @constant */
            version: "overview-periodic-v1";
            /** @constant */
            timezone: "Asia/Shanghai";
            /** @constant */
            check_time: "07:00";
            daily_requests: number;
            daily_bytes: number;
            monthly_requests: number;
            monthly_bytes: number;
            /** @constant */
            charging: "response-limit-no-refund";
            /** @constant */
            ledger_version: "overview-periodic-ledger-v1";
            scope_id: string;
        };
        ThreeMarketCalendarSource: {
            /** @enum {integer} */
            year: 2023 | 2024 | 2025 | 2026;
            /** @enum {string} */
            exchange: "sse" | "szse" | "bse";
            url: string;
            /** @enum {string} */
            evidence_kind: "web_tool_text" | "http_original";
            evidence_sha256: components["schemas"]["ObjectId"];
        };
        ThreeMarketCompletionBasis: {
            /** @constant */
            rule: "exchange_weekdays_excluding_announced_full_day_closures_before_shanghai_today";
            /** @constant */
            timezone: "Asia/Shanghai";
            /** @constant */
            exclude_anchor_day: true;
            supported_years: (2023 | 2024 | 2025 | 2026)[];
            sources: components["schemas"]["ThreeMarketCalendarSource"][];
            limitations: string[];
        };
        MarketActivityAnchors: {
            sse_szse: string | null;
            sse_szse_bse: string | null;
        };
        /** @enum {string} */
        MarketActivitySeriesId: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
        BusinessError: {
            detail: {
                code: string;
                message: string;
            };
        };
        OverviewUpdateStatus: {
            revision: number;
            /** @enum {string} */
            state: "idle" | "running" | "failed" | "blocked";
            reason: string | null;
            market_anchor_date: string;
            server_day: string;
            next_check_at: string;
            resume_at: string | null;
            daily: components["schemas"]["OverviewBudgetCounter"];
            monthly: components["schemas"]["OverviewBudgetCounter"];
            reserved: components["schemas"]["OverviewBudgetCounter"];
            warning: boolean;
            daily_resets_at: string;
            monthly_resets_at: string;
            market_anchors?: components["schemas"]["MarketActivityAnchors"];
        };
        OverviewBudgetCounter: {
            requests: number;
            bytes: number;
        };
        MarketActivityDescriptor: {
            endpoint: string;
            /** @constant */
            service_id: "thewolf-local-service";
            service_version: string;
            /** @constant */
            contract_version: "2.0.0";
            contract_sha256: components["schemas"]["PublicDigest"];
            data_scope_id: components["schemas"]["PublicDigest"];
            /** @constant */
            identity_format: "wolf-activity-config-v1";
            /** @constant */
            feature_version: "market-activity-v1";
            config_id: components["schemas"]["PublicDigest"];
            price_index_config_id: components["schemas"]["PublicDigest"];
            activity_scope_id: components["schemas"]["PublicDigest"];
            series: ("sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse")[];
            write_series: ("sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse")[];
            startup_series: ("sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse")[];
            blocked_series: {
                /** @enum {string} */
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                evidence_id: components["schemas"]["ObjectId"];
                /** @constant */
                reason: "source_withdrawn";
            }[];
            policy: components["schemas"]["MarketActivityPolicy"];
        };
        IndexSeriesDescriptor: {
            endpoint: string;
            /** @constant */
            service_id: "thewolf-local-service";
            service_version: string;
            /** @constant */
            contract_version: "2.0.0";
            contract_sha256: components["schemas"]["PublicDigest"];
            data_scope_id: components["schemas"]["PublicDigest"];
            config_id: components["schemas"]["PublicDigest"];
            /** @constant */
            identity_format: "wolf-index-config-v2";
            /** @constant */
            feature_version: "index-series-v2";
            write_indices: components["schemas"]["IndexSeriesId"][];
            startup_indices: components["schemas"]["IndexSeriesId"][];
            policy: components["schemas"]["IndexSeriesPolicy"];
        };
    };
    responses: never;
    parameters: {
        ClientMarker: "1";
        ExpectedInstance: components["schemas"]["PublicInstanceId"];
        ExpectedConfig: components["schemas"]["PublicDigest"];
        RequestId: components["schemas"]["RequestId"];
    };
    requestBodies: never;
    headers: {
        /** @description Actual serving process; required after successful binding, including business errors. */
        ResponseInstance: components["schemas"]["PublicInstanceId"];
        /** @description Frozen serving config; required after successful binding, including business errors. */
        ResponseConfig: components["schemas"]["PublicDigest"];
        NoStore: "no-store";
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    health: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 公开存活探针，不读取金融数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
            /** @description Target boundary rejection; before business I/O. */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Target boundary rejection; before business I/O. */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Target boundary rejection; before business I/O. */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description Unhandled error; no diagnostic paths; client treats write result as unknown. */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflighthealth: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "600";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    sessionReady: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 当前实现响应 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Ready"];
                };
            };
            /** @description Target boundary rejection; before business I/O. */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Target boundary rejection; before business I/O. */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Target boundary rejection; before business I/O. */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 当前实现响应 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightsessionReady: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "600";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesReady: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesReady"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightindexSeriesReady: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesCatalog: {
        parameters: {
            query?: {
                query?: string;
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesCatalog"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightindexSeriesCatalog: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesOperationResult: {
        parameters: {
            query: {
                instance_id: components["schemas"]["PublicInstanceId"];
                config_id: components["schemas"]["PublicDigest"];
                operation: components["schemas"]["IndexSeriesOperationKind"];
                index_id: components["schemas"]["IndexSeriesId"];
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                request_id: components["schemas"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesOperationResult"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightindexSeriesOperationResult: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                request_id: components["schemas"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    currentIndexSeries: {
        parameters: {
            query?: {
                snapshot_id?: components["schemas"]["ObjectId"];
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesView"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightcurrentIndexSeries: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    fixedIndexSeries: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesView"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightfixedIndexSeries: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesEvidence: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
                object_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesEvidenceView"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightindexSeriesEvidence: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
                object_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesRange: {
        parameters: {
            query: {
                start: components["schemas"]["Day"];
                end: components["schemas"]["Day"];
                fields?: string;
                snapshot_id?: components["schemas"]["ObjectId"];
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesRange"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightindexSeriesRange: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesStatus: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesUpdateStatus"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    startIndexSeries: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
                "X-Wolf-Request-Id": components["parameters"]["RequestId"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateRequest"];
            };
        };
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            202: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesAcceptedOperation"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            415: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError415"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            503: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError503"];
                };
            };
        };
    };
    preflightindexSeriesStatus: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET" | "POST";
                "Access-Control-Request-Headers": string;
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    indexSeriesCalculations: {
        parameters: {
            query: {
                formula_version: "index-price-calculations-v1";
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesCalculations"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesCalculationError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesCalculationError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"] | components["schemas"]["IndexSeriesCalculationError"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightindexSeriesCalculations: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                index_id: components["schemas"]["IndexSeriesId"];
                snapshot_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    marketActivityReady: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityReady"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightmarketActivityReady: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    marketActivityOperation: {
        parameters: {
            query: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                request_id: components["schemas"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityOperation"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightmarketActivityOperation: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                request_id: components["schemas"]["RequestId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    currentMarketActivity: {
        parameters: {
            query?: {
                price_snapshot_id?: components["schemas"]["ObjectId"];
                anchor_date?: string;
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityCurrent"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightcurrentMarketActivity: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    fixedMarketActivity: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivitySnapshot"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightfixedMarketActivity: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    marketActivityCalculations: {
        parameters: {
            query: {
                formula_version: "market-activity-calculations-v1" | "market-activity-calculations-sse-szse-v1";
            };
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityCalculations"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightmarketActivityCalculations: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    marketActivityEvidence: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
                object_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityEvidence"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightmarketActivityEvidence: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
                activity_id: components["schemas"]["ObjectId"];
                object_id: components["schemas"]["ObjectId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    startMarketActivity: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
                "X-Wolf-Request-Id": components["parameters"]["RequestId"];
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarketActivityUpdateBody"];
            };
        };
        responses: {
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityOperation"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError400"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError403"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            404: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError404"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            415: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError415"];
                };
            };
            /** @description B量额身份校验后的响应；来源缺口不代表有效数据。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MarketActivityError"] | components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightstartMarketActivity: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "POST";
                "Access-Control-Request-Headers": string;
            };
            path: {
                series_id: "sse:000001:price" | "szse:399001:price" | "szse:399006:price" | "sse:000688:price" | "cn-a-turnover" | "cn-a-turnover-sse-szse";
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
    overviewUpdateStatus: {
        parameters: {
            query?: never;
            header: {
                "X-Wolf-Client": components["parameters"]["ClientMarker"];
                "X-Wolf-Expected-Instance": components["parameters"]["ExpectedInstance"];
                "X-Wolf-Expected-Config": components["parameters"]["ExpectedConfig"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewUpdateStatus"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            400: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            403: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            409: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IndexSeriesError"] | components["schemas"]["BoundaryError409"];
                };
            };
            /** @description 新指数特性响应；身份已接受的业务响应携带实例与新配置摘要。 */
            422: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError422"];
                };
            };
            /** @description 未处理异常不泄露内部资料；写入结果不能据此推定回滚。 */
            500: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Wolf-Instance": components["headers"]["ResponseInstance"];
                    "X-Wolf-Config": components["headers"]["ResponseConfig"];
                    [name: string]: unknown;
                };
                content: {
                    "text/plain": components["schemas"]["InternalError"];
                };
            };
        };
    };
    preflightOverviewUpdateStatus: {
        parameters: {
            query?: never;
            header: {
                Origin: string;
                "Access-Control-Request-Method": "GET";
                "Access-Control-Request-Headers": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Valid metadata-only preflight. No body or business I/O. */
            204: {
                headers: {
                    "Access-Control-Allow-Origin"?: string;
                    "Access-Control-Allow-Methods"?: string;
                    "Access-Control-Allow-Headers"?: string;
                    "Access-Control-Max-Age"?: "0";
                    Vary?: "Origin, Access-Control-Request-Method, Access-Control-Request-Headers";
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Malformed preflight. */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError400"];
                };
            };
            /** @description Host, Origin or metadata denied. */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError403"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError404"];
                };
            };
            /** @description Preflight route/method fallback; no business I/O. */
            405: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoundaryError405"];
                };
            };
        };
    };
}
