/** 使用真实React提交时序和标准浏览器Blob URL核验R01；所有外部路由阻断。 */
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "vite";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
assert.ok(process.env.WOLF_PLAYWRIGHT_MODULE, "按README设置既有运行时的WOLF_PLAYWRIGHT_MODULE，不安装新依赖");
const { chromium } = require(process.env.WOLF_PLAYWRIGHT_MODULE);
const bundle = await build({ root: appRoot, configFile: path.join(appRoot, "vite.config.ts"), logLevel: "error",
  define: { "process.env.NODE_ENV": JSON.stringify("development") },
  build: { write: false, minify: false, rollupOptions: { input: path.join(appRoot, "scripts/pdf_ownership.fixture.tsx"),
    output: { format: "iife", name: "PdfOwnershipProbe" } } } });
const code = bundle.output.find(item => item.type === "chunk" && item.isEntry).code;
const sourceSha = createHash("sha256").update(await readFile(path.join(appRoot, "src/LegacySliceView.tsx"))).digest("hex");

/** 每个用例持有独立浏览器上下文，失败也关闭并释放夹具URL。 */
async function withProbe(run, { strictMode = false } = {}) {
  let browser, context, page;
  try {
    browser = await chromium.launch({ headless: true });
    context = await browser.newContext();
    await context.route("**/*", route => route.abort());
    page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(String(error)));
    await page.setContent('<!doctype html><html><body><div id="root"></div></body></html>');
    await page.evaluate(strict => { window.strictMode = strict; }, strictMode);
    await page.addScriptTag({ content: code });
    await page.getByRole("button", { name: "打开同版本原件" }).first().waitFor();
    if (strictMode) await page.waitForFunction(() => window.events.filter(event => event === "legacy committed").length >= 2);
    await run(page);
    assert.deepEqual(errors, []);
  } finally {
    if (page) await page.evaluate(() => window.releaseProbeURLs?.()).catch(() => {});
    if (context) await context.close();
    if (browser) await browser.close();
  }
}

async function openBody(page, index, action) {
  await page.evaluate(next => { window.finishBody = undefined; window.nextAction = next; }, action);
  await page.getByRole("button", { name: "打开同版本原件" }).nth(index).click();
  await page.waitForFunction(() => typeof window.finishBody === "function");
  await page.evaluate(() => window.finishBody());
}

async function result(page) {
  return page.evaluate(async () => ({ created: window.created, revoked: window.revoked, events: window.events,
    readable: await Promise.all(window.created.map(async url => {
      try { await (await window.originalFetch(url)).text(); return true; } catch { return false; }
    })), iframeCount: document.querySelectorAll("iframe").length }));
}

function assertReleased(observed, count) {
  assert.equal(observed.created.length, count);
  assert.deepEqual([...observed.revoked].sort(), [...observed.created].sort());
  assert.deepEqual(observed.readable, Array(count).fill(false));
  assert.equal(observed.iframeCount, 0);
  console.log(JSON.stringify({ sourceSha, ...observed }));
}

for (const strictMode of [false, true]) {
  test(`R01真实React：URL已接受但状态未提交时普通导航回收${strictMode ? "（StrictMode）" : ""}`, async () => {
    await withProbe(async page => {
      await openBody(page, 0, "leave");
      await page.waitForFunction(() => window.events.includes("market committed"));
      const observed = await result(page);
      assert.ok(observed.events.includes("leave before pending child commit"));
      assertReleased(observed, 1);
    }, { strictMode });
  });
}

test("R01真实React：替换原件状态未提交时导航，同时回收旧URL与新URL", async () => {
  await withProbe(async page => {
    await openBody(page, 0); await page.locator("iframe").waitFor();
    await openBody(page, 1, "leave");
    await page.waitForFunction(() => window.events.includes("market committed"));
    assertReleased(await result(page), 2);
  });
});

test("R01真实React：替换原件状态未提交时关闭，不遗留新URL", async () => {
  await withProbe(async page => {
    await openBody(page, 0); await page.locator("iframe").waitFor();
    await openBody(page, 1, "close");
    await page.waitForFunction(() => window.events.includes("close before pending child commit") && !document.querySelector("iframe"));
    assertReleased(await result(page), 2);
  });
});

test("R01真实React：正常切换仅撤销旧URL，关闭、重开及卸载仍正确", async () => {
  await withProbe(async page => {
    await openBody(page, 0); await page.locator("iframe").waitFor();
    await openBody(page, 1); await page.locator('iframe[title^="合成forecast"]').waitFor();
    const switched = await result(page);
    assert.deepEqual(switched.revoked, [switched.created[0]]);
    assert.deepEqual(switched.readable, [false, true]);
    await page.getByRole("button", { name: "关闭", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector("iframe"));
    assertReleased(await result(page), 2);
    await openBody(page, 0); await page.locator("iframe").waitFor();
    await page.locator("#pdf-probe-nav").click();
    await page.waitForFunction(() => window.events.includes("market committed"));
    assertReleased(await result(page), 3);
  }, { strictMode: true });
});
