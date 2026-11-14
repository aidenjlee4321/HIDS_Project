export type SessionView = Readonly<{status:'Locked'|'Authorizing'|'Authorized'; message:string; notice:string; generation:number}>;
type Timing = {now:()=>number; set:(fn:()=>void,ms:number)=>unknown; clear:(id:unknown)=>void};
const timing: Timing = {now:()=>performance.now(), set:(fn,ms)=>setTimeout(fn,ms), clear:id=>clearTimeout(id as ReturnType<typeof setTimeout>)};
class Superseded extends Error {}
class FamilyUnavailable extends Error {}

// State and credentials are volatile. Every asynchronous continuation must belong
// to the current authorization generation before it can publish or invalidate.
export class SessionClient {
  private transport: typeof fetch;
  private mode: 'pilot'|'history'|'setup'|'dashboard';
  private time: Timing;
  private generation = 0;
  private bearer: string | undefined;
  private absolute = 0;
  private idle = 0;
  private timer: unknown;
  private pending = new Set<AbortController>();
  private listeners = new Set<()=>void>();
  private view: SessionView = {status:'Locked',message:'',notice:'',generation:0};
  constructor(transport: typeof fetch, clock: Timing = timing, mode:'pilot'|'history'|'setup'|'dashboard'='pilot') {this.transport=transport;this.time=clock;this.mode=mode;}
  getSnapshot = () => this.view;
  subscribe = (fn:()=>void) => {this.listeners.add(fn);return ()=>{this.listeners.delete(fn);};};
  private publish(view:Omit<SessionView,'generation'>) {this.view={...view,generation:this.generation};for(const fn of this.listeners)fn();}
  private clear() {
    ++this.generation;
    for(const controller of this.pending)controller.abort();
    this.pending.clear();this.time.clear(this.timer);this.timer=undefined;
    this.bearer=undefined;this.absolute=0;this.idle=0;
  }
  private lock(notice='') {this.clear();this.publish({status:'Locked',message:'',notice});}
  private current(epoch:number) {if(epoch!==this.generation)throw new Superseded();}
  private unexpired(epoch:number) {
    this.current(epoch);
    if(this.time.now()>=Math.min(this.idle,this.absolute)) {this.lock();throw new Superseded();}
  }
  private arm(epoch:number) {
    this.time.clear(this.timer);
    this.timer=this.time.set(()=>{
      if(epoch!==this.generation)return;
      if(this.time.now()>=Math.min(this.idle,this.absolute))this.lock();
      else this.arm(epoch);
    },Math.max(0,Math.min(this.idle,this.absolute)-this.time.now()));
  }
  private async request(path:string,epoch:number,token?:string,body?:object) {
    this.current(epoch);
    const controller=new AbortController();this.pending.add(controller);
    try {
      const headers:Record<string,string>={};
      if(token)headers.Authorization=`Bearer ${token}`;
      if(body!==undefined)headers['Content-Type']='application/json';
      const response=await this.transport(path,{method:body===undefined?'GET':'POST',headers,
        body:body===undefined?undefined:JSON.stringify(body),signal:controller.signal,
        credentials:'omit',cache:'no-store',redirect:'error'});
      this.current(epoch);
      if(this.mode==='dashboard'&&response.status===404)throw new FamilyUnavailable();
      if(!response.ok)throw new Error('denied');
      const value=await response.json();this.current(epoch);return value;
    } finally {this.pending.delete(controller);}
  }
  async authorize(grant:string) {
    this.clear();const epoch=this.generation;const started=this.time.now();
    this.publish({status:'Authorizing',message:'',notice:''});
    try {
      const data=await this.request('/v0/auth/redeem',epoch,undefined,{grant});
      if(typeof data.token!=='string'||!/^[A-Za-z0-9_-]{43}$/.test(data.token)||data.scope!==(this.mode==='setup'?'setup:draft':this.mode+':read')||data.idle_seconds!==300||data.absolute_seconds!==1800)throw new Error('invalid grant');
      this.bearer=data.token;
      // Starting the presentation clock before redemption is conservative about
      // network delay. Backend expiry remains independently authoritative.
      this.absolute=started+1_800_000;this.idle=started+300_000;
      this.unexpired(epoch);this.arm(epoch);await this.check(epoch);
    } catch {
      if(epoch===this.generation)this.lock('The link expired or could not be used. Request a new root-authorized link.');
    }
  }
  private async check(epoch:number) {
    this.unexpired(epoch);const token=this.bearer;if(!token)throw new Superseded();
    const started=this.time.now();const data=await this.request(this.mode==='pilot'?'/v0/pilot':this.mode==='history'?'/v0/history':this.mode==='dashboard'?'/v0/dashboard':'/v0/setup',epoch,token);
    this.unexpired(epoch);
    if(this.mode==='pilot'?(data.synthetic!==true||typeof data.message!=='string'||data.message.length>1024):this.mode==='history'?(data.format!=='hids.m4.history-view/1'||data.history_only!==true||data.monitoring_status!=='not_assessed'):this.mode==='dashboard'?(data.format!=='hids.dashboard-view/1'||data.history_only!==true||data.monitoring_status!=='not_assessed'):(data.format!=='hids.setup-view/1'||data.snapshot_only!==true||data.monitoring_status!=='not_assessed'))throw new Error('invalid data');
    this.idle=Math.min(this.absolute,started+300_000);this.unexpired(epoch);this.arm(epoch);
    this.publish({status:'Authorized',message:this.mode==='pilot'?data.message:this.mode==='setup'?'Setup snapshot':'Stored snapshot',notice:''});
  }
  async checkAccess() {
    const epoch=this.generation;
    try {await this.check(epoch);}catch {if(epoch===this.generation)this.lock();}
  }
  async fetchProtected(path:string):Promise<{generation:number;data:unknown}|undefined> {
    const epoch=this.generation;
    try {
      if(!((this.mode==='setup'&&path==='/v0/setup')||((this.mode==='history'||this.mode==='dashboard')&&/^\/v0\/history(?:\/(?:events|findings)(?:\/[0-9a-f]{64}|\?cursor=[A-Za-z0-9_-]{1,512})?)?$/.test(path))||(this.mode==='dashboard'&&(path==='/v0/dashboard'||/^\/v0\/process\/events(?:\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|\?cursor=[A-Za-z0-9_-]{1,512})?$/.test(path)))))throw new Error('invalid route');
      this.unexpired(epoch);const token=this.bearer;if(!token)throw new Superseded();
      const started=this.time.now();const data:unknown=await this.request(path,epoch,token);
      this.unexpired(epoch);this.idle=Math.min(this.absolute,started+300_000);this.unexpired(epoch);this.arm(epoch);
      return {generation:epoch,data};
    } catch(error) {
      if(error instanceof FamilyUnavailable&&epoch===this.generation){
        try{this.unexpired(epoch);return {generation:epoch,data:{available:false}};}catch{return undefined;}
      }
      if(epoch===this.generation)this.lock();return undefined;
    }
  }
  async stageDraft(body:{assessment_id:string;confirmed_revision:number;selected:string[]}):Promise<{generation:number;data:unknown}|undefined> {
    const epoch=this.generation;
    try {
      if(this.mode!=='setup')throw new Error('invalid mode');this.unexpired(epoch);const token=this.bearer;if(!token)throw new Superseded();
      const started=this.time.now();const data=await this.request('/v0/setup/draft',epoch,token,body);this.unexpired(epoch);
      if(typeof data.reference!=='string'||!/^[A-Za-z0-9_-]{43}$/.test(data.reference)||data.expires_seconds!==60||data.requires_root_confirmation!==true)throw new Error('invalid draft');
      this.idle=Math.min(this.absolute,started+300_000);this.unexpired(epoch);this.arm(epoch);return {generation:epoch,data};
    }catch {if(epoch===this.generation)this.lock();return undefined;}
  }
  async logout() {
    const token=this.bearer;this.lock();
    if(!token)return;
    // A logout response must never modify a newer authorization. Local state is
    // cleared immediately; this captured token is used only for server revocation.
    const controller=new AbortController();
    const timeout=this.time.set(()=>controller.abort(),3000);
    try {await this.transport('/v0/auth/logout',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:'{}',signal:controller.signal,credentials:'omit',cache:'no-store',redirect:'error'});}
    catch {} finally {this.time.clear(timeout);}
  }
  dispose() {this.lock();this.listeners.clear();}
}
