const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const assert=require('node:assert/strict');
const api=require('../src/rewind-controller.js');
const artifacts=path.join(__dirname,'../.work/live-test');
fs.mkdirSync(artifacts,{recursive:true});
const cwd=path.join(artifacts,'workspace');
fs.mkdirSync(cwd,{recursive:true});
const marker=path.join(cwd,'rewind-marker.txt');
fs.writeFileSync(marker,'BASELINE_REWIND_TEST\n');
const exe=process.argv[2] || process.env.CODEX_BINARY || 'codex';
const child=spawn(exe,['app-server','--stdio'],{cwd,windowsHide:true,stdio:['pipe','pipe','pipe']});
let sequence=0,threadId,rawThread,lastTurn;
const pending=new Map(), notifications=new Set(), prompts=new Map();
let diagnostic='';
child.stderr.on('data',chunk=>{diagnostic=(diagnostic+chunk.toString()).slice(-12000);});
const lines=readline.createInterface({input:child.stdout});
lines.on('line',line=>{
  let message;try{message=JSON.parse(line);}catch{return;}
  if(message.id!==undefined && !message.method){
    const p=pending.get(message.id);if(!p)return;pending.delete(message.id);
    message.error?p.reject(Error(JSON.stringify(message.error))):p.resolve(message.result);
  }else if(message.id!==undefined && message.method){
    // Never auto-grant approval requests during an integration test.
    child.stdin.write(JSON.stringify({id:message.id,result:{decision:'decline'}})+'\n');
  }else for(const fn of notifications)fn(message);
});
function request(method,params){return new Promise((resolve,reject)=>{
  const id=++sequence;pending.set(id,{resolve,reject});child.stdin.write(JSON.stringify({id,method,params})+'\n');
});}
async function start(prompt){
  let resolveFinished;
  const done=new Promise(resolve=>{resolveFinished=resolve;});
  const listener=message=>{if(message.method==='turn/completed'&&message.params.threadId===threadId){lastTurn=message.params.turn;resolveFinished(lastTurn);}};
  notifications.add(listener);
  try{
    const response=await request('turn/start',{threadId,input:[{type:'text',text:prompt,text_elements:[]}]});
    prompts.set(response.turn.id,prompt);
    const completed=await done;
    if(completed.status!=='completed')throw Error('Test turn status '+completed.status+' '+JSON.stringify(completed.error));
    return completed;
  }finally{notifications.delete(listener);}
}
async function turns(){
  const response=await request('thread/turns/list',{threadId,itemsView:'full',limit:100,sortDirection:'asc'});
  return response.data.map(t=>({...t,turnId:t.id,params:{input:[{type:'text',text:prompts.get(t.id)||''}]}}));
}
const timeout=setTimeout(()=>{console.error('Integration test timed out.');child.kill();process.exitCode=1;},240000);
(async()=>{
  const init=await request('initialize',{clientInfo:{name:'codex_rewind_selftest',title:'Codex Rewind self-test',version:'0.1.0'},capabilities:{experimentalApi:true}});
  child.stdin.write(JSON.stringify({method:'initialized',params:{}})+'\n');
  const response=await request('thread/start',{cwd,approvalPolicy:'on-request',sandbox:'workspace-write',serviceName:'codex-rewind-selftest',developerInstructions:'This is an isolated integration test. Only edit rewind-marker.txt and recovery copies in .codex-rewind-backups within the current test workspace. Do not read or change other projects, memories, settings or remote services. Do not spawn agents. Keep answers concise.'});
  rawThread=response.thread;threadId=rawThread.id;
  fs.writeFileSync(path.join(artifacts,'live-rewind-thread.json'),JSON.stringify({threadId,cwd},null,2));
  console.log('Created isolated test thread.');
  await start('Reply BASELINE_OK only. Do not use tools or modify files.');
  console.log('Baseline turn completed.');
  const target=await start('Read rewind-marker.txt, then use apply_patch to change its one line from BASELINE_REWIND_TEST to CHANGED_REWIND_TEST. Make no other changes. Finish by saying marker changed.');
  assert.equal(fs.readFileSync(marker,'utf8').trim(),'CHANGED_REWIND_TEST');
  console.log('Real model changed the isolated marker file.');
  let completeListener;
  const manager={
    getHostId:()=> 'local',getStreamRole:()=>({role:'owner'}),
    getConversation:()=>({historyMode:'paginated',resumeState:'resumed',cwd}),
    getCompleteConversationTurns:turns,
    addTurnCompletedListener:fn=>{completeListener=fn;return()=>{completeListener=null;};},
    addConversationStateCallback:()=>()=>{},
    sendFollowUpMessage:async(id,options)=>{await start(options.prompt);await completeListener?.({conversationId:threadId,turnId:lastTurn.id});},
    sendRequest:request,applyRevertResponseToConversation:()=>{}
  };
  const result=await api.run(threadId,target.id,{manager,timeoutMs:180000,
    saveRun:async record=>fs.writeFileSync(path.join(artifacts,'live-rewind-record.json'),JSON.stringify(record,null,2)),
    panel:{update:(message,done,success)=>console.log(done?(success?'Completed.':'Incomplete: '+message):'Rollback running.')}
  });
  assert.equal(result.status,'complete',result.error);
  assert.equal(fs.readFileSync(marker,'utf8').trim(),'BASELINE_REWIND_TEST');
  const retained=await turns();assert.equal(retained.length,1);assert.equal(retained[0].turnId,result.historyBefore[0].turnId);
  // Verify persisted history rather than only the renderer's in-memory update.
  await request('thread/resume',{threadId,excludeTurns:true});
  assert.equal((await turns()).length,1);
  await request('thread/archive',{threadId});
  const evidence={status:'passed',backend:init.userAgent||'local Codex',retainedTurns:1,fileRestored:true,resumeVerified:true,testThreadArchived:true};
  fs.writeFileSync(path.join(artifacts,'live-rewind-result.json'),JSON.stringify(evidence,null,2));
  console.log(JSON.stringify(evidence));
})().catch(async error=>{console.error(error.message);fs.writeFileSync(path.join(artifacts,'live-rewind-error.log'),error.stack+'\n'+diagnostic);if(threadId)await request('thread/archive',{threadId}).catch(()=>{});process.exitCode=1;})
.finally(()=>{clearTimeout(timeout);child.stdin.end();child.kill();lines.close();});
