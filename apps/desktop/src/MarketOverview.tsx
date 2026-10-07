import { useEffect, useRef, useState } from "react";
import { request } from "./LegacySliceView";
import { DailyCandlestick } from "./DailyCandlestick";
import { parseIndexEvidence, parseIndexStatus, parseIndexView } from "./indexTypes";
import type { IndexEvidence, IndexStatus, IndexView } from "./indexTypes";

const PATH = "/api/indices/000300";
const active = (status?: IndexStatus) => ["preparing", "fetching_eastmoney", "fetching_tencent", "fetching_csindex", "validating", "publishing"].includes(status?.stage ?? "");
const labels: Record<string, string> = { preparing: "准备目标窗口", fetching_eastmoney: "旧任务：获取东财日线", fetching_tencent: "获取腾讯日线", fetching_csindex: "获取中证对照", validating: "双源精确校验", publishing: "发布固定快照" };
const sourceNames: Record<string, string> = { eastmoney: "东方财富", tencent: "腾讯", csindex: "中证官方" };
const unusedNames: Record<string, string> = { volume: "成交量", amount: "成交额", prec: "prec（未解释元数据）", version: "version（未解释元数据）" };
const sourceName = (source: string) => sourceNames[source] ?? source;
const unusedName = (field: string) => unusedNames[field] ?? field;
const timeText = (stamp?: string | null) => stamp ? new Date(stamp).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) : "尚未检查成功";

