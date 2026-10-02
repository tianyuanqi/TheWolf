/** 使用真实前端 PDF 读取函数验证延迟响应与快照切换，网络全部隔离替代。 */
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import ts from "typescript";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("加载中的旧 PDF 在快照切换后不显示，新响应仍可读取", async () => {
  const directory = await mkdtemp(path.join(appRoot, "node_modules", ".wolf-evidence-test-"));
  const originalFetch = globalThis.fetch;
  try {
    const source = await readFile(path.join(appRoot, "src", "App.tsx"), "utf8");
    const compiled = ts.transpileModule(source, { compilerOptions: {
      target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText;
    const modulePath = path.join(directory, "App.mjs");
    await writeFile(modulePath, compiled);
    const { readEvidencePdf } = await import(modulePath);
    let selectedSnapshot = "old";
    let finishOldBlob;
    let notifyBlobStarted;
    const blobStarted = new Promise((resolve) => { notifyBlobStarted = resolve; });
    globalThis.fetch = async (url, options) => {
      assert.equal(options.headers["X-Wolf-Session"], "synthetic-ui-test");
      assert.equal(options.method, "GET");
      return { ok: true, blob: () => new Promise((resolve) => {
        finishOldBlob = resolve;
        notifyBlobStarted();
      }) };
    };
    const oldResult = readEvidencePdf("/api/snapshots/old/pdf/forecast", "synthetic-ui-test", () => selectedSnapshot === "old");
    await blobStarted;
    selectedSnapshot = "new";
    finishOldBlob(new Blob(["old original"]));
    assert.equal(await oldResult, undefined);
    globalThis.fetch = async () => ({ ok: true, blob: async () => new Blob(["new original"]) });
    const newResult = await readEvidencePdf("/api/snapshots/new/pdf/report", "synthetic-ui-test", () => selectedSnapshot === "new");
    assert.equal(await (await originalFetch(newResult)).text(), "new original");
    URL.revokeObjectURL(newResult);
  } finally {
    globalThis.fetch = originalFetch;
    await rm(directory, { recursive: true, force: true });
  }
});
