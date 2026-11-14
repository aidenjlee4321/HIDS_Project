import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SessionClient} from '../../frontend/src/session_client.ts';
const response=(data:object,status=200)=>new Response(JSON.stringify(data),{status});
const auth=()=>response({token:'A'.repeat(43),scope:'pilot:read',idle_seconds:300,absolute_seconds:1800});
const example=(message='synthetic')=>response({synthetic:true,message});
function deferred(){let resolve!:(value:Response)=>void;let reject!:(reason:Error)=>void;const promise=new Promise<Response>((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
function setup(){
 let now=0,id=0;const timers=new Map<number,{fn:()=>void,at:number}>();
 const clock={now:()=>now,set:(fn:()=>void,ms:number)=>{const key=++id;timers.set(key,{fn,at:now+ms});return key;},clear:(key:unknown)=>{timers.delete(key as number);}};
 const queue:Array<Promise<Response>>=[];
 const calls:Array<{path:string,init?:RequestInit}>=[];
 const fetcher=(async(path:unknown,init?:RequestInit)=>{calls.push({path:String(path),init});return queue.length?await queue.shift()!:String(path).endsWith('/redeem')?auth():String(path).endsWith('/logout')?response({logged_out:true}):example();}) as typeof fetch;
 const client=new SessionClient(fetcher,clock);
 return {client,queue,calls,advance:(ms:number)=>{now+=ms;for(const [key,t] of [...timers])if(t.at<=now){timers.delete(key);t.fn();}}};
}
test('late success after logout never restores display',async()=>{
 const s=setup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);
 const check=s.client.checkAccess();const logout=s.client.logout();
 assert.equal(s.client.getSnapshot().status,'Locked');assert.equal(s.client.getSnapshot().message,'');
 assert.equal(s.calls.at(-2)?.init?.signal?.aborted,true);
 d.resolve(example('SECRET_OLD'));await Promise.all([check,logout]);assert.equal(s.client.getSnapshot().message,'');
});
test('late failure cannot clear newer authorized session',async()=>{
 const s=setup();await s.client.authorize('first');const d=deferred();s.queue.push(d.promise);const check=s.client.checkAccess();
 await s.client.logout();await s.client.authorize('second');d.reject(new Error('late'));await check;
 assert.equal(s.client.getSnapshot().status,'Authorized');assert.equal(s.client.getSnapshot().message,'synthetic');
});
test('overlapping authorizations ignore stale redemption',async()=>{
 const s=setup();const d=deferred();s.queue.push(d.promise);const first=s.client.authorize('first');
 await s.client.authorize('second');d.resolve(auth());await first;
 assert.equal(s.client.getSnapshot().status,'Authorized');assert.equal(s.calls.filter(x=>x.path==='/v0/pilot').length,1);
});
test('idle expiry rejects an already authorized in-flight response',async()=>{
 const s=setup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const check=s.client.checkAccess();
 s.advance(300_000);d.resolve(example('EXPIRED'));await check;
 assert.equal(s.client.getSnapshot().status,'Locked');assert.equal(s.client.getSnapshot().message,'');
});
test('current successful activity renews idle display deadline',async()=>{
 const s=setup();await s.client.authorize('grant');s.advance(200_000);await s.client.checkAccess();s.advance(200_000);
 assert.equal(s.client.getSnapshot().status,'Authorized');s.advance(100_000);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('activity never renews absolute deadline',async()=>{
 const s=setup();await s.client.authorize('grant');for(let i=0;i<8;i++){s.advance(200_000);await s.client.checkAccess();}
 s.advance(200_000);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('late logout completion cannot replace new session',async()=>{
 const s=setup();await s.client.authorize('first');const d=deferred();s.queue.push(d.promise);const logout=s.client.logout();
 await s.client.authorize('second');d.resolve(response({logged_out:true}));await logout;assert.equal(s.client.getSnapshot().status,'Authorized');
});
test('stale success cannot replace new session message',async()=>{
 const s=setup();await s.client.authorize('first');const d=deferred();s.queue.push(d.promise);const check=s.client.checkAccess();
 await s.client.authorize('second');d.resolve(example('OLD'));await check;assert.equal(s.client.getSnapshot().message,'synthetic');
});
test('current denial clears all rendered data',async()=>{
 const s=setup();await s.client.authorize('first');s.queue.push(Promise.resolve(response({},403)));await s.client.checkAccess();
 assert.equal(s.client.getSnapshot().status,'Locked');assert.equal(s.client.getSnapshot().message,'');assert.equal(s.client.getSnapshot().notice,'');
});

function historySetup(){
 const queue:Array<Promise<Response>>=[];let now=0;
 const clock={now:()=>now,set:()=>0,clear:()=>{}};
 const summary={format:'hids.m4.history-view/1',history_only:true,monitoring_status:'not_assessed'};
 const fetcher=(async(path:unknown)=>queue.length?await queue.shift()!:String(path).endsWith('/redeem')?response({token:'A'.repeat(43),scope:'history:read',idle_seconds:300,absolute_seconds:1800}):response(summary)) as typeof fetch;
 return {client:new SessionClient(fetcher,clock,'history'),queue,advance:()=>{now=300_000;}};
}
test('history authorizes only explicit history scope',async()=>{
 const s=historySetup();await s.client.authorize('grant');assert.equal(s.client.getSnapshot().status,'Authorized');
 const p=historySetup();p.queue.push(Promise.resolve(auth()));await p.client.authorize('grant');assert.equal(p.client.getSnapshot().status,'Locked');
});
test('history response after logout is discarded even if transport ignores abort',async()=>{
 const s=historySetup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.fetchProtected('/v0/history/events');await s.client.logout();d.resolve(response({secret:'old'}));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('old history failure cannot clear newer authorization',async()=>{
 const s=historySetup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.fetchProtected('/v0/history/findings');await s.client.authorize('new');d.reject(new Error('late'));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Authorized');
});
test('expired history response cannot produce renderable data',async()=>{
 const s=historySetup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.fetchProtected('/v0/history/events/'+'a'.repeat(64));s.advance();d.resolve(response({secret:'old'}));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('history data carries authorization generation and rejects arbitrary routes',async()=>{
 const s=historySetup();await s.client.authorize('grant');const data=await s.client.fetchProtected('/v0/history');assert.equal(data?.generation,s.client.getSnapshot().generation);await s.client.authorize('new');assert.notEqual(data?.generation,s.client.getSnapshot().generation);assert.equal(await s.client.fetchProtected('https://evil.example/'),undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});

function setupFlow(){
 const queue:Array<Promise<Response>>=[];let now=0;const clock={now:()=>now,set:()=>0,clear:()=>{}};
 const fetcher=(async(path:unknown)=>queue.length?await queue.shift()!:String(path).endsWith('/redeem')?response({token:'A'.repeat(43),scope:'setup:draft',idle_seconds:300,absolute_seconds:1800}):String(path).endsWith('/draft')?response({reference:'B'.repeat(43),expires_seconds:60,requires_root_confirmation:true}):response({format:'hids.setup-view/1',snapshot_only:true,monitoring_status:'not_assessed'})) as typeof fetch;
 return {client:new SessionClient(fetcher,clock,'setup'),queue,advance:()=>{now=300_000;}};
}
const draft={assessment_id:'a'.repeat(32),confirmed_revision:0,selected:[]};
test('setup scope and draft require independent root confirmation',async()=>{
 const s=setupFlow();await s.client.authorize('grant');assert.equal(s.client.getSnapshot().status,'Authorized');const result=await s.client.stageDraft(draft);assert.equal((result?.data as any).requires_root_confirmation,true);assert.equal(result?.generation,s.client.getSnapshot().generation);
});
test('late setup draft after logout cannot restore a reference',async()=>{
 const s=setupFlow();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.stageDraft(draft);await s.client.logout();d.resolve(response({reference:'B'.repeat(43),expires_seconds:60,requires_root_confirmation:true}));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('expired setup response is discarded',async()=>{
 const s=setupFlow();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.stageDraft(draft);s.advance();d.resolve(response({reference:'B'.repeat(43),expires_seconds:60,requires_root_confirmation:true}));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('old setup failure cannot invalidate newer authorization',async()=>{
 const s=setupFlow();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.stageDraft(draft);await s.client.authorize('new');d.reject(new Error('late'));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Authorized');
});
test('setup client rejects history access and wrong issued scope',async()=>{
 const s=setupFlow();await s.client.authorize('grant');assert.equal(await s.client.fetchProtected('/v0/history'),undefined);assert.equal(s.client.getSnapshot().status,'Locked');
 const p=setupFlow();p.queue.push(Promise.resolve(auth()));await p.client.authorize('grant');assert.equal(p.client.getSnapshot().status,'Locked');
});

function dashboardSetup(){
 const queue:Array<Promise<Response>>=[];let now=0;
 const clock={now:()=>now,set:()=>0,clear:()=>{}};
 const summary={format:'hids.dashboard-view/1',history_only:true,monitoring_status:'not_assessed',process:{available:false},history:{available:true}};
 const fetcher=(async(path:unknown)=>queue.length?await queue.shift()!:String(path).endsWith('/redeem')?response({token:'A'.repeat(43),scope:'dashboard:read',idle_seconds:300,absolute_seconds:1800}):response(summary)) as typeof fetch;
 return {client:new SessionClient(fetcher,clock,'dashboard'),queue,expire:()=>{now=300_000;}};
}
test('dashboard mode accepts only its explicitly issued scope',async()=>{
 const s=dashboardSetup();s.queue.push(Promise.resolve(auth()));await s.client.authorize('grant');assert.equal(s.client.getSnapshot().status,'Locked');
 await s.client.authorize('fresh');assert.equal(s.client.getSnapshot().status,'Authorized');s.client.dispose();
});
test('one unavailable family keeps dashboard authorization usable',async()=>{
 const s=dashboardSetup();await s.client.authorize('grant');s.queue.push(Promise.resolve(response({},404)));
 assert.deepEqual((await s.client.fetchProtected('/v0/process/events'))?.data,{available:false});assert.equal(s.client.getSnapshot().status,'Authorized');
 assert.ok(await s.client.fetchProtected('/v0/history/events'));s.client.dispose();
});
test('late unavailable family after logout cannot restore data',async()=>{
 const s=dashboardSetup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.fetchProtected('/v0/process/events');await s.client.logout();d.resolve(response({},404));
 assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('dashboard expiry still rejects unavailable and successful responses',async()=>{
 const s=dashboardSetup();await s.client.authorize('grant');const d=deferred();s.queue.push(d.promise);const pending=s.client.fetchProtected('/v0/process/events');s.expire();d.resolve(response({},404));assert.equal(await pending,undefined);assert.equal(s.client.getSnapshot().status,'Locked');
});
test('dashboard route allowlist excludes setup writes and arbitrary paths',async()=>{
 for(const path of ['/v0/setup','/v0/process/events?limit=100','/v0/process/events/../../etc/passwd']){
  const s=dashboardSetup();await s.client.authorize('grant');assert.equal(await s.client.fetchProtected(path),undefined);assert.equal(s.client.getSnapshot().status,'Locked');s.client.dispose();
 }
});
