import {zh,zhError} from './zh';
let csrfToken = '';
export function setCsrfToken(value: string) { csrfToken = value; }
export class ApiError extends Error { constructor(message: string, public status: number) {super(message);} }
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const isForm = init.body instanceof FormData;
  if (init.body && !isForm) headers.set('Content-Type','application/json');
  if (init.method && !['GET','HEAD'].includes(init.method)) headers.set('X-CSRF-Token',csrfToken);
  const response = await fetch(`/api${path}`, {...init,headers,credentials:'same-origin',cache:'no-store'}).catch(()=>{throw new ApiError('无法连接科研服务，请检查本机服务是否运行。',0);});
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === 'string' ? zhError(detail) : Array.isArray(detail) ? detail.map((x: {loc?:string[];msg:string}) => `${zh(x.loc?.at(-1)??'输入')}: ${zhError(x.msg)}`).join(' · ') : `请求失败 (${response.status})`;
    throw new ApiError(message,response.status);
  }
  return response.status === 204 ? undefined as T : response.json();
}
export const post = <T>(path:string,body:unknown) => api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const patch = <T>(path:string,body:unknown) => api<T>(path,{method:'PATCH',body:JSON.stringify(body)});
