const ORIGIN='__ORIGIN__';
const CACHE='__CACHE__';
const ASSETS=['/index.html','/app.js','/app.css','/icon.svg'];
const route=p=>p==='/'||p==='/diagnostics'||/^\/projects\/(generic|hdsp|ice)(\/(runs|notes)\/[a-zA-Z0-9-]+)?$/.test(p);
if(self.location.origin===ORIGIN){
 self.addEventListener('message',event=>{if(event.data?.type!=='QA_CHECK_SHELL'||!event.ports[0])return;event.waitUntil((async()=>{const cache=await caches.open(CACHE);const ready=(await Promise.all(ASSETS.map(path=>cache.match(path)))).every(response=>response?.ok);event.ports[0].postMessage({type:'QA_SHELL_READY',ready});})());});
 self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(async cache=>{for(const path of ASSETS){const response=await fetch(path==='/index.html'?'/':path,{cache:'reload'});if(!response.ok)throw Error('Shell fetch failed');await cache.put(path,response);}})));
 self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
 // No skipWaiting, cache deletion, API responses or dynamic user content.
 self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(url.origin!==ORIGIN||event.request.method!=='GET'||url.search)return;
 const key=event.request.mode==='navigate'&&route(url.pathname)?'/index.html':ASSETS.includes(url.pathname)?url.pathname:null;
 if(key)event.respondWith(caches.open(CACHE).then(async cache=>(await cache.match(key))||fetch(event.request)));
 });
}
