import { useEffect, useState } from "react";
import { ApiClient } from "./apiClient";
import { connectionDescriptor } from "./browserHost";
import { OperationCenter } from "./OperationCenter";
import { EtfFlowPage } from "./EtfFlowPage";
import { ProductionOverview } from "./ProductionOverview";

type Page = "overview" | "fund-flows";
function requestedPage(): Page {
  const fragment = new URLSearchParams(location.hash.slice(1));
  return (fragment.get("page") ?? location.hash.slice(1)) === "fund-flows" ? "fund-flows" : "overview";
}

/** 总览与ETF入口；实例变化时卸载连接及所有相关读取。 */
export function App() {
  const [page, setPage] = useState<Page>(requestedPage);
  const [client, setClient] = useState<ApiClient>();
  const [error, setError] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  const [requested, setRequested] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const changed = () => { setPage(requestedPage()); setAttempt(value => value + 1); };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let connected: ApiClient | undefined;
    setClient(undefined); setError(undefined);
    void connectionDescriptor(controller.signal)
      .then(expected => ApiClient.connect(expected, controller.signal))
      .then(next => {
        if (controller.signal.aborted) { next.close(); return; }
        connected = next; setClient(next);
        // 握手成功后仅归一化页面名称，不改受控运行身份。
        const fragment = new URLSearchParams(location.hash.slice(1));
        if (fragment.has("wolf-run")) { fragment.set("page", requestedPage()); history.replaceState(null, "", "#" + fragment); }
        else if (location.hash) history.replaceState(null, "", "#" + requestedPage());
      }).catch(reason => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "本地服务未就绪");
      });
    return () => { controller.abort(); connected?.close(); };
  }, [attempt]);
  const navigate = (target: string) => {
    const next: Page = target === "fund-flows" ? "fund-flows" : "overview";
    const fragment = new URLSearchParams(location.hash.slice(1));
    if (fragment.has("wolf-run")) { fragment.set("page", next); history.replaceState(null, "", "#" + fragment); }
    else history.replaceState(null, "", "#" + next);
    setPage(next);
  };
  const onUpdate = (target: string) => { setRequested(undefined); queueMicrotask(() => setRequested(target)); };
  const reconnect = () => setAttempt(value => value + 1);
  return <>
    <OperationCenter client={client} requested={requested} onPublished={() => setRefresh(value => value + 1)} reconnect={reconnect} />
    {page === "fund-flows" ? <EtfFlowPage legacyClient={client} connectionError={error} reconnect={reconnect} navigate={navigate} refreshToken={refresh} onUpdate={onUpdate} />
    : <ProductionOverview navigate={navigate} connectionClient={client} refreshToken={refresh} onUpdate={onUpdate} connectionError={error} reconnect={reconnect} />}
  </>;
}
