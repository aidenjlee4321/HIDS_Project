import React,{useEffect,useState,useSyncExternalStore} from 'react';
import {createRoot} from 'react-dom/client';
import {SessionClient} from './session_client';
import './pilot.css';
window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#grant='))location.reload();});
let bootstrap:string|undefined=location.hash.startsWith('#grant=')?location.hash.slice(7):undefined;
if(location.hash)history.replaceState(null,'','/');
const session=new SessionClient(fetch.bind(window),undefined,'dashboard');
if(bootstrap){const grant=bootstrap;bootstrap=undefined;void session.authorize(grant);}
type Loaded={generation:number;data:any};
function App(){
 const view=useSyncExternalStore(session.subscribe,session.getSnapshot);
 const [summary,setSummary]=useState<Loaded>();const [process,setProcess]=useState<Loaded>();const [events,setEvents]=useState<Loaded>();const [findings,setFindings]=useState<Loaded>();const [detail,setDetail]=useState<Loaded>();
 const current=(item:Loaded|undefined)=>view.status==='Authorized'&&item?.generation===view.generation?item.data:undefined;
 const load=async(path:string,set:(value:Loaded|undefined)=>void)=>{const value=await session.fetchProtected(path);if(value)set(value);};
 useEffect(()=>{
  setSummary(undefined);setProcess(undefined);setEvents(undefined);setFindings(undefined);setDetail(undefined);
  if(view.status==='Authorized')void (async()=>{
   const value=await session.fetchProtected('/v0/dashboard');if(!value)return;setSummary(value);
   const s=value.data as any;
   if(s.process?.available)void load('/v0/process/events',setProcess);
   if(s.history?.available){void load('/v0/history/events',setEvents);void load('/v0/history/findings',setFindings);}
  })();
 },[view.status,view.generation]);
 useEffect(()=>()=>session.dispose(),[]);
 const s=current(summary),p=current(process),e=current(events),f=current(findings),d=current(detail);
 return <main><p className="eyebrow">HIDS · stored history</p><h1>Overview</h1><p role="status" data-testid="status">{view.status}</p>
 {view.status==='Authorized'?<section data-testid="dashboard"><p>Frozen history. Current monitoring status: not assessed. Open a new root-authorized view to load a fresh snapshot.</p><button onClick={()=>void session.logout()}>Log out</button>
 {s&&<><p data-testid="counts">{s.process?.snapshot?.counts.events??'Unavailable'} process events · {s.history?.snapshot?.counts.events??'Unavailable'} Audit history events · {s.history?.snapshot?.counts.findings??'Unavailable'} informational findings</p>
 <p>Process snapshot: {s.process?.snapshot?.view_loaded_at??'Unavailable'}. Audit snapshot: {s.history?.snapshot?.view_loaded_at??'Unavailable'}.</p>
 {s.process?.snapshot?.truncated&&<p>Process snapshot truncated to its bounded limit. Earlier retained records are outside this view.</p>}
 {!s.process?.available&&<p>Process history unavailable. Other history remains independently accessible.</p>}
 {!s.history?.available&&<p>Audit history unavailable. Process history remains independently accessible.</p>}</>}
 <h2>Activity · process lifecycle</h2><p>Ordered by storage arrival. Activity wall time is not emitted by this source. Observation time is shown separately. These records are ordinary events.</p>
 {p?.available===false&&<p>Process page unavailable.</p>}
 {p?.items&&<><ul>{p.items.map((item:any)=><li key={item.event_id}><button data-testid="process-event" onClick={()=>void load('/v0/process/events/'+item.event_id,setDetail)}>{item.action} · PID {item.pid} · TID {item.tid}{item.pid!==item.tid?' · thread event':''}</button><p>Observed: {item.observed_at} · activity time: unavailable</p></li>)}</ul>{p.next_cursor&&<button onClick={()=>void load('/v0/process/events?cursor='+p.next_cursor,setProcess)}>Next process events</button>}</>}
 <h2>Activity · Audit history</h2><p>Ordered by import time, then event ID. This is not execution chronology.</p>
 {e?.available===false&&<p>Audit page unavailable.</p>}
 {e?.items&&<><ul>{e.items.map((item:any)=><li key={item.event_id}><button data-testid="event" onClick={()=>void load('/v0/history/events/'+item.event_id,setDetail)}>{item.exe_preview.text}{item.exe_preview.truncated?'… (truncated)':''} · PID {item.pid} · {item.evaluation_state}</button><p>Imported: {item.imported_at}</p></li>)}</ul>{e.next_cursor&&<button onClick={()=>void load('/v0/history/events?cursor='+e.next_cursor,setEvents)}>Next Audit events</button>}</>}
 <h2>Findings</h2>{f?.items&&<><ul>{f.items.map((item:any)=><li key={item.finding_id}><button data-testid="finding" onClick={()=>void load('/v0/history/findings/'+item.finding_id,setDetail)}>Informational · {item.rule_id}</button><p>{item.explanation}</p><button onClick={()=>void load('/v0/history/events/'+item.event_id,setDetail)}>Triggering event</button></li>)}</ul>{f.next_cursor&&<button onClick={()=>void load('/v0/history/findings?cursor='+f.next_cursor,setFindings)}>Next findings</button>}</>}
 {d&&<details open data-testid="detail"><summary>Technical detail</summary><p>Interval diagnostics describe the captured historical interval, not current health. Activity, observation and receipt times have distinct meanings. Nanoseconds and arrival ordinals are lossless decimal strings. No process executable or user identity is inferred.</p><pre className="history-detail">{JSON.stringify(d,null,2)}</pre></details>}
 </section>:<><p>Open a new link explicitly authorized through root or sudo.</p><p>{view.notice}</p></>}
 <p className="note">Closing or refreshing the tab requires a new authorization.</p></main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
