"""两切片数据层验收：合成行为反例及Python/浏览器生产依赖边界。"""
from __future__ import annotations

import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pmi.market_data import MarketData, ReadUnavailable, SnapshotError
from pmi.service_config import ServiceConfig, digest
from http_test_support import ReadClient, disk
from sqlite_fixture import initialize

REPO = Path(__file__).resolve().parents[2]
CONFIG_IMPORTS = {('pmi.service','pmi.market_data.periodic_budget.PeriodicOptions'), ('pmi.service_config','pmi.market_data.periodic_budget.PeriodicOptions'), ('pmi.managed_config','pmi.market_data.periodic_budget.PeriodicOptions'), ('pmi.periodic_scheduler','pmi.market_data.index_history_calendar.SHANGHAI')}
PUBLIC = {"MarketData", "ReadUnavailable", "SnapshotError", "ActivityError", "ActivityOptions", "ACTIVITY_SERIES", "ACTIVITY_MARKET", "EtfOptions", "EtfError", "decode_etf_request", "etf_request_id", "PeriodicBudgetError", "StorageError"}
OLD_MODULES = {"index_calendar", "index_contract", "index_snapshot", "index_update",
               "index_fetch", "read_only", "writer_lock", "snapshot", "data_update",
               "sina_slice", "source_fetch", "trading_calendar", "read_service"}
# 两切片均已迁入；旧路径、逐符号暂留及共享内部导入均不再放行。
# 非行情访问仅为安装包HTTP契约资源；同样固定到具体函数，不放行任意文件读取。
# 固定到实际处理契约资源／受控配置／自有进程的函数；不能给任意金融I/O放行。
RESOURCE_READS = {'pmi.http_boundary:Boundary.__init__': 'b9143671d6fc5a61b0e55cfe6bbd414b8ee3d607c37f54e289dabbb172144b13', 'pmi.http_contract:_validator': '58b51524010fe1f817eac199949e4cd86316d0d222ddfaf4f8b736bfdad69259', 'pmi.http_contract:response_value': 'c706667bd67b5d9a21dace969f7a517597f6c0e2ff1e492984142c6f98611e40', 'pmi.http_contract:verify_resources': 'a62b187d71ea3f7489fe83cc7f53cdb20d116eb286835f017ec3c2061e011af9', 'pmi.service_config:ServiceConfig.public_descriptor': '4ecfa1ecf2e7c812b815193a883bca07eebf7df1e4b33275c749184afd3d0bbe', 'pmi.managed_runtime:main.register': 'eb3661cd75d8c3a3e2513b653bdb64a8e280cc25eb2beef944c69258c477fdaf', 'pmi.managed_config:unique': '843cf6d79e9eb1b5591e6ac83b6880fef4f87010edc6aae7913f446247395c1d', 'pmi.managed_config:location': '884b93371ae4a2d21edffe99a19cf7a6bd7542bd223cd3976796641ac1893397', 'pmi.managed_config:disjoint': 'e771f3e5b903be0540dccf7a9450cc4461951e7e2e5c0344d525c14272c19f01', 'pmi.managed_config:parse': '25bc498f270faf560f66094ee8bc0de76d12e646699262dbc64cafebfccb8c30', 'pmi.managed_config:service_arguments': '0ebd84e44cd2e5531b686206926f97b1971c3ab07a4daf0801b40756d5e266aa', 'pmi.managed_runtime:members': '1ba0d43b09e6d236ec1b1a6d65ca463ea0e32f77202fc8b34e8055a8647f4bbd', 'pmi.managed_runtime:remove_tree': '326eeeeef74e166ed814a586d44af1680020f181daa2953e4a76aa3384973589', 'pmi.managed_runtime:main': '9f40caedeab1e9e0b470c163286c22940b9ba8f2bff3e483883aec05da0a4ca2', 'pmi.managed_runtime:main.request': 'b71c7e235696a6137d38ed9c2c3ae3f2ed44c527d1178124e3ab5a36c9d07fe6', 'pmi.managed_runtime:main.wait_ready': '15f231276d38062d405a11e92e88059cc91487bcd62a425bd22a5220eb7a4cae', 'pmi.managed_runtime:main.read_record': '2b4e95018a1c7db49ec595f439ddd57e7933217eaf6aa62bae440a4acc0a8896', 'pmi.managed_runtime:main.service_ready': 'd77cae651c28623ae8cd4b9a2725169e3f2949972ddb08506dd17bcacbabec71', 'pmi.managed_runtime:main.browser_ready': 'd9ec23034c0332f16c06cdec9f1b93253ad105ac896304e1422bdb52d46c954f', 'pmi.managed_service:serve': 'df8b115f92a25eeb230194701d174cde238748d71534475580c98650fb2c0ecf', 'pmi.managed_service:serve.watch': '9e13b95c29ba680c8f29a28322df4fd5cba3cf995a5dc26170742e674d638457', 'pmi.service:main': '31809b650966d6ec4ec87bc6c8e4d476e0f22bbd932a8523ef02698661c51fd0', 'pmi.http_contract.schema_graph:validator.build': '91526194d09e1a092343b829935ff3ee4067cbbc202875fef6eb1495f87569d4'}

