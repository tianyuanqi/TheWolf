/** 新托管入口的前置拒绝：不启动桌面、不接触真实根或安装环境。 */
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {mkdtempSync,writeFileSync,symlinkSync,rmSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const launcher=fileURLToPath(new URL('start_daily.mjs',import.meta.url));
function run(variant){
 const root=mkdtempSync('/private/tmp/wolf-entry-reject-');
 try{
  const config=root+'/config.json';writeFileSync(config,JSON.stringify({python:'/usr/bin/false'}));
  const env=Object.fromEntries(Object.entries(process.env).filter(([key])=>!key.startsWith('WOLF_')));
  let args=['--config',config,'--no-open'];
  if(variant==='missing')args=[];
  if(variant==='extra')args.push('--index-write');
  if(variant==='environment')env.WOLF_SERVICE_PORT='9';
  if(variant==='link'){symlinkSync(config,root+'/link.json');args[1]=root+'/link.json';}
  if(variant==='large')writeFileSync(config,' '.repeat(65537));
  return spawnSync(process.execPath,[launcher,...args],{env,encoding:'utf8',timeout:10000});
 }finally{rmSync(root,{recursive:true});}
}
for(const [variant,pattern]of [['missing',/用法/],['extra',/用法/],['environment',/拒绝继承WOLF/],['link',/普通文件/],['large',/配置过大/],['failed',/启动未完成/]]){
 test(variant+'拒绝且不打印可用入口',()=>{const result=run(variant);assert.notEqual(result.status,0);assert.match(result.stderr,pattern);assert.doesNotMatch(result.stdout,/行情总览：/);if(variant==='failed'){assert.match(result.stderr,/已核验本次自有进程组退出/);assert.match(result.stderr,/未取得本次运行目录身份/);}});
}
