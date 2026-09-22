import { useEffect, useState } from "react";

type Health = { status: string; service: string; storage: string };
type Research = {
  display_name: string;
  exchange: string;
  trade_date: string;
  close_price: number;
  currency: string;
  source_name: string;
  document_id: string;
};
type Evidence = {
  title: string;
  published_at: string;
  source_url: string;
  evidence_page: number;
  evidence_text: string;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`请求失败（${response.status}）`);
  return response.json() as Promise<T>;
}

export function App() {
  const [health, setHealth] = useState<Health>();
  const [research, setResearch] = useState<Research>();
  const [evidence, setEvidence] = useState<Evidence>();
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getJson<Health>("/api/health"), getJson<Research>("/api/demo/research")])
      .then(([nextHealth, nextResearch]) => {
        if (cancelled) return;
        setHealth(nextHealth);
        setResearch(nextResearch);
        setError(undefined);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "服务不可用");
        if (attempt < 10) window.setTimeout(() => setAttempt((value) => value + 1), 500);
      });
    return () => { cancelled = true; };
  }, [attempt]);

  async function openEvidence() {
    if (!research) return;
    try {
      setEvidence(await getJson<Evidence>(`/api/documents/${research.document_id}/evidence`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "证据不可用");
    }
  }

  return (
    <main>
      <header>
        <p className="eyebrow">THEWOLF · 本地验证</p>
        <h1>研究工作台</h1>
        <p>{health ? `本地服务已连接 · ${health.storage}` : "正在连接本地服务…"}</p>
      </header>
      {error && <p className="error">{error}</p>}
      {research && (
        <section className="card">
          <div>
            <p className="eyebrow">样本公司 · {research.exchange}</p>
            <h2>{research.display_name}</h2>
          </div>
          <dl>
            <div><dt>交易日</dt><dd>{research.trade_date}</dd></div>
            <div><dt>收盘价</dt><dd>{research.close_price} {research.currency}</dd></div>
            <div><dt>来源</dt><dd>{research.source_name}</dd></div>
          </dl>
          <button type="button" onClick={openEvidence}>查看本地证据</button>
        </section>
      )}
      {evidence && (
        <section className="card evidence">
          <p className="eyebrow">公告第 {evidence.evidence_page} 页</p>
          <h2>{evidence.title}</h2>
          <p>{evidence.evidence_text}</p>
          <small>发布时间：{evidence.published_at} · {evidence.source_url}</small>
        </section>
      )}
    </main>
  );
}