IO_NAMES = {"open", "fdopen", "read", "readinto", "readline", "readlines", "read_bytes", "read_text",
            "write", "writelines", "write_bytes", "write_text", "connect", "execute", "executemany",
            "executescript", "mkdir", "makedirs", "unlink", "remove", "rmdir", "rmtree", "symlink_to",
            "iterdir", "glob", "rglob", "stat", "lstat", "fstat", "exists", "is_dir", "is_file",
            "Popen", "system", "popen", "flock", "fsync", "truncate", "mkstemp", "TemporaryDirectory"}
DYNAMIC = {"eval", "exec", "__import__", "import_module", "getattr", "getmembers", "run_module", "run_path"}
# 原有双源OHLC校验以getattr读取SourceRow字段；只准许这一个未改算法的函数。
DATA_FIELD_READS = {
    "pmi.market_data.index_contract:build_manifest": "ec01c72b55922246920e527401f5bdd839acd033c7796144cba2dc0b9689cc58"
}
# 新浪既有固定解码器迁入；沿用第一步该函数的完整AST指纹，不放行其他eval。
SOURCE_DECODERS = {
    "pmi.market_data.sina_slice:_decode_sina": "10559294e9d780a148b2db6165041d211f6f5bc4ab13f385fa341bf17e7eb3a1"
}


