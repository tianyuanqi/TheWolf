/** Only the explicitly selected daily config may use the locally pinned release. */
import {readFileSync, lstatSync, realpathSync, readdirSync} from 'node:fs';
import {resolve, relative, isAbsolute, join} from 'node:path';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
const digest = bytes => createHash('sha256').update(bytes).digest('hex');
function ordinary(path) {
  if (realpathSync(path) !== path || !lstatSync(path).isFile()) throw Error('固定版本文件位置无效');
  return readFileSync(path);
}
export function dailyRelease(repo, args) {
  if (args[0] !== '--config' || !isAbsolute(args[1] ?? '')) return;
  const pointerPath = resolve(repo, '.local-data/daily/runtime-release.json');
  try { lstatSync(pointerPath); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  const raw = ordinary(pointerPath);
  const pointer = JSON.parse(raw);
  if (pointer.version !== 1 || Object.keys(pointer).sort().join() !== 'config,manifest_sha256,release,version'
      || typeof pointer.config !== 'string' || !isAbsolute(pointer.config) || resolve(pointer.config) !== pointer.config) throw Error('固定版本指向无效');
  if (pointer.config !== args[1]) return;
  const base = resolve(repo, '.local-data/releases');
  const release = pointer.release;
  if (typeof release !== 'string' || !isAbsolute(release) || realpathSync(release) !== release
      || !relative(base, release) || relative(base, release).startsWith('..') || isAbsolute(relative(base, release))) throw Error('固定版本目录无效');
  const manifestRaw = ordinary(join(release, 'release-manifest.json'));
  if (digest(manifestRaw) !== pointer.manifest_sha256) throw Error('固定版本清单已变化');
  const manifest = JSON.parse(manifestRaw);
  if (manifest.version !== 1 || !manifest.files || typeof manifest.files !== 'object' || Array.isArray(manifest.files)) throw Error('固定版本清单格式无效');
  const paths = Object.keys(manifest.files);
  for (const name of paths) {
    if (!name || isAbsolute(name) || name.split('/').some(p => !p || p === '.' || p === '..') || name.includes('\\')) throw Error('固定版本清单路径无效');
    if (digest(ordinary(join(release, name))) !== manifest.files[name]) throw Error('固定版本文件已变化：' + name);
  }
  const found = [];
  function walk(dir, prefix = '') {
    for (const item of readdirSync(dir, {withFileTypes:true})) {
      const name = prefix + item.name;
      if (name === 'release-manifest.json') continue;
      if (name === 'apps/desktop/node_modules') {
        if (realpathSync(join(dir,item.name)) !== realpathSync(join(repo,'apps/desktop/node_modules'))) throw Error('固定版本依赖位置变化');
        continue;
      }
      if (item.isDirectory()) walk(join(dir,item.name), name + '/');
      else if (item.isFile()) found.push(name);
      else throw Error('固定版本包含不允许的链接');
    }
  }
  walk(release);
  if (found.sort().join('\n') !== paths.sort().join('\n')) throw Error('固定版本含未登记文件');
  if (!paths.includes('apps/desktop/scripts/start_daily.mjs') || !paths.includes('apps/desktop/package-lock.json')
      || digest(ordinary(join(repo,'apps/desktop/package-lock.json'))) !== manifest.files['apps/desktop/package-lock.json']) throw Error('固定版本依赖锁不一致');
  return pathToFileURL(join(release, 'apps/desktop/scripts/start_daily.mjs')).href;
}
