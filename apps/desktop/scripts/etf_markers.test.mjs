/** 标记只改变绘图位置：验证非交易日、窗口边界及同日多证据，不制造数据。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const module = { exports: {} };
const source = ts.transpileModule(readFileSync(new URL('../src/etfFlowMarkers.ts', import.meta.url), 'utf8'),
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText;
vm.runInNewContext(source, { module, exports: module.exports });
const { placeEtfMarkers } = module.exports;
const plain = value => JSON.parse(JSON.stringify(value));

test('周末公告保留日期，位于周五和周一之间，不借用交易日', () => {
  const dates = ['2026-10-30', '2026-11-02', '2026-11-03'];
  const markers = [{ id: 'notice', date: '2026-10-31' }];
  const before = JSON.stringify({ dates, markers });
  const [actual] = placeEtfMarkers(dates, markers);
  assert.equal(actual.nonTrading, true);
  assert.ok(Math.abs(actual.position - 5 / 18) < 1e-12);
  assert.equal(actual.marker.date, '2026-10-31');
  assert.equal(JSON.stringify({ dates, markers }), before);
});
test('首尾日居中、窗口外不贴边，同日多条标记完整保留', () => {
  const dates = ['2026-11-02', '2026-11-03'];
  const markers = ['2026-11-01', '2026-11-02', '2026-11-03', '2026-11-03', '2026-11-04'].map((date, n) => ({ id: String(n), date }));
  const values = placeEtfMarkers(dates, markers);
  assert.deepEqual(plain(values.map(value => [value.marker.id, value.position, value.nonTrading])),
    [['1', 0.25, false], ['2', 0.75, false], ['3', 0.75, false]]);
});
test('空窗口不显示标记，单日窗口仍只显示该日', () => {
  const markers = [{ id: 'outside', date: '2026-11-02' }, { id: 'inside', date: '2026-11-03' }];
  assert.equal(placeEtfMarkers([], markers).length, 0);
  assert.deepEqual(plain(placeEtfMarkers(['2026-11-03'], markers)),
    [{ marker: markers[1], position: 0.5, nonTrading: false }]);
});
