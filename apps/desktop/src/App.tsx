import { useEffect, useState } from "react";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { LegacySliceView } from "./LegacySliceView";
import { MarketOverview } from "./MarketOverview";

export { readEvidencePdf } from "./LegacySliceView";

/** 两个页面共享桌面会话；总览读取失败不阻止进入旧资料页。 */
export function App() {
  const [page, setPage] = useState("market");
  const [token, setToken] = useState<string>();
  const [error, setError] = useState<string>();
  async function connect(restart = false) {
    try {
      if (!isTauri()) throw new Error("请通过TheWolf桌面窗口查看本地数据。");
      setToken(await invoke<string>(restart ? "restart_local_service" : "session_token"));
      setError(undefined);
    } catch (reason) { setError(`本地服务未就绪：${String(reason)}`); }
  }
  useEffect(() => { void connect(); }, []);
  return <>
    <nav className="page-nav" aria-label="研究页面">
      <button aria-current={page === "market" ? "page" : undefined} onClick={() => setPage("market")}>市场总览</button>
      <button aria-current={page === "legacy" ? "page" : undefined} onClick={() => setPage("legacy")}>002245资料</button>
    </nav>
    {!token && <main><p role={error ? "alert" : "status"}>{error ?? "正在连接本地服务…"}</p>
      <button onClick={() => connect(true)}>重试启动并读取</button></main>}
    {token && (page === "market" ? <MarketOverview token={token} restart={() => connect(true)} /> : <LegacySliceView sessionToken={token} />)}
  </>;
}
