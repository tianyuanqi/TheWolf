import { useEffect, useState } from "react";
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

/** 携带桌面会话凭据读取本地 API，并将服务端错误转为可见提示。 */
async function request(path: string, token: string): Promise<Response> {
  const response = await fetch(path, {
    headers: { "X-Wolf-Session": token }, signal: AbortSignal.timeout(8000),
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

  useEffect(() => {
    if (!isTauri()) {
      setLoading(false);
      setError("请通过 TheWolf 桌面开发窗口查看受保护的真实切片。");
      return;
    }
    invoke<string>("session_token").then(setToken).catch(() => {
      setLoading(false);
      setError("无法取得本地服务会话，请重启桌面窗口。");
    });
  }, []);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setLoading(true);
    request("/api/slice", token).then((response) => response.json() as Promise<Slice>)
      .then((nextSlice) => {
        if (cancelled) return;
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

  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl); }, [pdfUrl]);

  /** 从当前固定快照读取公告原件，避免切换快照后误用其他版本的 PDF。 */
  async function openEvidence(document: DocumentRecord) {
    if (!slice || !token) return;
    setPdfLoading(true);
    try {
      const response = await request(`/api/snapshots/${slice.snapshot_id}/pdf/${document.pdf_object_id}`, token);
      setPdfUrl(URL.createObjectURL(await response.blob()));
      setSelectedPdfId(document.pdf_object_id);
      setError(undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "公告原件不可用");
    } finally {
      setPdfLoading(false);
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
        <button type="button" onClick={() => setAttempt((value) => value + 1)}>重试读取</button></div>}
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
            <span>{slice.bars.length} 行 · 价格 元/股 · 成交量 股 · 成交额 元</span></div>
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
