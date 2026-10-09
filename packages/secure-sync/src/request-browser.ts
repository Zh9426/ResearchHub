/** Native browser request signatures. No retry, cookie or redirect authority. */
import {canonicalBytes,strictLoads} from '../../sync-protocol/src/browser.ts';
import {sign,sha256,type DeviceKeys} from './crypto-web.ts';
import {b64encode,equal} from './binary.ts';
import {preimage,integer,uuid,hex,type PublicObject} from './membership-core.ts';
export const RELAY='https://127.0.0.1:38001';
export const AUDIENCE='ResearchHub/SecureRelay/QA/v1';
type RequestTrust={id:string;headDigest:string;membershipEpoch:number;keyEpoch:number};
const gets:Record<string,Record<string,string>>={
 '/v1/messages':{cursor:'int',limit:'limit'},'/v1/membership':{},'/v1/membership/receipt':{candidate_digest:'digest'},'/v1/grants':{session_id:'uuid'},'/v1/pairing/challenge':{session_id:'uuid'},'/v1/pairing/receipt':{session_id:'uuid'},'/v1/checkpoints':{},'/v1/chunks':{opaque_locator:'uuid',index:'index'},
};
const posts=new Set(['/v1/hello','/v1/messages','/v1/ack','/v1/membership','/v1/membership/recovery','/v1/grants','/v1/pairing/challenge','/v1/pairing/submit','/v1/pairing/complete','/v1/checkpoints','/v1/chunks']);
export async function prepareRequest(d:DeviceKeys,t:RequestTrust,method:'GET'|'POST',path:string,query:PublicObject={},body?:unknown){
 let suffix='';
 if(method==='GET'){
  const spec=gets[path];
  try{
   if(!spec||Object.keys(query).sort().join()!==Object.keys(spec).sort().join()||body!==undefined)throw Error();
   for(const [k,kind] of Object.entries(spec)){
    if(kind==='uuid')uuid(query[k]);else if(kind==='digest')hex(query[k],32);else integer(query[k],kind==='limit'?1:0,kind==='limit'?100:kind==='index'?15:Number.MAX_SAFE_INTEGER);
   }
   suffix=Object.keys(query).sort().map(k=>`${k}=${query[k]}`).join('&');
  }catch{throw Error('INVALID_QUERY');}
 }else if(!posts.has(path)||Object.keys(query).length||body===undefined)throw Error('INVALID_REQUEST');
 uuid(t.id);uuid(d.deviceId);hex(t.headDigest,32);integer(t.membershipEpoch,1);integer(t.keyEpoch,1);
 const raw=method==='POST'?canonicalBytes(body):new Uint8Array();
 if(raw.length>524288)throw Error('REQUEST_TOO_LARGE');
 const proof:PublicObject={version:1,audience:AUDIENCE,method,path,query,opaque_project_id:t.id,device_id:d.deviceId,membership_epoch:t.membershipEpoch,key_epoch:t.keyEpoch,manifest_digest:t.headDigest,body_digest:await sha256(raw),request_id:crypto.randomUUID(),issued_at:Math.floor(Date.now()/1000)};
 proof.signature=b64encode(await sign(d.signing.privateKey,preimage('RelayRequest',proof)));
 return {url:RELAY+path+(suffix?'?'+suffix:''),proof:b64encode(canonicalBytes(proof)),raw};
}
export async function relayFetch(d:DeviceKeys,t:RequestTrust,method:'GET'|'POST',path:string,query:PublicObject={},body?:unknown):Promise<PublicObject>{
 const prepared=await prepareRequest(d,t,method,path,query,body),controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),15000);
 try{
  const response=await fetch(prepared.url,{method,credentials:'omit',redirect:'error',cache:'no-store',signal:controller.signal,headers:{'x-rh-proof':prepared.proof,...(method==='POST'?{'content-type':'application/json'}:{})},body:method==='POST'?Uint8Array.from(prepared.raw):undefined});
  const reader=response.body?.getReader();if(!reader)throw Error('RESPONSE_MISSING');
  const chunks:Uint8Array[]=[];let size=0;
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>524288){await reader.cancel();throw Error('RESPONSE_TOO_LARGE');}chunks.push(value);}
  const raw=new Uint8Array(size);let offset=0;for(const c of chunks){raw.set(c,offset);offset+=c.length;}
  const value=strictLoads(raw) as PublicObject;
  if(!equal(canonicalBytes(value),raw))throw Error('NONCANONICAL_RESPONSE');
  if(!response.ok||value.ok!==true)throw Error('RELAY_REJECTED');
  return value.result;
 }finally{clearTimeout(timer);}
}
