/** 使用固定正式库和日常端口启动桌面；启动本身不发起采集或迁移。 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const appRoot = fileURLToPath(new URL("../", import.meta.url));
const dataRoot = fileURLToPath(new URL("../../../.local-data/slice-002245-sina", import.meta.url));
const environment = {
  ...process.env,
  WOLF_SLICE_DATA_ROOT: dataRoot,
  WOLF_ENABLE_DATA_UPDATE: "1",
  WOLF_DEV_PORT: "5173",
  WOLF_SERVICE_PORT: "8000",
  CARGO_TARGET_DIR: fileURLToPath(new URL("../src-tauri/target", import.meta.url)),
};

// 不传入QA配置，也不把调用者的测试目录/端口带入正式会话。
const result = spawnSync("npm", ["run", "tauri", "--", "dev"], {
  cwd: appRoot, env: environment, stdio: "inherit",
});
if (result.error) {
  console.error("桌面启动失败：", result.error.message);
  process.exitCode = 1;
} else if (result.signal) {
  process.kill(process.pid, result.signal);
} else {
  process.exitCode = result.status ?? 1;
}