/** 真实本地指数视图；每次替换整份固定快照，失败保留可读旧版。 */
export function MarketOverview({ token, restart }: { token: string; restart: () => Promise<void> }) {
  const [view, setView] = useState<IndexView>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [status, setStatus] = useState<IndexStatus>();
  const [pending, setPending] = useState(false);
  const [posting, setPosting] = useState(false);
  const [notice, setNotice] = useState<string>();
  const [updateError, setUpdateError] = useState<string>();
  const [evidence, setEvidence] = useState<IndexEvidence[]>();
  const [evidenceDay, setEvidenceDay] = useState<string>();
  const [evidenceError, setEvidenceError] = useState<string>();
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const mounted = useRef(true);
  const reading = useRef(0);
  const evidenceGeneration = useRef(0);
  const postGuard = useRef(false);
  const uncertain = useRef(false);
  const previousJob = useRef<string | null | undefined>(undefined);
  const deadline = useRef(0);

  /** 完整响应核对后一次替换；旧图和旧依据从不混用新ID。 */
  async function load() {
    const generation = ++reading.current; setLoading(true);
    try {
      const next = parseIndexView(await (await request(PATH, token)).json());
      if (!mounted.current || generation !== reading.current) return;
      evidenceGeneration.current++;
      setEvidence(undefined); setEvidenceDay(undefined); setEvidenceError(undefined); setEvidenceLoading(false);
      setView(next); setError(undefined);
    } catch (reason) {
      if (mounted.current && generation === reading.current) setError(reason instanceof Error ? reason.message : "本地指数不可用");
    } finally { if (mounted.current && generation === reading.current) setLoading(false); }
  }
  async function readStatus(): Promise<IndexStatus> {
    return parseIndexStatus(await (await request(`${PATH}/update`, token)).json());
  }
  useEffect(() => {
    mounted.current = true; void load();
    readStatus().then(next => {
      if (!mounted.current) return;
      setStatus(next);
      if (active(next)) { deadline.current = Date.now() + 120000; setPending(true); }
    }).catch(() => { if (mounted.current) setUpdateError("无法读取本地更新状态，请核对结果。"); });
    return () => { mounted.current = false; reading.current++; evidenceGeneration.current++; };
  }, [token]);

  /** 超时只核对；相同旧终态不能当作本次成功，更不自动补发POST。 */
  function acceptStatus(next: IndexStatus, manual = false): boolean {
    setStatus(next);
    const waiting = uncertain.current && next.job_id === previousJob.current;
    if (waiting && !(manual && Date.now() > deadline.current && !active(next))) return false;
    if (waiting) setNotice("未发现新的更新任务，已结束等待，可手动再次检查。");
    else setNotice(undefined);
    uncertain.current = false; setUpdateError(undefined);
    if (!active(next) && !waiting && next.stage === "completed" && next.result !== "source_not_ready") void load();
    return !active(next);
  }
  useEffect(() => {
    if (!pending) return;
    let cancelled = false; let timer: number;
    async function poll() {
      try {
        const next = await readStatus();
        if (cancelled || !mounted.current) return;
        if (acceptStatus(next)) { setPending(false); return; }
      } catch { if (!cancelled) setUpdateError("本地结果待核对，保留已保存数据。"); }
      if (cancelled) return;
      if (Date.now() > deadline.current) { setPending(false); setUpdateError("更新结果待核对，请先核对本地结果。"); return; }
      timer = window.setTimeout(poll, 800);
    }
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [pending, token]);

  async function update(checkOnly = false) {
    if (postGuard.current) return;
    postGuard.current = true; setPosting(true);
    if (!checkOnly) { uncertain.current = true; previousJob.current = status?.job_id; deadline.current = Date.now() + 120000; setNotice(undefined); }
    try {
      const next = checkOnly ? await readStatus() : parseIndexStatus(await (await request(`${PATH}/update`, token, "POST")).json());
      if (!mounted.current) return;
      if (!checkOnly) uncertain.current = false;
      const finished = acceptStatus(next, checkOnly);
      if (!finished && Date.now() > deadline.current) deadline.current = Date.now() + 120000;
      setPending(!finished);
    } catch (reason) {
      if (!mounted.current) return;
      setUpdateError(`请求结果待核对：${reason instanceof Error ? reason.message : "本地请求失败"}`);
      if (Date.now() > deadline.current) deadline.current = Date.now() + 120000;
      setPending(true);
    } finally { postGuard.current = false; if (mounted.current) setPosting(false); }
  }
  function clearEvidence() {
    evidenceGeneration.current++;
    setEvidence(undefined); setEvidenceDay(undefined); setEvidenceError(undefined); setEvidenceLoading(false);
  }
  async function showEvidence(day: string) {
    if (!view) return;
    const fixed = view; const generation = ++evidenceGeneration.current;
    setEvidence(undefined); setEvidenceDay(day); setEvidenceError(undefined); setEvidenceLoading(true);
    try {
      const originals = await Promise.all(fixed.evidence.map(async item => parseIndexEvidence(
        await (await request(`${PATH}/snapshots/${fixed.snapshot_id}/evidence/${item.object_id}`, token)).json(), fixed, item.object_id)));
      if (mounted.current && generation === evidenceGeneration.current) setEvidence(originals);
    } catch (reason) {
      if (mounted.current && generation === evidenceGeneration.current) setEvidenceError(reason instanceof Error ? reason.message : "固定依据不可用");
    } finally { if (mounted.current && generation === evidenceGeneration.current) setEvidenceLoading(false); }
  }
  const pct = view?.summary.daily_change_pct;
  return <main className="market-view">
    <header><p className="eyebrow">THEWOLF · 本地市场</p><h1>沪深300</h1><p>000300 · 价格指数 · 中证</p></header>
    <section className="card">
      <div className="section-heading"><h2>最新已保存交易日</h2>
        <button disabled={posting || pending || !status?.enabled || !!updateError || uncertain.current} onClick={() => update()}>检查更新</button></div>
      {loading && <p role="status">正在读取本地指数…</p>}
      {error && <div role="alert" className="warning"><p>{error}{view ? ` · 保留已保存版本 ${view.window.end}` : " · 首版保存最近260个完整交易日。"}</p>
        <button onClick={() => { void restart().then(load); }}>重试启动并读取</button></div>}
      {view && <><dl className="summary">
        <div><dt>数据日期</dt><dd>{view.summary.trade_date}</dd></div><div><dt>收盘点位</dt><dd>{view.summary.close} 点</dd></div>
        <div><dt>较前交易日涨跌幅</dt><dd>{pct == null ? "未知（缺前收）" : `${Number(pct) > 0 ? "+" : ""}${pct}%`}</dd></div>
      </dl><p>已保存：{view.window.start} 至 {view.window.end} · 260日 · 点</p></>}
      {!status?.enabled && <p className="note">此数据根未启用指数写入。启动不采集。</p>}
      <p className="note">最近成功检查：{timeText(status?.last_success_at)}</p>
      <p role="status">{posting ? "正在发起或核对…" : pending ? labels[status?.stage ?? ""] ?? "核对更新结果…" : notice ?? status?.message}</p>
      {updateError && <p role="alert" className="warning">{updateError}</p>}
      {(updateError || status?.stage === "interrupted") && <button disabled={posting || pending} onClick={() => update(true)}>核对结果</button>}
    </section>
    {view && <>
      <DailyCandlestick key={view.snapshot_id} bars={view.bars} expectedDates={view.calendar_dates} onSelect={clearEvidence} onEvidence={showEvidence} />
      {(evidenceDay || evidenceLoading || evidenceError) && <section className="card index-evidence" aria-label="固定日线依据">
        <h2>{evidenceDay} · 本地双源依据</h2><p>固定快照：{view.snapshot_id}</p>
        {evidenceLoading && <p role="status">读取固定原件…</p>}{evidenceError && <p role="alert" className="warning">{evidenceError}</p>}
        {evidence?.map(original => { const row = original.rows.find(item => item.trade_date === evidenceDay);
          return <article key={original.object_id}>
            <h3>{sourceName(original.source)}</h3>
            {row && <><p>定位：{row.locator}</p><p>原值：开 {row.raw_values.open} · 高 {row.raw_values.high} · 低 {row.raw_values.low} · 收 {row.raw_values.close}</p>
              <p>标准值：开 {row.open} · 高 {row.high} · 低 {row.low} · 收 {row.close} 点</p></>}
            <p>{original.verification}</p><p>SHA-256：{original.object_id}</p><p>获取完成：{timeText(original.retrieval.completed_at)} · 发布时间：未知</p>
            <p>规范URL：{original.url}</p><p>未使用：{original.unused_fields.map(unusedName).join("、")}</p>
            <details><summary>安全文本预览{original.preview_truncated ? "（前4096字节）" : ""}</summary><pre>{original.text_preview}</pre></details>
          </article>; })}
      </section>}
      <section className="card"><h2>数据说明</h2><p>当前获取的历史版本，非当时可知回放。{view.evidence.map(item => sourceName(item.source)).join("与")}260日×4个OHLC精确校验。</p>
        <p className="note">首版当前视图260日，旧快照和原件保留。双源完整窗口校验通过才发布；未就绪、失败或中断保留旧版。</p>
        <p className="note">快照：{view.snapshot_id} · 观察：{view.observation_id}</p></section>
    </>}
  </main>;
}
