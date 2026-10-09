import {test} from 'node:test';
import assert from 'node:assert/strict';
import * as requests from '../src/request-browser.ts';
import {generateDevice} from '../src/crypto-web.ts';
import {verifySigned} from '../src/membership-core.ts';
import {strictLoads} from '../../sync-protocol/src/browser.ts';
import {b64decode} from '../src/binary.ts';
test('request signs exact Relay domain, body digest and fresh identity',async()=>{
 assert.equal(typeof requests.prepareRequest,'function');
 const d=await generateDevice();
 const t={id:crypto.randomUUID(),headDigest:'a'.repeat(64),membershipEpoch:2,keyEpoch:1};
 const a=await requests.prepareRequest(d,t,'POST','/v1/hello',{},{});
 const b=await requests.prepareRequest(d,t,'POST','/v1/hello',{},{});
 const p=strictLoads(b64decode(a.proof)) as Record<string,any>;
 await verifySigned('RelayRequest',p,d.signingPublic);
 assert.equal(p.audience,'ResearchHub/SecureRelay/QA/v1');
 assert.equal(p.body_digest,'44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a');
 assert.notEqual(a.proof,b.proof);
 await assert.rejects(requests.prepareRequest(d,t,'GET','/v1/messages',{cursor:true,limit:10}),/INVALID_QUERY/);
});


test('request query is sorted and response parser fails closed (unit fault injection)',async()=>{
 const d=await generateDevice(),t={id:crypto.randomUUID(),headDigest:'a'.repeat(64),membershipEpoch:2,keyEpoch:1};
 const p=await requests.prepareRequest(d,t,'GET','/v1/messages',{limit:10,cursor:0});
 assert.match(p.url,/cursor=0&limit=10$/);
 const original=globalThis.fetch;
 try{
  globalThis.fetch=async(_url,init)=>{
   assert.equal(init?.credentials,'omit');assert.equal(init?.redirect,'error');
   assert.equal(new Headers(init?.headers).has('accept-encoding'),false);
   return new Response(' {"ok":true,"result":{}}');
  };
  await assert.rejects(requests.relayFetch(d,t,'POST','/v1/hello',{},{}),/NONCANONICAL_RESPONSE/);
  globalThis.fetch=async()=>new Response('x'.repeat(524289));
  await assert.rejects(requests.relayFetch(d,t,'POST','/v1/hello',{},{}),/RESPONSE_TOO_LARGE/);
  globalThis.fetch=async()=>new Response('{"ok":true,"ok":true,"result":{}}');
  await assert.rejects(requests.relayFetch(d,t,'POST','/v1/hello',{},{}),/duplicate/);
 }finally{globalThis.fetch=original;}
});
