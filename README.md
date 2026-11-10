# TheWolf

个人本地行情研究工具。Python 服务与 React 浏览器分离，当前交付“行情总览”。`apps/desktop`沿用源码目录名，运行的是浏览器应用。

## 最小必读入口

依次阅读本节、[协作规则](AGENTS.md)、[当前状态](docs/status.md)、[PRD §1–3](docs/PRD-V0.1.md)、[业务约束](docs/Business-Constraints.md)。新任务再按影响读[架构](docs/Architecture-V0.1.md)、[数据模型](docs/Data-Model-V0.1.md)、[来源口径](docs/Data-Sources-V0.1.md)、[编码规范](docs/Coding-Standards.md)、[任务流程](docs/Task-Workflow.md)和[独审规范](docs/Independent-Code-Review-Policy.md)。近期目标见[任务树](docs/Roadmap-Tree.md)。

需求归PRD，架构归Architecture，操作命令归本页；HTTP结构只编辑`contracts/openapi.yaml`，其余生成物禁止手改。审查报告、截图、日志、来源原件、真实数据和机器私有配置只在本地保全，不纳入发布树。源码测试及合成夹具是可复现代码，保留纳管。

## 验证入口

从仓库根执行。需已有 Python 3.12、Node 22.12+及锁文件对应依赖；不自动安装。项目服务依赖见`python/requirements.lock`；契约工具分别使用`tools/contracts/requirements.lock`和同目录`package-lock.json`。前端依赖见`apps/desktop/package-lock.json`。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python/src:python/tests python/.venv/bin/python -B -m unittest discover -s python/tests
node --test apps/desktop/scripts/*.test.mjs apps/desktop/scripts/*.test.cjs
node apps/desktop/node_modules/typescript/bin/tsc --noEmit -p apps/desktop/tsconfig.json
PYTHONPATH="python/src:python/.venv/lib/python3.12/site-packages" tools/contracts/.venv/bin/python -B tools/contracts/check_browser.py
tools/contracts/.venv/bin/python -B tools/contracts/generate.py --check
git diff --check
```

构建输出放到本次独占目录：

```bash
WOLF_CHECK_ROOT="$(mktemp -d /private/tmp/wolf-master-check-XXXXXX)"
WOLF_VITE_CACHE="$WOLF_CHECK_ROOT/vite-cache" node apps/desktop/node_modules/vite/bin/vite.js build apps/desktop --config apps/desktop/vite.config.ts --configLoader runner --outDir "$WOLF_CHECK_ROOT/build"
```

实际页面检查使用已有 Playwright 和浏览器，禁止下载或真实取数。将`WOLF_PLAYWRIGHT_MODULE`指向已有模块绝对目录；可用`WOLF_BROWSER_EXECUTABLE`指定已有 Chrome 可执行文件。测试仅在专有临时根生成合成数据，结束核验自有进程、端口与文件恢复。`.harness.mjs`由对应 Python 入口提供夹具，不能直接按单元测试运行。

```bash
WOLF_TEST_ROOT="$WOLF_CHECK_ROOT" PYTHONPATH=python/src:python/tests python/.venv/bin/python -B python/tests/market_overview_smoke.py
WOLF_BSE_CHECK="$(mktemp -d /private/tmp/wolf-bse-smoke-XXXXXX)"
PYTHONPATH=python/src:python/tests python/.venv/bin/python -B python/tests/bse_smoke.py "$WOLF_BSE_CHECK"
```

第一项覆盖四指数、图表、窄窗、错误恢复与跨根隔离；第二项覆盖沪深北、托管启动和周期更新。环境变量需导出给子进程。检查结果与截图留在本次临时根，必要证据另行本地保全后才清理。通过不代表新一轮真实来源采集或日常配置迁移已完成。文档另核链接、字数及授权含义，计量规则见任务流程§5。

ETF迁入的合成验证沿用上述已有环境。`WOLF_CHECK_ROOT`须为本次独占目录，smoke的输出子目录必须尚不存在；`single`覆盖空数据及显式发布，`four`、`expanded`、`states`覆盖不同配置、历史与缺失状态。

```bash
PYTHONPATH=python/src:python/tests python/.venv/bin/python -B python/tests/etf_flow_client_fixture.py "$WOLF_CHECK_ROOT/etf-client.json"
WOLF_ETF_CLIENT_FIXTURE="$WOLF_CHECK_ROOT/etf-client.json" node --test apps/desktop/scripts/etf_flow_client.harness.mjs
PYTHONPATH=python/src:python/tests python/.venv/bin/python -B python/tests/etf_flow_page_smoke.py "$WOLF_CHECK_ROOT/etf-single" single
PYTHONPATH=python/src:python/tests python/.venv/bin/python -B python/tests/etf_flow_view_smoke.py "$WOLF_CHECK_ROOT/etf-revisions"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python/src:python/tests python/.venv/bin/python -B python/tests/stored_view_fixture.py "$WOLF_CHECK_ROOT/stored-views.json"
WOLF_STORED_FIXTURE="$WOLF_CHECK_ROOT/stored-views.json" node apps/desktop/scripts/stored_views.harness.mjs
```

## 启动

使用已有依赖，不将私有配置放进仓库。服务与浏览器均仅监听`127.0.0.1`。路径须为规范绝对路径；`data_root`指向已导入并核验的统一SQLite目录，可选量额`activity.root`与ETF`etf_flow.root`必须使用同一目录。`runtime_base`位于仓库和数据根之外，私有目录权限700。此示例没有金融写权限、没有启动采集、没有周期更新；服务不会自行建库或转换旧格式。

```json
{
  "python": "/absolute/project/python/.venv/bin/python",
  "data_root": "/absolute/private/market-store",
  "runtime_base": "/absolute/private/runtime",
  "service_port": 8000,
  "browser_port": 5173
}
```

```bash
npm --prefix apps/desktop start -- --config /absolute/private/config.json
# 仅启动、由使用者自行打开输出的本机地址：
npm --prefix apps/desktop start -- --config /absolute/private/config.json --no-open
```

托管入口校验配置并生成基础连接、指数、可选量额/ETF描述；只管理自己启动的进程。退出终端后检查本次端口释放。价格写权限、启动集合、请求/字节预算、量额根和周期额度必须显式配置；完整字段约束见`python/src/pmi/managed_config.py`及服务`--help`，未授权不得从示例推导启写。周期账本不存在或损坏时拒绝启动，不自动建账、重置或修复。

ETF默认未配置。已有获准ETF资料需在托管配置中显式增加下列可选对象；`root`与`data_root`相同，配置和证据文件须独立存在并通过冻结校验。此段只读，不初始化历史、不取数、不自动恢复。观察池和证据结构见ETF需求附件及`etf_flow/model.py`、`evidence.py`；隔离测试由源码夹具生成完整假配置，无需真实配置。

```json
"etf_flow": {
  "root": "/absolute/private/market-store",
  "configuration": "/absolute/private/etf-pool.json",
  "evidence": "/absolute/private/etf-evidence.json",
  "grant": null,
  "write_enabled": false,
  "refresh_revision": null
}
```

独立进程模式使用相同`--etf-root`、`--etf-configuration`、`--etf-evidence`参数生成`describe-etf-config`，宿主通过`WOLF_ETF_BROWSER_CONFIG`读取该公开描述。不能以API响应代替预期配置；首次真实启用及启写仍须另行授权。

也可独立启动两个进程。以下描述与服务必须使用同一参数：

```bash
WOLF_SESSION_DIR="$(mktemp -d /private/tmp/wolf-session-XXXXXX)"
PYTHONPATH=python/src python/.venv/bin/python -B -m pmi.service describe-config --data-root "${WOLF_DATA_ROOT:?指定已有规范数据根}" --port 8000 --origin http://127.0.0.1:5173 > "$WOLF_SESSION_DIR/connection.json"
PYTHONPATH=python/src python/.venv/bin/python -B -m pmi.service describe-index-config --data-root "$WOLF_DATA_ROOT" --port 8000 --origin http://127.0.0.1:5173 > "$WOLF_SESSION_DIR/index.json"
# 终端一：
PYTHONPATH=python/src python/.venv/bin/python -B -m pmi.service serve --data-root "$WOLF_DATA_ROOT" --port 8000 --origin http://127.0.0.1:5173
# 终端二：WOLF_SESSION_DIR使用上面实际创建的目录。
WOLF_DEV_PORT=5173 WOLF_BROWSER_CONFIG="$WOLF_SESSION_DIR/connection.json" WOLF_INDEX_BROWSER_CONFIG="$WOLF_SESSION_DIR/index.json" WOLF_VITE_CACHE="$WOLF_SESSION_DIR/vite-cache" node apps/desktop/node_modules/vite/bin/vite.js apps/desktop --config apps/desktop/vite.config.ts --configLoader runner
```

## 基线与恢复

固定日常发布包放在`.local-releases/`，与业务数据目录`.local-data/`分开；指针仍在`.local-data/daily/runtime-release.json`。发布包不纳管，入口继续核对完整清单、文件集合、规范路径及依赖锁；不能把应用包放入静态服务禁止访问的数据目录。

当前工作区为SQLite协议3.0.0，日常切换状态以[迁移任务书](docs/tasks/TASK-20261107-storage-read-baseline.md)为准。前后端必须来自同一契约和固定发布包；旧连接描述会被拒绝。启动、页面GET不会转换旧根、修复数据库或重发历史请求。旧260日沪深300/002245专用页面、API、采集器和原生客户端保持退役，原对象仅供离线核对。

以下为已授权维护时使用的命令。路径均须明确指定；备份目标与报告必须尚不存在，报告位于数据根之外。备份使用SQLite备份API，连同所有登记原件及逐表/逐字段指纹核对；恢复到另一新目录使用相同命令，再做全量检查和只读页面验证，不能覆盖正在运行的库。真实操作须遵守本轮授权边界。

```bash
PYTHONDONTWRITEBYTECODE=1 python/.venv/bin/python -B tools/migrations/backup_sqlite.py --source /absolute/private/market-store --target /absolute/private/new-backup --output /absolute/private/backup-report.json
PYTHONDONTWRITEBYTECODE=1 python/.venv/bin/python -B tools/migrations/backup_sqlite.py --source /absolute/private/new-backup --target /absolute/private/new-restored --output /absolute/private/restore-report.json
PYTHONDONTWRITEBYTECODE=1 python/.venv/bin/python -B tools/migrations/check_sqlite.py --root /absolute/private/new-restored --kind full --output /absolute/private/full-check-report.json
```

服务存活时每24小时检查结构、每7天完整核验，均只访问本地资料。过期、失败或热journal会停止金融读取；不自动修复或清空隔离状态。明确修复/恢复后，使用完整检查命令追加`--release-quarantine`解除持久隔离，再重启匹配服务以释放内存隔离；结构检查不能解封。检查命令会追加维护记录，不能当作严格只读盘点命令。

一次性导入入口为`tools/migrations/import_legacy.py --help`：必须提供已冻结的完整源清单、旧格式恢复核验、对应SHA、备份副本和迁移批次ID；不能用运行中的旧根替代副本。重复同批次只核对，不重复增加事实。逐版本核对、恢复及切换顺序见任务书；旧数据和旧版本本轮保留，未设置自动清理期限。

已验收交付包括行情总览、首只ETF大资金动向、统一SQLite存储和加载优化；2026-11-10本人授权由`codex/etf-flow`一起提交并合并到本地`master`，暂不推送。标的查询继续留在本地保全。旧分支与归档不并入master。本地代码保全不能替代业务数据备份；推送、切换GitHub默认分支、删除旧分支及日常版本切换分别按明确授权执行。
