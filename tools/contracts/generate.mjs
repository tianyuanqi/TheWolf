/** 同源类型与独立校验生成；只使用已安装锁定依赖。 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const [spec, output, dependencies] = process.argv.slice(2);
const require = createRequire(path.resolve(dependencies, "package.json"));
const { default: openapiTS, astToString } = require("openapi-typescript");
const Ajv2020 = require("ajv/dist/2020.js").default;
const standaloneCode = require("ajv/dist/standalone/index.js").default;
const lengthPath = require.resolve("ajv/dist/runtime/ucs2length.js");
const unicodeLength = require(lengthPath).default;
// Ajv默认辅助函数代码为CommonJS require；在代码生成前登记原实现，避免手修ESM产物。
// 不使用unicode:false；保留非BMP按码点计数，原依赖文件身份进入生成证据。
unicodeLength.code = `(${unicodeLength.toString()})`;
const bundle = JSON.parse(fs.readFileSync(path.join(output, "schemas.json"), "utf8"));
const source = JSON.parse(fs.readFileSync(spec, "utf8"));
const ast = await openapiTS(pathToFileURL(spec));
fs.writeFileSync(path.join(output, "http.d.ts"), "/** 自动生成：只修改 contracts/openapi.yaml，禁止手工修补。 */\n" + astToString(ast));
const ajv = new Ajv2020({ strict: true, allErrors: true, coerceTypes: false,
  useDefaults: false, removeAdditional: false, code: { source: true, esm: true }, formats: { binary: true } });
ajv.addSchema(bundle, "wolf");
const exports = {};
for (const name of Object.keys(bundle.$defs).sort()) {
  const key = `wolf-model-${name}`;
  ajv.addSchema({ $ref: `wolf#/$defs/${name}` }, key);
  exports[name] = key;
}
const emitted = standaloneCode(ajv, exports);
if (/\brequire\s*\(/.test(emitted)) throw new Error("独立ESM仍依赖未支持的require辅助函数");
fs.writeFileSync(path.join(output, "validators.mjs"), "/** 同源生成的独立ESM校验，不执行动态编译。 */\n" + emitted + "\n");
fs.writeFileSync(path.join(output, "validators.d.mts"),
  '/** 同源校验签名；边界参数/头不冒充正文DTO。 */\nimport type { components } from "./http";\n' +
  Object.keys(bundle.$defs).sort().map(name => source.components.schemas[name]
    ? `export const ${name}: (value: unknown) => value is components["schemas"]["${name}"];`
    : `export const ${name}: (value: unknown) => boolean;`).join("\n") + "\n");
console.log(JSON.stringify({ kind: "generator-runtime-helper", helper: "ajv/dist/runtime/ucs2length.js",
  sha256: crypto.createHash("sha256").update(fs.readFileSync(lengthPath)).digest("hex"),
  exportCount: Object.keys(exports).length, externalRequire: false }));
