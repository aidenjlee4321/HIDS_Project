import React,{useEffect,useState,useSyncExternalStore} from 'react';
import {createRoot} from 'react-dom/client';
import {SessionClient} from './session_client';
import './pilot.css';
window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#grant='))location.reload();});
let bootstrap:string|undefined=location.hash.startsWith('#grant=')?location.hash.slice(7):undefined;
if(location.hash)history.replaceState(null,'','/');
const session=new SessionClient(fetch.bind(window),undefined,'history');
if(bootstrap){const grant=bootstrap;bootstrap=undefined;void session.authorize(grant);}
type Loaded={generation:number;data:any};
function App(){
 const view=useSyncExternalStore(session.subscribe,session.getSnapshot);
 const [summary,setSummary]=useState<Loaded>();const [events,setEvents]=useState<Loaded>();const [findings,setFindings]=useState<Loaded>();const [detail,setDetail]=useState<Loaded>();
 const current=(item:Loaded|undefined)=>view.status==='Authorized'&&item?.generation===view.generation?item.data:undefined;
 const load=async(path:string,set:(value:Loaded|undefined)=>void)=>{const value=await session.fetchProtected(path);if(value)set(value);};
 useEffect(()=>{
  setSummary(undefined);setEvents(undefined);setFindings(undefined);setDetail(undefined);
  if(view.status==='Authorized'){
   void load('/v0/history',setSummary);void load('/v0/history/events',setEvents);void load('/v0/history/findings',setFindings);
  }
 },[view.status,view.generation]);
 useEffect(()=>()=>session.dispose(),[]);
 const s=current(summary),e=current(events),f=current(findings),d=current(detail);
 return <main><p className="eyebrow">HIDS · stored snapshot trial</p><h1>Overview</h1><p role="status" data-testid="status">{view.status}</p>
 {view.status==='Authorized'?<section data-testid="history"><p>Stored snapshot. Monitoring status: not assessed. Collection does not start here.</p><button onClick={()=>void session.logout()}>Log out</button>
 {s&&<><p data-testid="counts">{s.counts.events} events · {s.counts.findings} informational findings · {s.counts.unevaluated} unevaluated events</p><p>Snapshot prepared: {s.view_loaded_at}</p></>}
 <h2>Activity</h2><p>Sorted by import time, then event ID. This is not execution chronology.</p>
 {e&&<><ul>{e.items.map((item:any)=><li key={item.event_id}><button data-testid="event" onClick={()=>void load('/v0/history/events/'+item.event_id,setDetail)}>{item.exe_preview.text}{item.exe_preview.truncated?'… (truncated)':''} · PID {item.pid} · {item.evaluation_state}</button><p>Imported: {item.imported_at}</p></li>)}</ul>{e.next_cursor&&<button onClick={()=>void load('/v0/history/events?cursor='+e.next_cursor,setEvents)}>Next events</button>}</>}
 <h2>Findings</h2>{f&&<><ul>{f.items.map((item:any)=><li key={item.finding_id}><button data-testid="finding" onClick={()=>void load('/v0/history/findings/'+item.finding_id,setDetail)}>Informational · {item.rule_id}</button><p>{item.explanation}</p><button onClick={()=>void load('/v0/history/events/'+item.event_id,setDetail)}>Triggering event</button></li>)}</ul>{f.next_cursor&&<button onClick={()=>void load('/v0/history/findings?cursor='+f.next_cursor,setFindings)}>Next findings</button>}</>}
 {d&&<details open data-testid="detail"><summary>Technical detail</summary><p>Null means unavailable. Result, offsets and nanosecond values are lossless decimal strings. Native exe/comm values are Base64 bytes.</p><pre className="history-detail">{JSON.stringify(d,null,2)}</pre></details>}
 </section>:<><p>Open a new link explicitly authorized through root or sudo.</p><p>{view.notice}</p></>}
 <p className="note">No automatic refresh. Closing or refreshing the tab requires a new authorization.</p></main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
