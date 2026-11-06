/** 自有监护管道的Vite worker；启动前固定运行目录与缓存身份。 */
import { createServer } from '../node_modules/vite/dist/node/index.js';
import { readFileSync, lstatSync, createReadStream } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../',import.meta.url));
const run = process.env.WOLF_MANAGED_RUN;
if (!run || lstatSync(run).isSymbolicLink() || process.env.WOLF_VITE_CACHE !== resolve(run,'vite-cache')) throw new Error('托管缓存位置无效');
const mark=JSON.parse(readFileSync(resolve(run,'owner.json'),'utf8'));
const descriptor=JSON.parse(readFileSync(resolve(run,'connection.json'),'utf8'));
const stat=lstatSync(run);
if (stat.dev!==mark.device || stat.ino!==mark.inode || descriptor.run_id!==mark.run_id || descriptor.connection_mode!=='managed') throw new Error('托管运行身份无效');
let server, closing=false, closePromise, command='';
async function close(){
  closing=true;
  if(!server) return;
  closePromise ??= server.close();
  await closePromise;
  // 显式stop已关闭服务器；结束本worker残余事件句柄。意外EOF仍保留组watchdog。
  if(command==='stop\n') process.exit(0);
}
const watch=createReadStream(null,{fd:Number(process.env.WOLF_MANAGED_WATCH_FD),autoClose:true});
watch.on('data',data=>{ command+=data.toString(); if(command==='stop\n') void close(); });
watch.on('end',()=>{
  if(command!=='stop\n') {
    const group=Number(process.env.WOLF_MANAGED_PGID);
    setTimeout(()=>process.kill(-group,'SIGKILL'),7000);
  }
  void close();
});
process.on('SIGTERM',()=>void close());process.on('SIGINT',()=>void close());
server=await createServer({root,configFile:resolve(root,'vite.config.ts'),configLoader:'runner'});
if(closing) await close(); else await server.listen();
