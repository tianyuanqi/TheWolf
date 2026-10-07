/** 使用真实前端 PDF 读取函数验证延迟响应与快照切换，网络全部隔离替代。 */
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import vm from "node:vm";
import { createRequire } from "node:module";
import ts from "typescript";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dependency = createRequire(path.join(appRoot, "package.json"));

/** 执行真实组件及所有effect清理，使用可读/可撤销的真实Blob URL核验资源归属。 */
async function componentHarness({ delayedBody = false, unmountOnCreate = false } = {}) {
  const hooks = [], effects = [], created = [], revoked = [];
  let cursor = 0, tree, completeBody, bodyStarted, mounted = true;
  const started = new Promise(resolve => { bodyStarted = resolve; });
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { value: initial };
      return [hooks[index].value, value => { hooks[index].value = typeof value === "function" ? value(hooks[index].value) : value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!hooks[index]) hooks[index] = { current: initial };
      return hooks[index];
    },
    useEffect(callback, dependencies) {
      const index = cursor++, previous = hooks[index];
      if (!previous || dependencies.some((value, i) => value !== previous.dependencies[i])) {
        hooks[index] = { dependencies };
        effects.push(() => { previous?.cleanup?.(); hooks[index].cleanup = callback(); });
      }
    },
  };
  const documents = ["forecast", "report"].map(id => ({ title: `合成${id}公告`, pdf_object_id: id,
    issuer_name: "合成", published_at: null, physical_page: 1, evidence_text: "合成",
    publication_precision: "unknown", source_url: "https://synthetic.invalid" }));
  const slice = { snapshot_id: "fixed", instrument_code: "002245", instrument_name: "合成", exchange: "SZSE",
    source_id: "synthetic", market_contract: { raw_publisher: "synthetic" }, calendar_dates: ["2026-09-30"],
    bars: [], open_session_count: 1, observed_count: 0, unknown_missing_dates: [], complete_through_date: "2026-09-30", documents };
  const source = await readFile(path.join(appRoot, "src", "LegacySliceView.tsx"), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: {
    target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX,
  } }).outputText;
  const module = { exports: {} };
  function unmount() {
    if (!mounted) return;
    mounted = false;
    for (const hook of hooks) hook?.cleanup?.();
  }
  vm.runInNewContext(code, {
    module, exports: module.exports,
    require: name => name === "react" ? react : name === "@tauri-apps/api/core" ? { invoke: async () => {} } : dependency(name),
    fetch: async path => ({ ok: true,
      json: async () => path.endsWith("/update") ? { enabled: false, stage: "idle" } : slice,
      blob: () => {
        bodyStarted();
        if (delayedBody) return new Promise(resolve => { completeBody = resolve; });
        return Promise.resolve(new Blob([path]));
      },
    }),
    URL: {
      createObjectURL(blob) {
        const url = URL.createObjectURL(blob); created.push(url);
        if (unmountOnCreate) unmount();
        return url;
      },
      revokeObjectURL(url) { revoked.push(url); URL.revokeObjectURL(url); },
    },
    AbortSignal, Date, window: { setTimeout, clearTimeout },
  });
  function nodes(value) {
    if (Array.isArray(value)) return value.flatMap(nodes);
    if (!value || typeof value !== "object") return [];
    return [value, ...nodes(value.props?.children)];
  }
  async function settle() {
    assert.ok(mounted, "卸载后不得再次执行effect来代替生产回收");
    for (let i = 0; i < 6; i++) {
      cursor = 0; tree = module.exports.LegacySliceView({ sessionToken: "synthetic" });
      while (effects.length) effects.shift()();
      await new Promise(resolve => setImmediate(resolve));
    }
  }
  await settle();
  return { created, revoked, started, unmount, settle,
    complete: () => completeBody(new Blob(["合成迟到PDF body"])),
    open: index => nodes(tree).filter(node => node.type === "button" && node.props.children === "打开同版本原件")[index].props.onClick(),
    close: () => nodes(tree).find(node => node.type === "button" && node.props.children === "关闭").props.onClick(),
    frames: () => nodes(tree).filter(node => node.type === "iframe"),
    cleanup: () => { unmount(); for (const url of created) URL.revokeObjectURL(url); },
  };
}

test("M01-R01：body读取中卸载，迟到结果不创建对象URL", async () => {
  const h = await componentHarness({ delayedBody: true });
  try {
    const pending = h.open(0); await h.started; h.unmount(); h.complete(); await pending;
    assert.equal(h.created.length, 0); assert.equal(h.revoked.length, 0);
  } finally { h.cleanup(); }
});

test("已有PDF在组件卸载时回收，真实Blob URL无法继续读取", async () => {
  const h = await componentHarness();
  try {
    await h.open(0); await h.settle(); assert.equal(h.frames().length, 1);
    const url = h.created[0]; assert.match(await (await fetch(url)).text(), /forecast/);
    h.unmount(); assert.deepEqual(h.revoked, [url]); await assert.rejects(fetch(url));
  } finally { h.cleanup(); }
});

test("正常PDF关闭与公告选择切换均回收旧URL，当前原件仍可读", async () => {
  const h = await componentHarness();
  try {
    await h.open(0); await h.settle(); const first = h.created[0];
    assert.match(h.frames()[0].props.title, /forecast/);
    await h.open(1); await h.settle(); const second = h.created[1];
    assert.deepEqual(h.revoked, [first]); await assert.rejects(fetch(first));
    assert.match(h.frames()[0].props.title, /report/); assert.match(await (await fetch(second)).text(), /report/);
    h.close(); await h.settle(); assert.equal(h.frames().length, 0);
    assert.deepEqual(h.revoked, [first, second]); await assert.rejects(fetch(second));
    await h.open(0); await h.settle(); assert.match(await (await fetch(h.created[2])).text(), /forecast/);
  } finally { h.cleanup(); }
});

test("对象URL已创建但组件在接收前卸载，后置代次核对立即回收", async () => {
  const h = await componentHarness({ unmountOnCreate: true });
  try {
    await h.open(0); assert.equal(h.created.length, 1);
    assert.deepEqual(h.revoked, h.created); await assert.rejects(fetch(h.created[0]));
  } finally { h.cleanup(); }
});

test("加载中的旧 PDF 在快照切换后不显示，新响应仍可读取", async () => {
  const directory = await mkdtemp(path.join(appRoot, "node_modules", ".wolf-evidence-test-"));
  const originalFetch = globalThis.fetch;
  try {
    const source = await readFile(path.join(appRoot, "src", "LegacySliceView.tsx"), "utf8");
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
