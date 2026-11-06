/** 显式本机配置的浏览器入口；只管理本次创建的监护进程，不采用旧桌面默认根。 */
import { spawn, execFile } from 'node:child_process';
import { openSync, readFileSync, closeSync, constants, lstatSync } from 'node:fs';
import { isAbsolute, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';
import { dailyRelease } from './daily_release.mjs';

const repo = fileURLToPath(new URL('../../../', import.meta.url));
let pinnedEntry;
try { pinnedEntry = dailyRelease(repo, process.argv.slice(2)); }
catch (error) { console.error('固定日常版本校验失败：', error.message); process.exit(1); }
if (pinnedEntry) {
  await import(pinnedEntry);
} else {
let child;
/** 只观察刚创建的自有组，永不按遗留PID发信号或删除目录。 */
async function groupEmpty(pgid) {
  const output = await new Promise((resolve, reject) => execFile('/bin/ps', ['-axo', 'pid=,pgid='], { timeout: 1000 }, (error, stdout) => error ? reject(error) : resolve(stdout)));
  return !output.split('\n').some(line => line.trim().split(/\s+/)[1] === String(pgid));
}
async function reportAbnormal(pgid, runPath, base) {
  console.error('本次运行已失效；正在等待后备监护并核验自有进程组退场。');
  let empty = false;
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    try { empty = await groupEmpty(pgid); } catch { break; }
    if (empty) break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  console.error(empty ? '已核验本次自有进程组退出。' : '时限内未能核验全部自有进程退出；未按旧PID处置，请保留现场。');
  if (runPath) {
    try { lstatSync(runPath); console.error('运行目录保留待核验：', runPath); }
    catch (error) { console.error(error.code === 'ENOENT' ? '本次运行目录已不存在；入口未执行额外清理。' : `无法核验运行目录，请保留：${runPath}`); }
  } else console.error('未取得本次运行目录身份；运行基目录待核验：', base ?? '配置无效，未知');
}
try {
  const args = process.argv.slice(2);
  if (args.length < 2 || args[0] !== '--config' || (args.length !== 2 && (args.length !== 3 || args[2] !== '--no-open'))) {
    throw new Error('用法：npm start -- --config /绝对路径/config.json [--no-open]');
  }
  if (process.platform !== 'darwin') throw new Error('托管入口目前仅验证macOS；其他平台请用独立启动');
  const path = args[1];
  if (!isAbsolute(path) || resolve(path) !== path || !lstatSync(path).isFile() || lstatSync(path).isSymbolicLink()) throw new Error('配置必须是规范绝对路径的普通文件');
  if (Object.keys(process.env).some(key => key.startsWith('WOLF_'))) throw new Error('托管入口拒绝继承WOLF配置覆盖，请使用明确本机配置');
  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  let raw; try { raw = readFileSync(fd, 'utf8'); } finally { closeSync(fd); }
  if (Buffer.byteLength(raw) > 65536) throw new Error('本机配置过大');
  const value = JSON.parse(raw);
  if (typeof value.python !== 'string' || !isAbsolute(value.python)) throw new Error('必须显式指定已有Python解释器');
  const env = { ...process.env, PYTHONPATH: resolve(repo, 'python/src'), PYTHONDONTWRITEBYTECODE: '1' };
  delete env.PYTHONHOME; delete env.PYTHONPYCACHEPREFIX;
  child = spawn(value.python, ['-B', '-m', 'pmi.managed_runtime', process.execPath, repo], { env, detached: true, stdio: ['pipe', 'pipe', 'inherit'] });
  child.stdin.on('error', () => {});
  child.stdin.write(JSON.stringify({ config: raw, config_path: path }) + '\n');
  let ready = false, stopping = false, runPath;
  const stop = () => { if (!stopping) { stopping = true; child.stdin.end(); } };
  process.on('SIGINT', stop); process.on('SIGTERM', stop);
  createInterface({ input: child.stdout }).on('line', line => {
    try {
      const message = JSON.parse(line);
      if (message.event === 'ready' && !ready && !stopping) {
        ready = true;
        const runId = new URL(message.url).hash.match(/(?:#|&)wolf-run=([a-f0-9-]{36})(?:&|$)/)?.[1];
        if (runId && typeof value.runtime_base === 'string') runPath = resolve(value.runtime_base, runId);
        console.log(`行情总览：${message.url}\n退出：Ctrl+C；本次退出不会删除业务数据。`);
        if (!args.includes('--no-open')) {
          const opener = spawn('/usr/bin/open', [message.url], { stdio: 'ignore' });
          opener.on('error', () => console.error('浏览器未自动打开，请使用上面的地址'));
        }
      } else if (message.event === 'retained') console.error('运行目录保留待核验：', message.path);
    } catch { console.error('监护消息无效，停止本次运行'); stop(); }
  });
  child.on('error', error => { console.error('启动失败：', error.message); process.exitCode = 1; });
  child.on('exit', (code, signal) => {
    process.exitCode = code ?? (signal ? 1 : 0);
    if (!ready) console.error('启动未完成，未连接外部服务');
    if (signal || code !== 0) void reportAbnormal(child.pid, runPath, value.runtime_base).catch(() => console.error('异常退场核验失败，请保留本次现场。'));
  });
} catch (error) {
  console.error('日常入口启动失败：', error.message); process.exitCode = 1;
}
}
