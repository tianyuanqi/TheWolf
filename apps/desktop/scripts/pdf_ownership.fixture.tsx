/** 真实React资源回归宿主：合成传输只控制正文完成，导航保持普通按钮事件。 */
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { LegacySliceView } from "../src/LegacySliceView";

type PdfProbe = {
  originalFetch: typeof fetch; created: string[]; revoked: string[]; events: string[];
  nextAction?: "leave" | "close"; strictMode?: boolean;
  finishBody?: () => void; leave: () => void; releaseProbeURLs: () => void;
};
const probe = window as typeof window & PdfProbe;
probe.originalFetch = window.fetch.bind(window);
probe.created = []; probe.revoked = []; probe.events = [];
const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
URL.createObjectURL = (blob) => {
  const url = create(blob);
  probe.created.push(url); probe.events.push("URL created");
  const action = probe.nextAction;
  probe.nextAction = undefined;
  if (action) {
    // 让生产回调接受URL并排入更新，再以普通点击抢先卸载/关闭；不强制React提交。
    queueMicrotask(() => queueMicrotask(() => {
      probe.events.push(`${action} before pending child commit`);
      if (action === "leave") probe.leave();
      else Array.from(document.querySelectorAll("button")).find(button => button.textContent === "关闭")!.click();
    }));
  }
  return url;
};
URL.revokeObjectURL = (url) => {
  probe.revoked.push(url); probe.events.push("URL revoked"); revoke(url);
};
const documents = ["report", "forecast"].map(id => ({ title: `合成${id}公告`, issuer_name: "合成",
  published_at: null, publication_precision: "unknown", physical_page: 1,
  evidence_text: "合成", source_url: "https://synthetic.invalid", pdf_object_id: id }));
const slice = { snapshot_id: "synthetic-fixed", instrument_code: "002245", instrument_name: "合成",
  exchange: "SZSE", source_id: "synthetic", market_contract: { raw_publisher: "synthetic" },
  calendar_dates: ["2026-09-30"], bars: [], open_session_count: 1, observed_count: 0,
  unknown_missing_dates: [], complete_through_date: "2026-09-30", documents };
window.fetch = (async (path: RequestInfo | URL) => ({ ok: true,
  json: async () => String(path).endsWith("/update") ? { enabled: false, stage: "idle" } : slice,
  blob: () => new Promise(resolve => {
    probe.finishBody = () => resolve(new Blob([`explicit synthetic PDF bytes: ${String(path)}`], { type: "application/pdf" }));
  }),
})) as typeof fetch;

function Shell() {
  const [show, setShow] = useState(true);
  probe.leave = () => document.getElementById("pdf-probe-nav")!.click();
  useEffect(() => { probe.events.push(show ? "legacy committed" : "market committed"); }, [show]);
  return <><button id="pdf-probe-nav" onClick={() => setShow(false)}>市场总览</button>
    {show ? <LegacySliceView sessionToken="synthetic-probe" /> : <div id="market">市场总览（合成测试宿主）</div>}</>;
}
createRoot(document.getElementById("root")!).render(probe.strictMode ? <React.StrictMode><Shell /></React.StrictMode> : <Shell />);
// 断言完成后的夹具恢复不计入生产撤销记录。
probe.releaseProbeURLs = () => { for (const url of probe.created) revoke(url); };
