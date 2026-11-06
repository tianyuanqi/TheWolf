import { useEffect, useState } from "react";
import { ApiClient } from "./apiClient";
import { connectionDescriptor } from "./browserHost";
import { OperationCenter } from "./OperationCenter";
import { ProductionOverview } from "./ProductionOverview";

/** 单一总览入口；实例变化时卸载连接及所有相关读取。 */
export function App() {
  const [client, setClient] = useState<ApiClient>();
  const [error, setError] = useState<string>();
  const [refresh, setRefresh] = useState(0);
  const [requested, setRequested] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const changed = () => setAttempt(value => value + 1);
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
        if (fragment.has("wolf-run")) { fragment.set("page", "overview"); history.replaceState(null, "", "#" + fragment); }
        else if (location.hash) history.replaceState(null, "", "#overview");
      }).catch(reason => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "本地服务未就绪");
      });
    return () => { controller.abort(); connected?.close(); };
  }, [attempt]);
  const reconnect = () => setAttempt(value => value + 1);
  return <>
    <OperationCenter client={client} requested={requested} onPublished={() => setRefresh(value => value + 1)} reconnect={reconnect} />
    <ProductionOverview connectionClient={client} refreshToken={refresh} onUpdate={target => { setRequested(undefined); queueMicrotask(() => setRequested(target)); }} connectionError={error} reconnect={reconnect} />
  </>;
}
