const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const file=path.join(__dirname,'../.work/patched/webview/assets/sites-end-resource-b8e3f57525e9.js');
const source=fs.readFileSync(file,'utf8');
const start=source.indexOf('function Ax(e){'),end=source.indexOf('function jx(',start);
assert.ok(start>=0&&end>start);
function render(enabled){
 const sent=[];
 const jsx=(type,props)=>({type,props});
 const context={Symbol,Mx:{c:()=>Array(50).fill(Symbol.for('react.memo_cache_sentinel'))},
  Nx:{useRef:()=>({current:null}),useState:()=>[null,()=>{}]},Px:{jsx,jsxs:jsx,Fragment:'Fragment'},
  Vn:()=>({formatMessage:x=>x.defaultMessage}),Zn:{Item:'MenuItem'},
  __codexRewind:{canRun:()=>enabled,run:async(...args)=>{sent.push(args);return{};}},
  props:{onFork:()=>{},memoryCitationEntries:[],open:true,onOpenChange:()=>{},rewindThreadId:'chat',rewindTurnId:'target'},console
 };
 for(const name of ['vr','f','Y','be','Tr','Un','dn','ar','jr','We','Wn','bt','My','Ny','Py'])context[name]=name;
 vm.runInNewContext(source.slice(start,end)+';result=Ax(props);',context);
 const menu=context.result.props.children[0];
 const first=menu.props.children[0];
 assert.equal(first.type,'Fragment');
 const [branch,rewind]=first.props.children;
 assert.equal(branch.props.children.props.id,'assistantMessageContent.branchInNewChatTooltip');
 assert.equal(rewind.props.children,'回退到本轮之前');
 assert.equal(rewind.props.disabled,!enabled);
 return {rewind,sent};
}
(async()=>{const {rewind,sent}=render(true);rewind.props.onSelect();await Promise.resolve();assert.deepEqual(Array.from(sent[0]),['chat','target']);render(false);console.log('PASS: actual patched menu renders rewind immediately below branch; target turn is forwarded; unsupported state disables it.');})().catch(e=>{console.error(e);process.exitCode=1;});
