import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {runInNewContext} from 'node:vm';
import {describe,it,expect,vi} from 'vitest';

function worker(){
 const handlers:Record<string,(event:any)=>void>={};
 const offline={kind:'offline'};
 const fetch=vi.fn().mockRejectedValue(new Error('Offline'));
 const match=vi.fn().mockResolvedValue(offline);
 runInNewContext(readFileSync(resolve('public/sw.js'),'utf8'),{
  URL,Promise,fetch,caches:{match},
  self:{location:{origin:'https://hub.test'},addEventListener:(name:string,fn:any)=>handlers[name]=fn},
 });
 return {handlers,fetch,match,offline};
}

describe('PWA private data boundary',()=>{
 it('does not intercept authenticated API requests or writes',()=>{
  const {handlers,fetch,match}=worker();
  for(const request of [
   {url:'https://hub.test/api/projects',method:'GET',mode:'cors'},
   {url:'https://hub.test/api/auth/me',method:'GET',mode:'cors'},
   {url:'https://hub.test/projects',method:'POST',mode:'navigate'},
  ]){
   const respondWith=vi.fn();handlers.fetch({request,respondWith});
   expect(respondWith).not.toHaveBeenCalled();
  }
  expect(fetch).not.toHaveBeenCalled();expect(match).not.toHaveBeenCalled();
 });
 it('falls back to the static offline explanation without caching a private page',async()=>{
  const {handlers,fetch,match,offline}=worker();
  let result:Promise<unknown>|undefined;
  handlers.fetch({request:{url:'https://hub.test/projects/private-id',method:'GET',mode:'navigate'},respondWith:(p:Promise<unknown>)=>result=p});
  expect(await result).toEqual(offline);expect(fetch).toHaveBeenCalledTimes(1);
  expect(match).toHaveBeenCalledWith('/offline.html');
 });
 it('ships a standalone manifest with matching PNG icon sizes',()=>{
  const manifest=JSON.parse(readFileSync(resolve('public/manifest.webmanifest'),'utf8'));
  expect(manifest.display).toBe('standalone');expect(manifest.start_url).toBe('/');
  for(const icon of manifest.icons){
   const bytes=readFileSync(resolve('public',icon.src.slice(1)));
   expect(bytes.subarray(0,8).toString('hex')).toBe('89504e470d0a1a0a');
   expect(`${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`).toBe(icon.sizes);
  }
 });
});
