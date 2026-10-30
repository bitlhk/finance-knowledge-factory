// Fetch only the already-authorized managed connection; never log the catalog.
const WebSocket = require(process.env.EMPLOYEE_WS_MODULE || '/home/ubuntu/employee-agent/node_modules/ws');
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const state = process.argv[2];
if (!state || !path.isAbsolute(state)) throw new Error('Usage: node start-managed.cjs /absolute/isolated-state-directory');
fs.mkdirSync(state, {recursive:true, mode:0o700});
const ws = new WebSocket('ws://127.0.0.1:19000/ws');
const id = 'knowledge-production-connection-' + Date.now();
const timer = setTimeout(()=>{ws.terminate();process.stderr.write('Managed connection timeout\n');process.exitCode=1;},15000);
ws.on('open',()=>ws.send(JSON.stringify({type:'req',id,method:'models.list',params:{}})));
ws.on('error',()=>{clearTimeout(timer);process.stderr.write('Managed connection unavailable\n');process.exitCode=1;});
ws.on('message',raw=>{
  let result;
  try { result = JSON.parse(raw.toString()); } catch {return;}
  if (result.id!==id) return;
  clearTimeout(timer);ws.close();
  const m=result.payload?.models?.find(m=>m.model_name==='deepseek-v4-flash');
  if(!m?.api_key || !m?.api_base?.startsWith('https://')) {process.stderr.write('Managed DeepSeek connection not available\n');process.exitCode=1;return;}
  const log=fs.openSync(path.join(state,'server.log'),'a',0o600);
  const cpFile=path.join(root,'.m1-local','flowable-classpath.txt');
  const cp=fs.existsSync(cpFile)?path.join(root,'probes/flowable/target/classes')+':'+fs.readFileSync(cpFile,'utf8').trim():'';
  const child=spawn('python3',['-m','web_production.server','--port','61352','--state',state],{
    cwd:root,detached:true,stdio:['ignore',log,log],
    env:{...process.env,OPENAI_API_KEY:m.api_key,OPENAI_BASE_URL:m.api_base,OPENAI_MODEL:m.model_name,
         KNOWLEDGE_FLOWABLE_CLASSPATH:cp}});
  child.on('error',()=>{process.stderr.write('Preview process failed to start\n');process.exitCode=1;});
  child.unref();fs.closeSync(log);
  process.stdout.write('Preview process requested: PID '+child.pid+'; verify http://127.0.0.1:61352/api/state\n');
});
