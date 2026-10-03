import { useEffect, useRef, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";

type Bar = { trade_date: string; open_cny: string; high_cny: string; low_cny: string;
  close_cny: string; volume_shares: string; amount_cny: string };
type DocumentRecord = { title: string; issuer_name: string; published_at: string | null;
  publication_precision: string; physical_page: number; evidence_text: string;
  source_url: string; pdf_object_id: string };
type Slice = {
  snapshot_id: string; instrument_code: string; instrument_name: string; exchange: string;
  source_id: string; market_contract: { raw_publisher: string };
  calendar_dates: string[]; bars: Bar[]; open_session_count: number; observed_count: number;
  unknown_missing_dates: string[]; complete_through_date: string; pdf_object_id: string;
  document: Omit<DocumentRecord, "pdf_object_id">;
  documents?: DocumentRecord[];
};
type UpdateStatus = { job_id?: string | null; stage: string; result?: string | null; message?: string | null;
  last_success_at?: string | null; enabled?: boolean; snapshot_id?: string };
const ACTIVE_STAGES = ["preparing", "fetching_sina", "fetching_szse", "validating", "publishing"];
const UPDATE_POLL_LIMIT_MS = 120000;
const STAGE_LABELS: Record<string, string> = { preparing: "准备更新", fetching_sina: "获取新浪日线",
  fetching_szse: "获取深交所对照", validating: "校验完整窗口", publishing: "保存新快照" };

/** 将来源连接失败转为操作提示；原始诊断仍保留在本地任务状态中。 */
function updateStatusText(status?: UpdateStatus): string | undefined {
  if (status?.stage === "failed" && status.message?.startsWith("source network unavailable")) {
    return "无法连接行情来源，此次检查未完成。已保存的日线和公告仍可读取，最近成功检查时间未更新。请检查网络或代理设置后重试。";
  }
  return status?.message ?? undefined;
}

/** 携带桌面会话凭据读取本地 API，并将服务端错误转为可见提示。 */
async function request(path: string, token: string, method = "GET"): Promise<Response> {
  const response = await fetch(path, {
    method, body: method === "POST" ? "{}" : undefined,
    headers: { "X-Wolf-Session": token, ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: { message?: string } } | null;
    throw new Error(body?.detail?.message ?? `本地服务请求失败（${response.status}）`);
  }
  return response;
}

function formatInteger(value: string): string {
  return value.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** PDF 响应完整读取后再次核对选择代次，过期响应不创建或展示对象 URL。 */
export async function readEvidencePdf(path: string, token: string, isCurrent: () => boolean): Promise<string | undefined> {
  const response = await request(path, token);
  const blob = await response.blob();
  return isCurrent() ? URL.createObjectURL(blob) : undefined;
}

/** 展示固定快照的日线与公告，并按公告对象读取同版本原件。 */
export function App() {
  const [token, setToken] = useState<string>();
  const [slice, setSlice] = useState<Slice>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [pdfUrl, setPdfUrl] = useState<string>();
  const [selectedPdfId, setSelectedPdfId] = useState<string>();
  const [pdfLoading, setPdfLoading] = useState(false);
  const [update, setUpdate] = useState<UpdateStatus>();
  const [updating, setUpdating] = useState(false);
  const [startingUpdate, setStartingUpdate] = useState(false);
  const [updateError, setUpdateError] = useState<string>();
  const [updateNotice, setUpdateNotice] = useState<string>();
  const pdfGeneration = useRef(0);
  const pollStarted = useRef(0);
  const updateStarting = useRef(false);
  const uncertainPost = useRef(false);
  const submissionStarted = useRef(0);
  const previousJob = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (!isTauri()) {
      setLoading(false);
      setError("请通过 TheWolf 桌面开发窗口查看受保护的真实切片。");
      return;
    }
    invoke<string>("session_token").then(setToken).catch((reason: unknown) => {
      setLoading(false);
      setError(`本地服务未就绪：${String(reason)}`);
    });
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    request("/api/slice", token).then((response) => response.json() as Promise<Slice>)
      .then((nextSlice) => {
        if (cancelled) return;
        pdfGeneration.current += 1;
        setPdfUrl(undefined);
        setSelectedPdfId(undefined);
        setPdfLoading(false);
        setSlice(nextSlice);
        setError(undefined);
        setLoading(false);
      }).catch((reason: unknown) => {
        if (cancelled) return;
        if (!slice && attempt < 10) {
          window.setTimeout(() => setAttempt((value) => value + 1), 500);
        } else {
          setLoading(false);
          setError(reason instanceof Error ? reason.message : "本地快照不可用");
        }
      });
    return () => { cancelled = true; };
  }, [token, attempt]);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    request("/api/slice/update", token).then((response) => response.json() as Promise<UpdateStatus>)
      .then((status) => {
        if (cancelled) return;
        setUpdate(status);
        if (ACTIVE_STAGES.includes(status.stage)) {
          pollStarted.current = Date.now();
          setUpdating(true);
        }
      }).catch(() => { if (!cancelled) setUpdateError("更新状态读取失败，可点击核对结果"); });
    return () => { cancelled = true; };
  }, [token]);

  useEffect(() => {
    if (!token || !updating) return;
    let cancelled = false;
    let timer: number;
    async function poll() {
      try {
        const status = await (await request("/api/slice/update", token!)).json() as UpdateStatus;
        if (cancelled) return;
        setUpdate(status);
        const awaitingSubmission = uncertainPost.current && status.job_id === previousJob.current;
        if (!awaitingSubmission) {
          uncertainPost.current = false;
          setUpdateError(undefined);
        }
        if (!awaitingSubmission && !ACTIVE_STAGES.includes(status.stage)) {
          setUpdating(false);
          if (status.stage === "completed") setAttempt((value) => value + 1);
          return;
        }
      } catch {
        if (cancelled) return;
        setUpdateError("服务暂时无法连接，正在核对本地结果；请勿重复发起采集");
      }
      if (Date.now() - pollStarted.current > UPDATE_POLL_LIMIT_MS) {
        setUpdating(false);
        setUpdateError("更新结果待核对，请点击核对结果后再发起新任务");
        return;
      }
      timer = window.setTimeout(poll, 800);
    }
    void poll();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [token, updating]);

  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  /** 从当前固定快照读取公告原件，避免切换快照后误用其他版本的 PDF。 */
  async function openEvidence(document: DocumentRecord) {
    if (!slice || !token) return;
    const generation = ++pdfGeneration.current;
    setPdfLoading(true);
    try {
      const nextPdfUrl = await readEvidencePdf(`/api/snapshots/${slice.snapshot_id}/pdf/${document.pdf_object_id}`, token,
        () => generation === pdfGeneration.current);
      if (!nextPdfUrl) return;
      if (generation !== pdfGeneration.current) { URL.revokeObjectURL(nextPdfUrl); return; }
      setPdfUrl(nextPdfUrl);
      setSelectedPdfId(document.pdf_object_id);
      setError(undefined);
    } catch (reason) {
      if (generation !== pdfGeneration.current) return;
      setError(reason instanceof Error ? reason.message : "公告原件不可用");
    } finally {
      if (generation === pdfGeneration.current) setPdfLoading(false);
    }
  }

  /** POST 超时先只读核对；等待截止后确认没有新任务且本地任务未运行，才恢复人工发起入口。 */
  async function updateDailyBars(checkOnly = false) {
    if (!token || updateStarting.current) return;
    updateStarting.current = true;
    setStartingUpdate(true);
    if (!checkOnly) {
      previousJob.current = update?.job_id;
      uncertainPost.current = true;
      submissionStarted.current = Date.now();
      setUpdateNotice(undefined);
    }
    pollStarted.current = Date.now();
    setUpdateError(undefined);
    try {
      const status = await (await request("/api/slice/update", token, checkOnly ? "GET" : "POST"))
        .json() as UpdateStatus;
      setUpdate((previous) => ({ ...previous, ...status }));
      const awaitingSubmission = checkOnly && uncertainPost.current && status.job_id === previousJob.current;
      // 相同旧终态不能证明本次成功。只在等待截止后的人工 GET 成功时解除等待，绝不自动补发 POST。
      // 提示仅说明此刻未发现新任务；之后的手动请求仍由服务端单写者锁协调。
      if (awaitingSubmission && !ACTIVE_STAGES.includes(status.stage)
          && Date.now() - submissionStarted.current > UPDATE_POLL_LIMIT_MS) {
        uncertainPost.current = false;
        setUpdating(false);
        setUpdateNotice("未发现新的更新任务。已结束本次等待，可手动再次点击“更新日线”。已保存的日线和公告仍可读取。");
        return;
      }
      if (!awaitingSubmission) uncertainPost.current = false;
      if (!awaitingSubmission && !ACTIVE_STAGES.includes(status.stage)) {
        setUpdating(false);
        if (status.stage === "completed") setAttempt((value) => value + 1);
      } else setUpdating(true);
    } catch {
      setUpdateError("请求结果待核对，正在查询本地任务状态");
      setUpdating(true);
    } finally {
      updateStarting.current = false;
      setStartingUpdate(false);
    }
  }

  /** 仅通过桌面端允许的深交所地址打开外部原件。 */
  async function openSource(sourceUrl: string) {
    try {
      await invoke("open_official_source", { sourceUrl });
      setError(undefined);
    } catch (reason) {
      setError(`无法在浏览器打开深交所原件：${String(reason)}`);
    }
  }

  /** 读取失败时先确认或重启当前子服务，再重新请求快照。 */
  async function retryLocalService() {
    setLoading(true);
    try {
      const currentToken = await invoke<string>("restart_local_service");
      setToken(currentToken);
      setError(undefined);
      setAttempt((value) => value + 1);
    } catch (reason) {
      setLoading(false);
      setError(`本地服务仍不可用：${String(reason)}`);
    }
  }

  const missing = slice?.unknown_missing_dates.length ?? 0;
  const documents = slice?.documents ?? (slice
    ? [{ ...slice.document, pdf_object_id: slice.pdf_object_id }] : []);
  return (
    <main>
      <header><p className="eyebrow">THEWOLF · 本地研究</p>
        <h1>{slice ? `${slice.instrument_name}（${slice.instrument_code}）日线与公告` : "002245 日线与公告"}</h1>
        <p>固定版本的真实数据切片 · 仅供资料查阅</p></header>
      {loading && <p className="status" role="status">正在读取本地快照…</p>}
      {error && <div className="status error" role="alert"><span>{error}</span>
        <button type="button" onClick={retryLocalService}>重试启动并读取</button></div>}
      {!loading && !slice && !error && <p className="status">尚无已发布的真实数据快照。</p>}
      {slice && <>
        <section className="card" aria-labelledby="slice-title">
          <p className="eyebrow">{slice.exchange} · {slice.instrument_code}</p>
          <h2 id="slice-title">{slice.instrument_name}</h2>
          <dl className="summary">
            <div><dt>冻结区间</dt><dd>{slice.calendar_dates[0]} 至 {slice.calendar_dates.at(-1)}</dd></div>
            <div><dt>来源</dt><dd>{slice.market_contract.raw_publisher} · 未复权</dd></div>
            <div><dt>覆盖</dt><dd>{slice.observed_count}/{slice.open_session_count} 开市日</dd></div>
          </dl>
          <p className={missing ? "coverage warning" : "coverage"}>
            {missing ? `未知缺口：${slice.unknown_missing_dates.join("、")}` : "目标窗口无未知缺口"}
            {" · "}完整至 {slice.complete_through_date} · 本地保存，可离线读取
          </p>
          <small>来源标识：{slice.source_id} · 固定快照：{slice.snapshot_id}</small>
          <p className="note">仅有当前取得的历史版本，不支持严格历史时点研究。</p>
        </section>
        <section className="card" aria-labelledby="bars-title">
          <div className="section-heading"><h2 id="bars-title">未复权日线</h2>
            <button type="button" disabled={startingUpdate || updating || !update?.enabled || !!updateError}
              onClick={() => updateDailyBars()}>更新日线</button>
            <span>{slice.bars.length} 行 · 价格 元/股 · 成交量 股 · 成交额 元</span></div>
          <p className="note">完整日线不含上海时区当日 · 最近成功检查：{update?.last_success_at
            ? new Date(update.last_success_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) : "未知"}</p>
          {!update?.enabled && <p className="note">此数据根尚未启用更新。</p>}
          <p role="status" className={update?.stage === "failed" || update?.stage === "interrupted" ? "warning" : "coverage"}>
            {startingUpdate ? "正在发起更新…" : updating ? `${STAGE_LABELS[update?.stage ?? ""] ?? "核对更新结果"}…`
              : updateNotice ?? (uncertainPost.current ? "尚未确认新的更新任务，已保存的数据仍可读取。" : updateStatusText(update))}</p>
          {updateError && <p role="alert" className="warning">{updateError}</p>}
          {(updateError || update?.stage === "interrupted") && <button type="button" disabled={updating}
            onClick={() => updateDailyBars(true)}>核对结果</button>}
          <div className="table-scroll" role="region" aria-label="日线数据表" tabIndex={0}>
            <table><thead><tr><th scope="col">交易日</th><th scope="col">开盘</th>
              <th scope="col">最高</th><th scope="col">最低</th><th scope="col">收盘</th>
              <th scope="col">成交量</th><th scope="col">成交额</th></tr></thead>
              <tbody>{[...slice.bars].reverse().map((bar) => <tr key={bar.trade_date}>
                <th scope="row">{bar.trade_date}</th><td>{bar.open_cny}</td><td>{bar.high_cny}</td>
                <td>{bar.low_cny}</td><td>{bar.close_cny}</td>
                <td>{formatInteger(bar.volume_shares)}</td>
                <td>{formatInteger(bar.amount_cny)}</td></tr>)}</tbody></table>
          </div>
        </section>
        {[...documents].sort((a, b) => (b.published_at ?? "").localeCompare(a.published_at ?? ""))
          .map((document) => <section className="card evidence" key={document.pdf_object_id}
            aria-label={`${document.title}公告证据`}>
            <p className="eyebrow">深交所公告 · 原件证据</p>
            <h2>{document.title}</h2>
            <p className="document-meta">{document.issuer_name} · 发布日期 {document.published_at ?? "未知"}（{document.publication_precision === "date" ? "仅日期" : document.publication_precision}） · 物理第 {document.physical_page} 页</p>
            <blockquote>{document.evidence_text}</blockquote>
            <button type="button" onClick={() => openEvidence(document)} disabled={pdfLoading}>
              {pdfLoading ? "正在读取原件…" : "打开同版本原件"}
            </button>
            <p className="source-link">原始出处：<button className="external-link" type="button"
              onClick={() => openSource(document.source_url)}>深交所原件（在浏览器打开）</button></p>
            {pdfUrl && selectedPdfId === document.pdf_object_id &&
              <div className="pdf-viewer"><div className="section-heading"><h3>本地归档原件</h3>
                <button type="button" onClick={() => { setPdfUrl(undefined); setSelectedPdfId(undefined); }}>关闭</button></div>
                <iframe title={`${document.title}，第 ${document.physical_page} 页`}
                  src={`${pdfUrl}#page=${document.physical_page}`} /></div>}
          </section>)}
      </>}
    </main>
  );
}
