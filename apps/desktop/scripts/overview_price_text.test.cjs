const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.join(__dirname, '../src/overviewPriceText.ts'), 'utf8');
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const moduleValue = { exports: {} };
vm.runInNewContext(output, { exports: moduleValue.exports });
const { priceText } = moduleValue.exports;

test('指数价格按十进制四舍五入，保留两位且补足零', () => {
  for (const [value, expected] of [['11471.0938', '11471.09'], ['2566.8030', '2566.80'], ['1000.0050', '1000.01'], ['999.9950', '1000.00'], ['1.0049', '1.00'], ['1.005', '1.01'], ['0', '0.00'], ['0.0049', '0.00'], ['-0.0049', '0.00'], ['-1.0050', '-1.01']]) {
    assert.equal(priceText(value), expected);
  }
  assert.equal(priceText('11471.0938', true), '11,471.09');
  assert.equal(priceText('999999999999999999.995', true), '1,000,000,000,000,000,000.00');
});
test('缺失和非法值不能显示成有效零', () => {
  assert.equal(priceText(null), '暂无数据');
  assert.equal(priceText(undefined), '暂无数据');
  for (const value of ['', 'NaN', 'Infinity', '1e4', '1,000.00']) assert.throws(() => priceText(value));
});
