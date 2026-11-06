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

## 启动

使用已有依赖，不将私有配置放进仓库。服务与浏览器均仅监听`127.0.0.1`。最小托管配置示例中的路径需替换为本机既有、相互分离的规范绝对目录；`runtime_base`位于仓库和数据根之外，私有目录权限700。此示例没有金融写权限、没有启动采集、没有周期更新；数据根为空时页面显示暂无数据。

```json
{
  "python": "/absolute/project/python/.venv/bin/python",
  "data_root": "/absolute/private/price",
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

托管入口校验配置并生成基础连接、指数、可选量额描述；只管理自己启动的进程。退出终端后检查本次端口释放。价格写权限、启动集合、请求/字节预算、量额根和周期额度必须显式配置；完整字段约束见`python/src/pmi/managed_config.py`及服务`--help`，未授权不得从示例推导启写。周期账本不存在或损坏时拒绝启动，不自动建账、重置或修复。

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

本基线协议为2.0.0；旧`slice_write`、`index_write`和相应CLI参数已移除，旧连接描述会被拒绝，须从本版本显式配置重新生成。不会迁移、删除或修复任何旧金融数据库。总览继续读取已保存的v2指数及量额版本；旧260日沪深300/002245专用页面、API、采集器和原生客户端已退役。旧标签页操作记录仅保留原字节导出，不据此自动查询或重发。

`master`仅收录已验收总览；大资金动向、标的查询留在本地保全中，后续分别迁入`codex/etf-flow`、`codex/stock-query`，逐项验收后纳入。旧分支与归档不并入master。本地代码保全不能替代业务数据备份；推送、切换GitHub默认分支、删除旧分支及日常版本切换分别按明确授权执行。
