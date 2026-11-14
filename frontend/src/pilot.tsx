import React, {useEffect, useSyncExternalStore} from 'react';
import {createRoot} from 'react-dom/client';
import {SessionClient} from './session_client';
import './pilot.css';

window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#grant='))location.reload();});
let bootstrap:string|undefined;
if(location.hash.startsWith('#grant='))bootstrap=location.hash.slice(7);
if(location.hash)history.replaceState(null,'','/');
const session=new SessionClient(fetch.bind(window));
if(bootstrap){const grant=bootstrap;bootstrap=undefined;void session.authorize(grant);}
function App() {
  const view=useSyncExternalStore(session.subscribe,session.getSnapshot);
  useEffect(()=>()=>session.dispose(),[]);
  return <main><p className="eyebrow">HIDS · synthetic session pilot</p><h1>Local access check</h1>
    <p role="status" data-testid="status">{view.status}</p>
    {view.status==='Authorized'?<><p data-testid="example">{view.message}</p><button onClick={()=>void session.checkAccess()}>Check access</button> <button onClick={()=>void session.logout()}>Log out</button></>:
      <><p>This test shows synthetic information only. Open a new link authorized through root or sudo.</p><p>{view.notice}</p></>}
    <p className="note">Refreshing or closing this tab requires a new authorization. No monitoring starts here.</p>
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