def _module(path: Path) -> str:
    parts = path.relative_to(REPO / "python/src").with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _symbols(tree: ast.AST) -> dict[ast.AST, tuple[str, ast.AST]]:
    result = {}
    def visit(node, name="<module>", owner=tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name if name == "<module>" else name + "." + node.name
            owner = node
        result[node] = (name, owner)
        for child in ast.iter_child_nodes(node):
            visit(child, name, owner)
    visit(tree)
    return result


def _fingerprint(node: ast.AST) -> str:
    # Python 3.12新增空type_params字段；它不代表函数行为变化。
    value = ast.dump(node, include_attributes=False).replace(', type_params=[]', '')
    return hashlib.sha256(value.encode()).hexdigest()


def python_boundary(sources: dict[str, str]) -> dict:
    """扫描全部生产模块和导入图；未知依赖/动态绕行失败，无股票暂留项。"""
    violations, pending, resources, graph = [], set(), set(), {}
    for module, source in sources.items():
        tree = ast.parse(source)
        symbols, aliases, imports = _symbols(tree), {}, []
        data = module == "pmi.market_data" or module.startswith("pmi.market_data.")
        def issue(node, rule):
            file = 'python/src/' + module.replace('.', '/')
            file += '/__init__.py' if module in {'pmi', 'pmi.market_data', 'pmi.http_contract'} else '.py'
            violations.append({"file": file, "line": node.lineno, "rule": rule})
        def name(node):
            if isinstance(node, ast.Name):
                return aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return name(node.value) + "." + node.attr
            return "?"
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
                    imports.append((node, item.name))
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    package = module if module in {"pmi", "pmi.market_data", "pmi.http_contract"} else module.rsplit('.', 1)[0]
                    base = ".".join(package.split('.')[:len(package.split('.')) - node.level + 1]) + ("." + base if base else "")
                for item in node.names:
                    full = base + "." + item.name
                    aliases[item.asname or item.name] = full
                    imports.append((node, full))
                    if item.name == "*":
                        issue(node, "禁止无法判定的通配导入")
        # 简单别名仍保留来源；复杂动态取属性在下方拒绝，不能静默放行。
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute)):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        aliases[target.id] = name(node.value)
        graph[module] = set()
        for node, full in imports:
            matches = [key for key in sources if full == key or full.startswith(key + ".")]
            if matches:
                graph[module].add(max(matches, key=len))
            private = (module,full) not in CONFIG_IMPORTS and full.startswith("pmi.market_data.") and full not in {"pmi.market_data." + symbol for symbol in PUBLIC}
            if private and not data:
                issue(node, "上层导入数据层内部实现")
            if any(full == "pmi." + old or full.startswith("pmi." + old + ".") for old in OLD_MODULES):
                issue(node, "仍引用已删除的旧行情入口")
            if data and full.startswith("pmi.") and not full.startswith("pmi.market_data"):
                issue(node, "数据层反向依赖上层")
            top = full.split('.')[0]
            approved = {"requests", "akshare", "py_mini_racer"} if data else {"fastapi", "starlette", "uvicorn", "pydantic", "jsonschema"}
            # schema_graph沿用已锁定的Pydantic依赖，仅此模块可用其纯校验API。
            if module == 'pmi.http_contract.schema_graph': approved.add('pydantic_core')
            if top not in sys.stdlib_module_names | approved | {"pmi", "__future__"}:
                issue(node, "未登记的外部依赖，须判断是否绕过数据层")
            if not data and module != "pmi.storage" and top in {"sqlite3", "dbm", "shelve", "ctypes"}:
                issue(node, "上层导入底层存储或动态执行能力")
        for node in ast.walk(tree):
            if isinstance(node, (ast.Attribute, ast.Name)):
                full = name(node)
                if not data and (module,full) not in CONFIG_IMPORTS and full.startswith("pmi.market_data."):
                    rest = full[len("pmi.market_data."):].split('.')[0]
                    if rest not in PUBLIC:
                        issue(node, "上层经别名访问数据层内部实现")
                if not data and isinstance(node, ast.Attribute) and node.attr in {
                        "_root", "_writes", "_locations", "_read", "_require_code", "_series_locations",
                        "_series_runtime", "_series_budget", "_remember_index_locations", "_read_series"}:
                    issue(node, "上层访问数据层私有定位")
            if not isinstance(node, ast.Call):
                continue
            callee = name(node.func)
            leaf = callee.rsplit('.', 1)[-1]
            network = callee.startswith(("requests.", "urllib.request."))
            sensitive = leaf in IO_NAMES | DYNAMIC or network or callee in {"os.replace", "os.rename", "os.link"}
            if data and leaf in DYNAMIC:
                symbol, owner = symbols[node]
                key, actual = module + ':' + symbol, _fingerprint(owner)
                field_read = leaf == 'getattr' and DATA_FIELD_READS.get(key) == actual
                fixed_decoder = leaf == 'eval' and SOURCE_DECODERS.get(key) == actual
                if not (field_read or fixed_decoder):
                    issue(node, "数据层出现未登记动态执行")
            if not sensitive or data or module == "pmi.storage":
                continue
            symbol, owner = symbols[node]
            key = module + ":" + symbol
            actual = _fingerprint(owner)
            if RESOURCE_READS.get(key) == actual:
                resources.add((module, symbol))
            else:
                issue(node, "未登记的文件/SQL/旧入口/动态访问: " + callee)
    # CLI、服务及两个来源子进程均为真实入口；未被服务导入不等于不可达。
    reachable, queue = set(), ["pmi.service", "pmi.managed_service", "pmi.managed_runtime"]
    while queue:
        item = queue.pop()
        if item in reachable:
            continue
        reachable.add(item)
        queue.extend(graph.get(item, ()))
    if "pmi.storage" in reachable:
        violations.append({"file": "pmi.storage", "line": 1, "rule": "演示存储进入生产调用图"})
    return {"files": len(sources), "violations": violations,
            "stock_pending": sorted(pending), "non_market_reads": sorted(resources),
            "demo_unreachable": "pmi.storage" not in reachable}


