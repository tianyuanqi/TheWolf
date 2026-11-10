import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync, lstatSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import type { IncomingMessage, ServerResponse } from "node:http";
import { parseDescriptor } from "./src/apiClient";
import { parseEtfDescriptor } from "./src/etfFlowClient";
import { parseActivityDescriptor } from "./src/activityClient";
import { parseIndexDescriptor } from "./src/indexSeriesClient";

/** 受控浏览器宿主：冻结公开预期；API由浏览器直连，不启用代理。 */
export default defineConfig(({ command }) => {
  const appRoot = fileURLToPath(new URL(".", import.meta.url));
  const serving = command === "serve";
  // 同源生成物已是独立ESM；按原URL直接发送，避免每次启动重复转换及生成巨量调试映射。
  const validatorFile = resolve(appRoot, "../../contracts/generated/validators.mjs");
  const validatorPath = "/@fs" + encodeURI(validatorFile);
  const validatorCode = serving ? readFileSync(validatorFile) : null;
  const port = Number(process.env.WOLF_DEV_PORT);
  let descriptor = "";
  let indexDescriptor: string | undefined;
  let activityDescriptor: string | undefined;
  let etfDescriptor: string | undefined;
  if (serving) {
    const path = process.env.WOLF_BROWSER_CONFIG;
    if (!Number.isInteger(port) || port < 1 || port > 65535 || !path || !isAbsolute(path)
        || lstatSync(path).isSymbolicLink() || !lstatSync(path).isFile()) {
      throw new Error("必须显式配置WOLF_DEV_PORT及公开描述文件WOLF_BROWSER_CONFIG");
    }
    const legacy = parseDescriptor(JSON.parse(readFileSync(path, "utf8")));
    descriptor = JSON.stringify(legacy);
    const etfPath = process.env.WOLF_ETF_BROWSER_CONFIG;
    if (etfPath) {
      if (!isAbsolute(etfPath) || lstatSync(etfPath).isSymbolicLink() || !lstatSync(etfPath).isFile()) {
        throw new Error("WOLF_ETF_BROWSER_CONFIG必须是绝对路径的普通公开描述文件");
      }
      etfDescriptor = JSON.stringify(parseEtfDescriptor(JSON.parse(readFileSync(etfPath, "utf8")), legacy));
    }
    const indexPath = process.env.WOLF_INDEX_BROWSER_CONFIG;
    if (indexPath) {
      if (!isAbsolute(indexPath) || lstatSync(indexPath).isSymbolicLink() || !lstatSync(indexPath).isFile()) {
        throw new Error("WOLF_INDEX_BROWSER_CONFIG必须是绝对路径的普通公开描述文件");
      }
      indexDescriptor = JSON.stringify(parseIndexDescriptor(JSON.parse(readFileSync(indexPath, "utf8")), legacy));
      const activityPath = process.env.WOLF_ACTIVITY_BROWSER_CONFIG;
      if (activityPath) {
        if (!isAbsolute(activityPath) || lstatSync(activityPath).isSymbolicLink() || !lstatSync(activityPath).isFile()) {
          throw new Error("WOLF_ACTIVITY_BROWSER_CONFIG必须是绝对路径的普通公开描述文件");
        }
        activityDescriptor = JSON.stringify(parseActivityDescriptor(JSON.parse(readFileSync(activityPath, "utf8")), JSON.parse(indexDescriptor)));
      }
    }
    if (process.env.WOLF_ACTIVITY_BROWSER_CONFIG && !indexDescriptor) throw new Error("量额配置必须绑定价格预期");
  }
  const authority = `127.0.0.1:${port}`;
  const origin = `http://${authority}`;
  // Vite发送HTML/静态资源时会重设缓存头，最终响应层也必须沿用相同策略。
  const responseHeaders = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
  };
  const guard = (request: IncomingMessage, response: ServerResponse, next: () => void) => {
    const headers: Record<string, string[]> = {};
    for (let i = 0; i < request.rawHeaders.length; i += 2) {
      const key = request.rawHeaders[i].toLowerCase();
      (headers[key] ??= []).push(request.rawHeaders[i + 1]);
    }
    for (const [name, value] of Object.entries(responseHeaders)) response.setHeader(name, value);
    const invalid = headers.host?.length !== 1 || headers.host[0] !== authority
      || (headers.origin && (headers.origin.length !== 1 || headers.origin[0] !== origin))
      || Object.keys(headers).some(key => key === "forwarded" || key.startsWith("x-forwarded-"));
    if (invalid) { response.statusCode = 403; response.end("Forbidden"); return; }
    const configPath = request.url?.split("?")[0];
    if (configPath === validatorPath) {
      if (!["GET", "HEAD"].includes(request.method ?? "")) {
        response.statusCode = 405; response.setHeader("Allow", "GET, HEAD"); response.end(); return;
      }
      if (!validatorCode) { response.statusCode = 503; response.end(); return; }
      response.setHeader("Content-Type", "text/javascript; charset=utf-8");
      response.setHeader("Content-Length", validatorCode.length);
      response.end(request.method === "HEAD" ? undefined : validatorCode); return;
    }
    if (configPath === "/__wolf/config" || configPath === "/__wolf/index-config" || configPath === "/__wolf/activity-config" || configPath === "/__wolf/etf-config") {
      if (request.url !== configPath || !["GET", "HEAD"].includes(request.method ?? "")) {
        response.statusCode = 400; response.end("Invalid config request"); return;
      }
      const body = configPath === "/__wolf/config" ? descriptor : configPath === "/__wolf/index-config" ? indexDescriptor : configPath === "/__wolf/activity-config" ? activityDescriptor : etfDescriptor;
      if (body === undefined) { response.statusCode = 404; response.end(); return; }
      response.setHeader("Content-Type", "application/json");
      response.end(request.method === "HEAD" ? undefined : body); return;
    }
    next();
  };
  return {
    plugins: [{ name: "wolf-browser-host", configureServer(server) { server.middlewares.use(guard); },
      configurePreviewServer(server) { server.middlewares.use(guard); } }, react()],
    cacheDir: process.env.WOLF_VITE_CACHE ?? "node_modules/.vite",
    server: { host: "127.0.0.1", port, strictPort: true, hmr: false, cors: { origin }, headers: responseHeaders,
      fs: { strict: true, allow: [resolve(appRoot), resolve(appRoot, "../../contracts/generated")],
        deny: ["**/.local-data/**", "**/.git/**", "**/.env*", "**/*.pem"] } },
    preview: { host: "127.0.0.1", port, strictPort: true, headers: responseHeaders },
  };
});
