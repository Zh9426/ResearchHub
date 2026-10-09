const READY_TIMEOUT_MS=15000;
// The controlling worker confirms its own complete static cache; a controller alone is insufficient.
export function verifyControlledShell(timeout=3000):Promise<boolean>{
 const controller=navigator.serviceWorker?.controller;
 if(!controller||controller.state!=='activated')return Promise.resolve(false);
 return new Promise(resolve=>{
  const channel=new MessageChannel();
  const finish=(ready:boolean)=>{clearTimeout(timer);channel.port1.onmessage=null;channel.port1.close();channel.port2.close();resolve(ready);};
  const timer=setTimeout(()=>finish(false),timeout);
  channel.port1.onmessage=event=>finish(event.data?.type==='QA_SHELL_READY'&&event.data.ready===true&&navigator.serviceWorker.controller===controller);
  try{controller.postMessage({type:'QA_CHECK_SHELL'},[channel.port2]);}catch{finish(false);}
 });
}
export function initializeOfflineResources():Promise<void>{
 if(!navigator.serviceWorker)return Promise.reject(new Error('当前浏览器不支持 Service Worker'));
 return new Promise((resolve,reject)=>{
  const workers=new Set<ServiceWorker>();let registration:ServiceWorkerRegistration|undefined,finished=false,checking=false;
  const cleanup=()=>{clearTimeout(timer);navigator.serviceWorker.removeEventListener('controllerchange',check);registration?.removeEventListener('updatefound',track);for(const worker of workers)worker.removeEventListener('statechange',check);};
  const finish=(error?:Error)=>{if(finished)return;finished=true;cleanup();error?reject(error):resolve();};
  const timer=setTimeout(()=>finish(new Error('离线资源准备超时，请检查静态服务后重试')),READY_TIMEOUT_MS);
  async function check(){
   if(finished)return;
   if([...workers].some(worker=>worker.state==='redundant')){finish(new Error('离线资源安装失败，请检查静态资源后重试'));return;}
   if(navigator.serviceWorker.controller?.state==='activated'&&!checking){checking=true;const ready=await verifyControlledShell();checking=false;if(finished)return;if(ready)finish();else finish(new Error('离线缓存不完整，请重试'));}
  }
  function track(){for(const worker of [registration?.installing,registration?.waiting,registration?.active]){if(worker&&!workers.has(worker)){workers.add(worker);worker.addEventListener('statechange',check);}}void check();}
  navigator.serviceWorker.addEventListener('controllerchange',check);
  navigator.serviceWorker.register('/sw.js',{scope:'/'}).then(value=>{if(finished)return;registration=value;registration.addEventListener('updatefound',track);track();},error=>finish(error instanceof Error?error:new Error(String(error))));
 });
}