TS_CHECK = r'''
const ts = require(process.argv[1]);
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const violations = [], classified = [];
const forbidden = new Set(['localStorage','indexedDB','caches','require','eval','Function',
  'showOpenFilePicker','showSaveFilePicker','FileReader','XMLHttpRequest','WebSocket','__TAURI_INTERNALS__']);
const allowedSession = new Set(['sessionStorage.getItem(key)',
  'sessionStorage.setItem(key,JSON.stringify({pending:current??null,history:previous}))']);
for (const [file, source] of Object.entries(input)) {
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const issue = (node, rule) => violations.push({file, line: tree.getLineAndCharacterOfPosition(node.getStart()).line+1, rule});
  function visit(node) {
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node) && node.moduleSpecifier) {
      const module = node.moduleSpecifier.text;
      const local = module.startsWith('./') && Object.keys(input).some(name => name === module.slice(2)+'.ts' || name === module.slice(2)+'.tsx');
      const contract = ['../../../contracts/generated/http','../../../contracts/generated/validators.mjs','../../../contracts/generated/manifest.json'].includes(module);
      const etfStyle = file === 'EtfFlowPage.tsx' && ['./overview.css','./etfFlow.css'].includes(module);
      const style = etfStyle || file === 'main.tsx' && module === './styles.css' || file === 'ProductionOverview.tsx' && module === './overview.css';
      const chart = ['OverviewCharts.tsx','EtfFlowChart.tsx'].includes(file) && ['echarts/core','echarts/charts','echarts/components','echarts/renderers'].includes(module);
      if (!local && !contract && !style && !chart && !['react','react-dom/client'].includes(module)) issue(node, '未登记的浏览器依赖');
    }
    if (ts.isIdentifier(node) || ts.isStringLiteral(node)) {
      const word = node.text;
      if (forbidden.has(word)) issue(node, '浏览器持久缓存/文件/动态入口');
      if (word === 'sessionStorage') {
        const call = node.parent?.parent;
        const text = call?.getText(tree).replace(/\s/g,'');
        const recordCall = file === 'operationSession.ts' && ts.isCallExpression(call) && ['sessionStorage.getItem(key)','sessionStorage.setItem(key,text)','sessionStorage.key(i)'].includes(text);
        const recordLength = file === 'operationSession.ts' && ts.isPropertyAccessExpression(node.parent) && node.parent.getText(tree) === 'sessionStorage.length';
        if (!recordCall && !recordLength && (file !== 'ManualUpdate.tsx' || !ts.isCallExpression(call) || !allowedSession.has(text))) issue(node, '操作身份以外的浏览器存储访问');
        else classified.push({file, line: tree.getLineAndCharacterOfPosition(node.getStart()).line+1, usage:'操作身份，不是行情缓存'});
      }
      if (word === 'fetch' && !['apiClient.ts','indexSeriesClient.ts','activityClient.ts','etfFlowClient.ts','browserHost.ts'].includes(file)) issue(node, '页面绕过公共Client');
    }
    if (ts.isCallExpression(node) && node.expression.kind === ts.SyntaxKind.ImportKeyword) issue(node, '动态导入无法证明边界');
    if (ts.isElementAccessExpression(node) && ['window','globalThis','self'].includes(node.expression.getText(tree))) issue(node, '动态全局能力访问无法证明边界');
    ts.forEachChild(node, visit);
  }
  visit(tree);
}
process.stdout.write(JSON.stringify({files:Object.keys(input).length, violations, classified}));
'''


