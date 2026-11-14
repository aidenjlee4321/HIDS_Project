import React,{useEffect,useState,useSyncExternalStore} from 'react';
import {createRoot} from 'react-dom/client';
import {SessionClient} from './session_client';
import './pilot.css';
window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#grant='))location.reload();});
let bootstrap:string|undefined=location.hash.startsWith('#grant=')?location.hash.slice(7):undefined;
if(location.hash)history.replaceState(null,'','/');
const session=new SessionClient(fetch.bind(window),undefined,'setup');
if(bootstrap){const grant=bootstrap;bootstrap=undefined;void session.authorize(grant);}
type Loaded={generation:number;data:any;expiresAt?:number};
function App(){
 const view=useSyncExternalStore(session.subscribe,session.getSnapshot);const [snapshot,setSnapshot]=useState<Loaded>();const [draft,setDraft]=useState<Loaded>();const [choices,setChoices]=useState<{generation:number;ids:string[]}>();
 const current=(item:Loaded|undefined)=>view.status==='Authorized'&&item?.generation===view.generation?item.data:undefined;
 const s=current(snapshot),d=current(draft);const ids=view.status==='Authorized'&&choices?.generation===view.generation?choices.ids:[];
 useEffect(()=>{
  setSnapshot(undefined);setDraft(undefined);setChoices(undefined);
  if(view.status==='Authorized')void session.fetchProtected('/v0/setup').then(value=>{
   if(!value)return;const data=value.data as any;setSnapshot(value);
   const eligible=data.sources.filter((source:any)=>source.preflight==='eligible').map((source:any)=>source.id);
   setChoices({generation:value.generation,ids:data.confirmed.revision===0?eligible:data.confirmed.selected.filter((id:string)=>eligible.includes(id))});
  });
 },[view.status,view.generation]);
 useEffect(()=>()=>session.dispose(),[]);
 useEffect(()=>{if(!draft?.expiresAt)return;const id=setTimeout(()=>setDraft(current=>current===draft?undefined:current),Math.max(0,draft.expiresAt-performance.now()));return ()=>clearTimeout(id);},[draft]);
 async function stage(){if(!s)return;setDraft(undefined);const started=performance.now();const value=await session.stageDraft({assessment_id:s.assessment_id,confirmed_revision:s.confirmed.revision,selected:ids});if(value&&performance.now()<started+60000)setDraft({...value,expiresAt:started+60000});}
 return <main><p className="eyebrow">HIDS · first-run setup trial</p><h1>Choose monitoring sources</h1><p role="status" data-testid="status">{view.status}</p>
 {view.status==='Authorized'?<section data-testid="setup"><p>Stored preflight snapshot. Monitoring status: not assessed.</p><p>Choices and recommendations do not start collection. Root or sudo confirmation is required. Saved choices require fresh activation after restart.</p><button onClick={()=>void session.logout()}>Log out</button>
 {s&&<><p>Assessment prepared: {s.assessed_at}</p><p data-testid="saved-selection">Saved choices: {s.confirmed.selected.join(', ')||'none'} · revision {s.confirmed.revision}</p>
 {s.sources.map((source:any)=><section key={source.id}><label><input type="checkbox" data-testid={'source-'+source.id} checked={ids.includes(source.id)} disabled={source.preflight!=='eligible'} onChange={e=>{setDraft(undefined);setChoices({generation:view.generation,ids:e.target.checked?[...ids,source.id]:ids.filter(id=>id!==source.id)});}}/>{source.label}</label><p>{source.preflight==='eligible'?'Recommended by preflight; runtime unproven':source.preflight}</p><p>{source.limitation}</p><details><summary>Preflight details</summary><pre className="history-detail">{JSON.stringify({implementation:source.implementation,checks:source.checks,provenance:source.provenance},null,2)}</pre></details></section>)}
 <button onClick={()=>void stage()}>Prepare root review</button><p>Changing boxes is local. Prepare a new review to replace an earlier staged draft. Empty choices mean no source will be initialized.</p>
 {d&&<section data-testid="draft"><h2>Root confirmation required</h2><p>This review reference expires after 60 seconds. Open the root setup CLI in a private terminal, choose review or confirm/start, then enter the reference at its prompt. Never put it in command arguments or logs.</p><code data-testid="review-reference">{d.reference}</code><p>Stop owned sources before editing active choices. No host logging settings change.</p></section>}</>}
 </section>:<><p>Open a new setup link explicitly authorized through root or sudo.</p><p>{view.notice}</p></>}
 </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
