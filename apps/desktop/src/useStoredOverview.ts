import { useEffect, useRef, useState } from "react";
import type { ApiClient } from "./apiClient";
import { indexConnectionDescriptor, activityConnectionDescriptor } from "./browserHost";
import { IndexSeriesClient } from "./indexSeriesClient";
import { ActivityClient } from "./activityClient";
import { OVERVIEW_INDICES, type OverviewIndexId } from "./indexSeriesTypes";
import { LEGACY_MARKET, type ActivityField, type ActivityDescriptor } from "./activityTypes";
import type { Frequency } from "./indexCalculationTypes";
import type { ChartWindow } from "./OverviewCharts";
import { StoredViews, requestedRange, type Versions, type PriceOverview, type PriceRange, type ActivityRange, type MarketOverview } from "./storedViews";

export type StoredRow = { snapshot?: PriceOverview; performance?: PriceOverview["performance"]; loading: boolean; stale?: boolean; error?: string; empty?: boolean };
export type StoredRows = Partial<Record<OverviewIndexId, StoredRow>>;
type Connected = { owner: string; views: StoredViews; versions: Versions; descriptor?: ActivityDescriptor };
const message = (error: unknown) => error instanceof Error ? error.message : "本地资料暂不可用";

/** 版本元数据、概况与范围各自有代次；迟到结果不能跨连接、范围或固定绑定。 */
export function useStoredOverview({ connection, connectionError, refreshToken, selected, range, frequency, ma, field, activityMA }: {
  connection?: ApiClient; connectionError?: string; refreshToken: number; selected: OverviewIndexId | "three-market";
  range: ChartWindow; frequency: Frequency; ma: number[]; field: ActivityField; activityMA: number[];
}) {
  const owner = `${connection?.expected.config_id ?? ""}:${connection?.instance ?? ""}`;
  const [reload, setReload] = useState(0);
  const [connected, setConnected] = useState<Connected>();
  const [rows, setRows] = useState<StoredRows>({});
  const [market, setMarket] = useState<MarketOverview>();
  const [marketError, setMarketError] = useState<string>();
  const [connectionNotice, setConnectionNotice] = useState<string>();
  const [busy, setBusy] = useState(true);
  const [phase, setPhase] = useState("正在连接本地服务…");
  const generation = useRef(0);
  const priorOwner = useRef("");
  const detailFailed = useRef(false);
  const [detail, setDetail] = useState<{ owner: string; key: string; loading: boolean; price?: PriceRange; activity?: ActivityRange; priceError?: string; activityError?: string }>({ owner: "", key: "", loading: false });

  useEffect(() => {
    const current = ++generation.current, controller = new AbortController();
    detailFailed.current = false;
    let price: IndexSeriesClient | undefined, activity: ActivityClient | undefined, poll: ReturnType<typeof setTimeout> | undefined;
    setConnected(undefined); setConnectionNotice(undefined); setMarketError(undefined); setMarket(undefined); setBusy(Boolean(connection));
    if (priorOwner.current !== owner) { setRows({}); setMarket(undefined); priorOwner.current = owner; }
    else setRows(old => Object.fromEntries(Object.entries(old).map(([id, row]) => [id, { ...row, stale: Boolean(row.snapshot), loading: true }])));
    if (!connection) { setPhase(connectionError ?? "正在连接本地服务…"); return () => controller.abort(); }
    setPhase("正在核对本地连接与已保存版本…");
    const live = () => !controller.signal.aborted && current === generation.current;
    void (async () => {
      const expected = await indexConnectionDescriptor(connection.expected, controller.signal);
      if (!expected) throw new Error("指数连接未配置");
      price = await IndexSeriesClient.connect(expected, connection.instance, controller.signal);
      if (!live()) { price.close(); return; }
      let descriptor: ActivityDescriptor | undefined;
      let contentFailed = false;
      try {
        descriptor = await activityConnectionDescriptor(expected, controller.signal);
        if (descriptor) activity = await ActivityClient.connect(descriptor, price.instance, controller.signal);
      } catch (error) { contentFailed = true; if (live()) setConnectionNotice(message(error)); }
      if (!live()) { activity?.close(); return; }
      const views = new StoredViews(price, activity);
      const versions = await views.versions(controller.signal);
      if (!live()) return;
      setConnected({ owner, views, versions, descriptor });
      setPhase("正在读取概况与所选范围…");
      await Promise.all([
        ...OVERVIEW_INDICES.map(async item => {
          const version = versions.indices.find(value => value.index_id === item.id)?.price;
          if (!version) { if (live()) setRows(old => ({ ...old, [item.id]: { loading: false, empty: true, error: "尚无已保存价格" } })); return; }
          try {
            const snapshot = await views.overview(item.id, version, controller.signal);
            if (live()) setRows(old => ({ ...old, [item.id]: { snapshot, performance: snapshot.performance, loading: false } }));
          } catch (error) { contentFailed = true; if (live()) setRows(old => ({ ...old, [item.id]: { ...old[item.id], loading: false, stale: Boolean(old[item.id]?.snapshot), error: message(error) } })); }
        }),
        (async () => {
          const version = versions.markets.find(value => value.series_id === LEGACY_MARKET)?.activity;
          if (!version || !activity) { if (live()) { setMarket(undefined); setMarketError("尚无已发布市场数据或量额连接不可用"); } return; }
          try { const value = await views.marketOverview(LEGACY_MARKET, version, controller.signal); if (live()) setMarket(value); }
          catch (error) { contentFailed = true; if (live()) setMarketError(message(error)); }
        })(),
      ]);
      if (!live()) return;
      setBusy(false); setPhase("读取结束 · 当前读取不采集新行情");
      // 正常定期只查ID；先前连接/概况失败至少间隔30秒后重读，同版本成功内容不重复读取。
      const frozen = JSON.stringify(versions);
      let pollFailed = false;
      const inspect = async () => {
        if (!live()) return;
        try {
          const next = await views.versions(controller.signal);
          if (live() && (pollFailed || contentFailed || detailFailed.current || JSON.stringify(next) !== frozen)) { views.clear(); setReload(value => value + 1); return; }
        } catch (error) {
          views.clear(); pollFailed = true;
          if (live()) { setConnected(undefined); setRows({}); setMarket(undefined); setConnectionNotice(message(error)); setPhase("版本核对失败，已暂停显示资料"); }
        }
        if (live()) poll = setTimeout(inspect, 30000);
      };
      poll = setTimeout(inspect, 30000);
    })().catch(error => {
      if (!live()) return;
      // 描述、握手及第一次版本检查与后续轮询采用同一失败边界。
      setConnected(undefined); setRows({}); setMarket(undefined); setBusy(false);
      setPhase("版本核对失败，已暂停显示资料"); setConnectionNotice(message(error));
      poll = setTimeout(() => { if (live()) setReload(value => value + 1); }, 30000);
    });
    return () => { controller.abort(); if (poll) clearTimeout(poll); price?.close(); activity?.close(); };
  }, [connection, connectionError, owner, reload, refreshToken]);

  const key = JSON.stringify([owner, selected, range, frequency, ma, field, activityMA, connected?.versions]);
  useEffect(() => {
    const controller = new AbortController();
    if (!connected || connected.owner !== owner) return () => controller.abort();
    const marketSelected = selected === "three-market", id = marketSelected ? LEGACY_MARKET : selected;
    const version = marketSelected ? undefined : connected.versions.indices.find(item => item.index_id === id)?.price;
    const quantity = marketSelected ? connected.versions.markets.find(item => item.series_id === id)?.activity
      : connected.versions.indices.find(item => item.index_id === id)?.activity;
    setDetail({ owner, key, loading: true });
    const timer = setTimeout(() => { void (async () => {
      const result: typeof detail = { owner, key, loading: false };
      await Promise.all([
        (async () => {
          if (marketSelected) return;
          if (!version) { result.priceError = "尚无已保存价格"; return; }
          try { result.price = await connected.views.priceRange(selected, version, requestedRange(version.source_coverage, range), frequency, ma, controller.signal); }
          catch (error) { result.priceError = message(error); if (!controller.signal.aborted) detailFailed.current = true; }
        })(),
        (async () => {
          if (!quantity || !connected.views.activity) { result.activityError = "尚无与固定价格或日期匹配的量额"; return; }
          if (!marketSelected && quantity.binding !== version?.publication_id) { result.activityError = "量额与固定价格版本不匹配"; return; }
          try { result.activity = await connected.views.activityRange(id, quantity, requestedRange(quantity.source_coverage, range), marketSelected ? "amount" : field,
            marketSelected ? "daily" : frequency, activityMA, controller.signal); }
          catch (error) { result.activityError = message(error); if (!controller.signal.aborted) detailFailed.current = true; }
        })(),
      ]);
      if (!marketSelected && !result.price && result.activity) {
        result.activity = undefined; result.activityError = "当前周期价格计算未取得，量额暂不显示";
      }
      if (result.price && result.activity && (result.price.calendar_version !== result.activity.calendar_version
          || JSON.stringify(result.price.requested_range) !== JSON.stringify(result.activity.requested_range)
          || result.price.series.rows.length !== result.activity.series.rows.length
          || result.price.series.rows.some((row, i) => row.start !== result.activity!.series.rows[i].start || row.end !== result.activity!.series.rows[i].end))) {
        result.activity = undefined; result.activityError = "价格与量额的固定日期、日历或周期不一致";
      }
      if (!controller.signal.aborted) setDetail(result);
    })(); }, range.preset === "custom" ? 100 : 0);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [connected, key]);
  const selectedDetail = detail.owner === owner && detail.key === key ? detail : { loading: Boolean(connected), price: undefined, activity: undefined, priceError: undefined, activityError: undefined };
  return { rows, market, marketError, connectionNotice, detail: selectedDetail, descriptor: connected?.owner === owner ? connected.descriptor : undefined,
    busy: busy || selectedDetail.loading, phase: !busy && selectedDetail.loading ? "正在读取所选范围及配对量额…" : phase,
    reload: () => setReload(value => value + 1) };
}
