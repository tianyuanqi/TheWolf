import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,symlinkSync} from 'node:fs';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {dailyRelease} from './daily_release.mjs';
const hash=x=>createHash('sha256').update(x).digest('hex');
test('pinned selection and fail-closed integrity without touching real config',()=>{
 const repo=mkdtempSync('/private/tmp/wolf-release-test-');
 try {
  const release=join(repo,'.local-data/releases/fixture'), config=join(repo,'private.json');
  const files={'apps/desktop/scripts/start_daily.mjs':'// fixed','apps/desktop/package-lock.json':'{}','contracts/generated/manifest.json':'{"fixed":true}'};
  for(const [name,body] of Object.entries(files)){mkdirSync(join(release,name,'..'),{recursive:true});writeFileSync(join(release,name),body);}
  mkdirSync(join(repo,'apps/desktop/node_modules'),{recursive:true});writeFileSync(join(repo,'apps/desktop/package-lock.json'),'{}');
  symlinkSync(join(repo,'apps/desktop/node_modules'),join(release,'apps/desktop/node_modules'));
  const manifest=JSON.stringify({version:1,files:Object.fromEntries(Object.entries(files).map(([p,s])=>[p,hash(s)]))});
  writeFileSync(join(release,'release-manifest.json'),manifest);
  const pointer={version:1,release,config,manifest_sha256:hash(manifest)};
  mkdirSync(join(repo,'.local-data/daily'),{recursive:true}); const pp=join(repo,'.local-data/daily/runtime-release.json');writeFileSync(pp,JSON.stringify(pointer));
  assert.match(dailyRelease(repo,['--config',config]),/fixture\/apps\/desktop\/scripts\/start_daily.mjs$/);
  assert.equal(dailyRelease(repo,['--config',join(repo,'isolated.json')]),undefined);
  // Shared development contract drift cannot change pinned entry or content.
  mkdirSync(join(repo,'contracts/generated'),{recursive:true});writeFileSync(join(repo,'contracts/generated/manifest.json'),'new development');
  assert.ok(dailyRelease(repo,['--config',config]));
  writeFileSync(join(release,'extra.py'),'unexpected');assert.throws(()=>dailyRelease(repo,['--config',config]),/未登记/);rmSync(join(release,'extra.py'));
  writeFileSync(join(release,'contracts/generated/manifest.json'),'changed');assert.throws(()=>dailyRelease(repo,['--config',config]),/文件已变化/);
  writeFileSync(join(release,'contracts/generated/manifest.json'),files['contracts/generated/manifest.json']);
  writeFileSync(join(repo,'apps/desktop/package-lock.json'),'new lock');assert.throws(()=>dailyRelease(repo,['--config',config]),/依赖锁/);writeFileSync(join(repo,'apps/desktop/package-lock.json'),'{}');
  writeFileSync(pp,JSON.stringify({...pointer,manifest_sha256:'0'.repeat(64)}));assert.throws(()=>dailyRelease(repo,['--config',config]),/清单已变化/);
  writeFileSync(pp,JSON.stringify({...pointer,release:repo}));assert.throws(()=>dailyRelease(repo,['--config',config]),/目录无效/);
 }finally{rmSync(repo,{recursive:true});}
});