def browser_boundary(sources: dict[str, str]) -> dict:
    """使用项目已有TypeScript解析器，不装依赖、不启动浏览器。"""
    result = subprocess.run(["node", "-e", TS_CHECK, str(REPO / "apps/desktop/node_modules/typescript")],
                            input=json.dumps(sources), text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


class DataLayerBoundaryTests(unittest.TestCase):
    def test_approved_chart_and_series_client_are_narrow_exceptions(self):
        approved = browser_boundary({
            'OverviewCharts.tsx': 'import {init} from "echarts/core";',
            'indexSeriesClient.ts': 'fetch("/api/index-series/session");',
            'activityClient.ts': 'fetch("/api/market-activity/session");'})
        self.assertEqual(approved['violations'], [])
        for sources in ({'OtherPage.tsx': 'import {init} from "echarts/core";'},
                        {'OverviewCharts.tsx': 'import plug from "echarts/extension/bmap/bmap";'},
                        {'OtherPage.tsx': 'fetch("/api/index-series/session");'},
                        {'OtherPage.tsx': 'fetch("/api/market-activity/session");'}):
            self.assertTrue(browser_boundary(sources)['violations'])

    def _assert_opaque_scope_api(self, data):
        # 固定当前公开面，防止目录出口仅改名；不扩展为通用动态分析器。
        public = {name for name in dir(data) if not name.startswith('_')}
        self.assertEqual(public, {'scope_id', 'check_location', 'check_write_paths',
                                 'read_daily', 'latest_date', 'read_evidence',
                                 'status', 'is_active', 'update', 'index_policy', 'index_catalog',
                                 'resolve_index', 'read_index_range', 'read_index_calculations', 'close_updates', 'wait_updates', 'storage_identity', 'storage_status', 'start_maintenance',
                                 'market_versions', 'price_view', 'activity_view', 'read_index_view',
                                 'read_index_original', 'activity', 'activity_scope_id', 'activity_anchor_date', 'activity_market_anchors', 'periodic_status', 'periodic_check', 'etf_flow'})
        self.assertIs(type(data.scope_id), str)
        self.assertRegex(data.scope_id, r'\A[0-9a-f]{64}\Z')
        # 新公开面只给身份/能力/预算，不把目录或数据库位置作为新出口。
        for value in (data.index_policy, data.index_catalog()):
            self.assertNotIn('relative_dir', json.dumps(value))
            self.assertNotIn('data_root', json.dumps(value))
        self.assertEqual(data.resolve_index('上证指数'), 'sse:000001:price')

    def test_public_scope_api_and_actual_config_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); initialize(root)
            config = ServiceConfig(root, 18080, ('http://127.0.0.1:18081',))
            with ExitStack() as stack:
                for target in ('builtins.open', 'pathlib.Path.open', 'pathlib.Path.mkdir',
                               'os.open', 'sqlite3.connect'):
                    stack.enter_context(patch(target, side_effect=AssertionError('身份计算发生I/O')))
                self._assert_opaque_scope_api(config.market_data)
                self.assertEqual(config.data_scope_id, config.market_data.scope_id)
                self.assertRegex(config.config_id, r'\A[0-9a-f]{64}\Z')
            descriptor = config.public_descriptor()
            self.assertNotIn(str(root), json.dumps(descriptor))

            # 真实ServiceConfig仅可取得不透明摘要；若重新拼路径或索取布局即失败。
            accesses = []
            class DigestOnly:
                def __getattribute__(self, name):
                    if name not in ('scope_id', 'storage_identity'):
                        raise AssertionError('上层索取存储内部信息: ' + name)
                    accesses.append(name)
                    return '1' * 64
            object.__setattr__(config, 'market_data', DigestOnly())
            expected_config = digest({'identity_format': 'wolf-config-v2', 'data_scope_id': '1' * 64,
                'backend_authority': '127.0.0.1:18080',
                'allowed_origins': ['http://127.0.0.1:18081'], 'contract_major': 3, 'storage': '1'*64})
            self.assertEqual(config.data_scope_id, '1' * 64)
            self.assertEqual(config.config_id, expected_config)
            self.assertEqual(config.public_descriptor(),
                             {**descriptor, 'data_scope_id': '1' * 64, 'config_id': expected_config})
            self.assertTrue(accesses)
            self.assertTrue((root/'facts.sqlite').is_file())

    def test_scope_export_counterexamples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); initialize(root)
            exports = (
                ('scope_mapping', {'slice': '.', 'index_000300': 'indices/csi000300'}),
                ('renamed_layout', {'index_000300': root / 'indices/csi000300'}),
                ('scope_id', root / 'indices/csi000300'),
                ('scope_id', 'indices/csi000300'),
                ('scope_id', object()),
            )
            for name, value in exports:
                with self.subTest(export=name, value_type=type(value).__name__):
                    leak = type('StorageExport', (MarketData,),
                                {name: property(lambda self, value=value: value)})
                    with self.assertRaises(AssertionError):
                        self._assert_opaque_scope_api(leak(root, {}))

    def test_production_boundary(self):
        sources = {_module(path): path.read_text() for path in (REPO / "python/src/pmi").rglob("*.py")}
        python = python_boundary(sources)
        browser = browser_boundary({str(p.relative_to(REPO / "apps/desktop/src")): p.read_text()
                                    for p in (REPO / "apps/desktop/src").rglob("*") if p.suffix in {".ts", ".tsx", ".js", ".mjs", ".cjs"}})
        report = {"stage": "step2-two-slices", "python": python, "browser": browser,
                  "completion": "两切片生产上层违规与股票暂留均须为0"}
        print(json.dumps(report, ensure_ascii=False))
        self.assertEqual(python["violations"], [])
        self.assertEqual(browser["violations"], [])
        self.assertEqual(python["stock_pending"], [])
        self.assertTrue(python["demo_unreachable"])
        for module in OLD_MODULES:
            self.assertIsNone(importlib.util.find_spec("pmi." + module), module)

    def test_python_bypass_counterexamples(self):
        for source in (
            "from pmi.market_data import index_snapshot as hidden\nhidden.read_snapshot(root)",
            "import pmi.market_data.index_snapshot as hidden\nhidden.read_snapshot(root)",
            "import pmi.market_data as md\nmd.index_snapshot.read_snapshot(root)",
            "import sqlite3 as db\nf = db.connect\nf('index.sqlite')",
            "from pathlib import Path\nPath('index.sqlite').read_bytes()",
            "from pmi.market_data import snapshot as hidden\nhidden.read_snapshot(root)",
            "from pmi import data_update as hidden\nhidden.start_update(root)",
            "from pathlib import Path\nPath('slice.sqlite').read_bytes()",
            "import importlib as loader\nloader.import_module(name)",
            "getattr(data, '_root').read_bytes()",
        ):
            with self.subTest(source=source):
                self.assertTrue(python_boundary({"pmi.probe": source})["violations"])
        self.assertFalse(python_boundary({"pmi.probe": "from pmi.market_data import MarketData\ndata.read_daily('000300')"})["violations"])
        self.assertTrue(python_boundary({"pmi.market_data.probe": "from pmi.api import create_app"})["violations"])
        self.assertTrue(python_boundary({"pmi.market_data.probe": "decoder.eval(untrusted)"})["violations"])
        self.assertTrue(python_boundary({"pmi.service": "import pmi.storage", "pmi.storage": ""})["violations"])
        self.assertTrue(python_boundary({"pmi.service": "from pmi import helper", "pmi.helper": "from pathlib import Path\nPath('cache').read_text()"})["violations"])

    def test_browser_bypass_counterexamples(self):
        for source in ("import {readFile as hidden} from 'node:fs'; hidden('cache')",
                       "window['localStorage'].getItem('bars')", "indexedDB.open('bars')",
                       "const hidden = sessionStorage; hidden.getItem('bars')", "import(name)",
                       "fetch('/api/indices/000300')"):
            with self.subTest(source=source):
                self.assertTrue(browser_boundary({"Page.tsx": source})["violations"])
        self.assertFalse(browser_boundary({"Page.tsx": "client.json('/api/indices/000300', parse)"})["violations"])
