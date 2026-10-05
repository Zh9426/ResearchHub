import type {NextRequest} from 'next/server';
export const dynamic='force-dynamic';
async function proxy(request:NextRequest,{params}:{params:Promise<{path:string[]}>}){
 const {path}=await params;
 const target=new URL(`/api/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`,process.env.API_INTERNAL_URL??'http://127.0.0.1:8000');
 const headers=new Headers(request.headers);headers.delete('host');headers.delete('connection');headers.delete('content-length');
 // Browser supplies Origin; forwarded transport headers are server-owned.
 headers.set('x-forwarded-host',request.nextUrl.host);headers.set('x-forwarded-proto',request.nextUrl.protocol.replace(':',''));
 try{
  const init:RequestInit&{duplex?:string}={method:request.method,headers,redirect:'manual',cache:'no-store',signal:request.signal};
  if(!['GET','HEAD'].includes(request.method)){init.body=request.body;init.duplex='half';}
  const upstream=await fetch(target,init);
  const out=new Headers(upstream.headers);out.delete('content-encoding');out.delete('content-length');out.delete('transfer-encoding');out.set('cache-control','no-store');
  return new Response(upstream.body,{status:upstream.status,headers:out});
 }catch{return Response.json({detail:'API 服务暂时不可用。请确认 Research Hub API 已启动。'},{status:502});}
}
export {proxy as GET,proxy as POST,proxy as PATCH,proxy as DELETE,proxy as PUT,proxy as OPTIONS,proxy as HEAD};
