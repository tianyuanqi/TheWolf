/** 隔离替身验证日常入口不会继承QA目录/端口，不启动真实桌面或采集。 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, writeFileSync, chmodSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const appRoot = fileURLToPath(new URL("../", import.meta.url));
const launcher = fileURLToPath(new URL("start_daily.mjs", import.meta.url));
const dataRoot = fileURLToPath(new URL("../../../.local-data/slice-002245-sina", import.meta.url));

/** 临时npm只返回允许核验的字段；保留真实用户环境，不执行Tauri。 */
function run(exitCode, signal) {
  const directory = mkdtempSync(join(tmpdir(), "thewolf-daily-entry-"));
  try {
    const npm = join(directory, "npm");
    writeFileSync(npm, `#!/usr/bin/env node
console.log(JSON.stringify({args: process.argv.slice(2), cwd: process.cwd(),
  dataRoot: process.env.WOLF_SLICE_DATA_ROOT, enabled: process.env.WOLF_ENABLE_DATA_UPDATE, indexEnabled: process.env.WOLF_ENABLE_INDEX_UPDATE,
  frontend: process.env.WOLF_DEV_PORT, service: process.env.WOLF_SERVICE_PORT,
  target: process.env.CARGO_TARGET_DIR}));
${signal ? 'process.kill(process.pid, "SIGTERM");' : `process.exit(${exitCode});`}
`);
    chmodSync(npm, 0o700);
    return spawnSync(process.execPath, [launcher], {
      cwd: directory, encoding: "utf8", timeout: 10000,
      env: { ...process.env, PATH: `${directory}:${process.env.PATH}`,
        WOLF_SLICE_DATA_ROOT: "/tmp/synthetic-qa", WOLF_ENABLE_DATA_UPDATE: "0", WOLF_ENABLE_INDEX_UPDATE: "0",
        WOLF_DEV_PORT: "5186", WOLF_SERVICE_PORT: "8016", CARGO_TARGET_DIR: "/tmp/synthetic-build" },
    });
  } finally {
    rmSync(directory, { recursive: true });
  }
}

test("日常入口覆盖父环境指数开关0，固定正式根/端口且不增加采集参数", () => {
  const result = run(0);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), {
    args: ["run", "tauri", "--", "dev"], cwd: resolve(appRoot), dataRoot,
    enabled: "1", indexEnabled: "1", frontend: "5173", service: "8000", target: join(appRoot, "src-tauri/target"),
  });
});

test("启动失败保留子进程非零退出码", () => {
  assert.equal(run(23).status, 23);
});

test("子进程终止信号传回入口，不伪称启动成功", () => {
  assert.equal(run(0, true).signal, "SIGTERM");
});
